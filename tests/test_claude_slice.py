"""End-to-end tests: agent.toml -> IR -> Claude adapter -> CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from middletic.adapters.base import MANAGED_END, MANAGED_START, ManagedBlockError
from middletic.adapters.claude import ClaudeAdapter
from middletic.cli.main import app
from middletic.core.ir import build_ir
from middletic.core.loader import ConfigError, parse_config

FULL_TOML = """
[project]
name = "demo"
description = "A demo project."

[agent]
role = "Senior Python engineer"

[behavior]
tone = "concise"
explain_changes = true
ask_before_destructive_actions = true

[code]
style = "PEP 8, full typing"
language = "Python"

[testing]
required = true
command = "pytest -q"

[git]
branch_prefix = "feat/"
require_clean_worktree = true

[permissions]
allow = ["read"]
deny = ["rm -rf"]

[mcp.github]
command = "npx"
args = ["-y", "server-github"]
env = { GITHUB_TOKEN = "secret-value" }
"""

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "agent.toml").write_text(FULL_TOML, encoding="utf-8")
    return tmp_path


# --- parsing / validation -------------------------------------------------


def test_parse_valid_config() -> None:
    cfg = parse_config(FULL_TOML)
    assert cfg.project.name == "demo"
    assert cfg.mcp["github"].args == ["-y", "server-github"]


def test_minimal_config_uses_defaults() -> None:
    cfg = parse_config('[project]\nname = "x"\n')
    assert cfg.behavior.explain_changes is True
    assert cfg.permissions.allow == []


@pytest.mark.parametrize(
    "toml",
    [
        "",  # missing [project]
        '[project]\nname = ""\n',
        '[project]\nname = "x"\nbogus = 1\n',
        '[project]\nname = "x"\n[unknown]\na = 1\n',
        '[project]\nname = "x"\n[testing]\nrequired = true\n',
        '[project]\nname = "x"\n[permissions]\nallow = ["a"]\ndeny = ["a"]\n',
        '[project]\nname = "x"\n[mcp.s]\nargs = []\n',
        "[project\n",
    ],
)
def test_invalid_configs_rejected(toml: str) -> None:
    with pytest.raises(ConfigError):
        parse_config(toml)


# --- IR -------------------------------------------------------------------


def test_ir_is_decoupled_and_hides_env_values() -> None:
    ir = build_ir(parse_config(FULL_TOML))
    assert ir.project_name == "demo"
    assert ir.mcp_servers[0].env_keys == ("GITHUB_TOKEN",)
    assert "secret-value" not in repr(ir)


# --- adapter / managed block ----------------------------------------------


def test_generate_renders_markdown() -> None:
    files = ClaudeAdapter().generate(build_ir(parse_config(FULL_TOML)))
    body = files["CLAUDE.md"]
    assert body.startswith("# demo")
    assert "Run tests with `pytest -q`." in body
    assert "`github`: `npx -y server-github`" in body
    assert "secret-value" not in body


def test_inject_into_empty() -> None:
    out = ClaudeAdapter().inject_managed_block("", "hello")
    assert out == f"{MANAGED_START}\nhello\n{MANAGED_END}\n"


def test_inject_appends_and_preserves_manual_content() -> None:
    a = ClaudeAdapter()
    out = a.inject_managed_block("# My notes\n\nKeep me.\n", "gen")
    assert out.startswith("# My notes\n\nKeep me.\n\n")
    assert out.endswith(f"{MANAGED_START}\ngen\n{MANAGED_END}\n")


def test_inject_replaces_only_block() -> None:
    a = ClaudeAdapter()
    existing = f"before\n{MANAGED_START}\nold\n{MANAGED_END}\nafter\n"
    assert a.inject_managed_block(existing, "new") == (
        f"before\n{MANAGED_START}\nnew\n{MANAGED_END}\nafter\n"
    )


@pytest.mark.parametrize(
    "existing",
    [
        f"{MANAGED_START}\nno end\n",
        f"{MANAGED_END}\n{MANAGED_START}\n",
        f"{MANAGED_START}\n{MANAGED_END}\n{MANAGED_START}\n{MANAGED_END}\n",
    ],
)
def test_malformed_blocks_raise(existing: str) -> None:
    with pytest.raises(ManagedBlockError):
        ClaudeAdapter().inject_managed_block(existing, "x")


def test_new_content_with_delimiter_rejected() -> None:
    with pytest.raises(ManagedBlockError):
        ClaudeAdapter().inject_managed_block("", f"bad {MANAGED_END}")


def test_injection_is_idempotent() -> None:
    a = ClaudeAdapter()
    body = a.generate(build_ir(parse_config(FULL_TOML)))["CLAUDE.md"]
    once = a.inject_managed_block("# Notes\n", body)
    assert a.inject_managed_block(once, body) == once


# --- CLI ------------------------------------------------------------------


def test_cli_validate_ok(project: Path) -> None:
    result = runner.invoke(app, ["validate", "-c", str(project / "agent.toml")])
    assert result.exit_code == 0
    assert "valid" in result.output


def test_cli_validate_fails(tmp_path: Path) -> None:
    bad = tmp_path / "agent.toml"
    bad.write_text('[project]\nname = "x"\nbogus = 1\n', encoding="utf-8")
    result = runner.invoke(app, ["validate", "-c", str(bad)])
    assert result.exit_code == 1


def test_cli_validate_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", "-c", str(tmp_path / "agent.toml")])
    assert result.exit_code == 1


def test_cli_sync_create_update_idempotent(project: Path) -> None:
    cfg = str(project / "agent.toml")
    claude = project / "CLAUDE.md"

    assert runner.invoke(app, ["sync", "-c", cfg]).exit_code == 0
    first = claude.read_text(encoding="utf-8")
    assert MANAGED_START in first and "# demo" in first

    # Manual content outside the block survives a config change.
    claude.write_text("# Mine\n\n" + first + "\nFooter\n", encoding="utf-8")
    (project / "agent.toml").write_text(
        FULL_TOML.replace("Senior Python engineer", "Staff engineer"), encoding="utf-8"
    )
    result = runner.invoke(app, ["sync", "-c", cfg])
    assert "updated" in result.output
    second = claude.read_text(encoding="utf-8")
    assert second.startswith("# Mine\n\n")
    assert second.endswith("\nFooter\n")
    assert "Staff engineer" in second and "Senior Python engineer" not in second

    result = runner.invoke(app, ["sync", "-c", cfg])
    assert "up to date" in result.output
    assert claude.read_text(encoding="utf-8") == second


def test_cli_sync_dry_run_writes_nothing(project: Path) -> None:
    result = runner.invoke(app, ["sync", "-c", str(project / "agent.toml"), "--dry-run"])
    assert result.exit_code == 0
    assert not (project / "CLAUDE.md").exists()


def test_cli_sync_refuses_malformed_block(project: Path) -> None:
    (project / "CLAUDE.md").write_text(f"{MANAGED_START}\nbroken\n", encoding="utf-8")
    result = runner.invoke(app, ["sync", "-c", str(project / "agent.toml")])
    assert result.exit_code == 1
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == f"{MANAGED_START}\nbroken\n"
