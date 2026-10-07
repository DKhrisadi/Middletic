"""``agent doctor`` and ``agent init``."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from middletic.cli.main import app
from middletic.core.loader import load_config, parse_config
from middletic.doctor.checks import Check, Level, check_permissions, run_doctor
from middletic.doctor.secrets import scan

runner = CliRunner()

FAKE_TOKENS = {
    "openai": "sk-abcdefghijklmnopqrstuvwx",
    "github": "ghp_abcdefghijklmnopqrstuvwxyz0123",
    "aws": "AKIAABCDEFGHIJKLMNOP",
    "slack": "xoxb-1234567890-abcdefghij",
    "jwt": "eyJhbGciOiJI.eyJzdWIiOiIxMjM0.abcdefghijkl",
    "bearer": "Bearer abcdefghijklmnopqrstuvwxyz",
}


def write(tmp: Path, body: str) -> Path:
    path = tmp / "agent.toml"
    path.write_text('[project]\nname = "x"\n' + body, encoding="utf-8")
    return path


def levels(checks: list[Check], name: str) -> list[Level]:
    return [c.level for c in checks if c.name == name]


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


# --- secrets --------------------------------------------------------------


@pytest.mark.parametrize("token", FAKE_TOKENS.values(), ids=FAKE_TOKENS.keys())
def test_token_patterns_detected_in_env(token: str) -> None:
    findings = scan({"mcp": {"s": {"env": {"VALUE": token}}}})
    assert [f.path for f in findings] == ["mcp.s.env.VALUE"]
    assert token not in findings[0].reason


def test_sensitive_env_literal_flagged_but_env_ref_ok() -> None:
    raw = {"mcp": {"s": {"env": {"API_KEY": "hunter22", "TOKEN": "${MY_TOKEN}", "LOG": "debug"}}}}
    assert [f.path for f in scan(raw)] == ["mcp.s.env.API_KEY"]


def test_secret_in_args_and_description_detected() -> None:
    raw = {
        "project": {"description": "uses sk-abcdefghijklmnopqrstuvwx"},
        "mcp": {"s": {"args": ["--ok", "--token=abcdef123456"]}},
    }
    assert {f.path for f in scan(raw)} == {"project.description", "mcp.s.args[1]"}


def test_clean_config_has_no_findings() -> None:
    raw = {"project": {"name": "x"}, "mcp": {"s": {"command": "npx", "env": {"A": "${A}"}}}}
    assert scan(raw) == []


def test_doctor_warns_on_secret_without_leaking(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        f'[mcp.gh]\ncommand = "npx"\nenv = {{ GITHUB_TOKEN = "{FAKE_TOKENS["github"]}" }}\n',
    )
    checks = run_doctor(path)
    assert Level.WARN in levels(checks, "secrets")
    assert all(FAKE_TOKENS["github"] not in c.message for c in checks)
    result = runner.invoke(app, ["doctor", "-c", str(path)])
    assert FAKE_TOKENS["github"] not in result.output
    assert "mcp.gh.env.GITHUB_TOKEN" in result.output


def test_doctor_accepts_env_reference(tmp_path: Path) -> None:
    path = write(
        tmp_path, '[mcp.gh]\ncommand = "npx"\nenv = { GITHUB_TOKEN = "${GITHUB_TOKEN}" }\n'
    )
    assert levels(run_doctor(path), "secrets") == [Level.OK]


# --- schema ---------------------------------------------------------------


def test_doctor_invalid_schema_is_error(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    path.write_text("[project]\nbogus = 1\n", encoding="utf-8")
    assert Level.ERROR in levels(run_doctor(path), "schema")
    assert runner.invoke(app, ["doctor", "-c", str(path)]).exit_code == 1


def test_doctor_missing_file_is_error(tmp_path: Path) -> None:
    assert levels(run_doctor(tmp_path / "agent.toml"), "schema") == [Level.ERROR]


def test_doctor_invalid_toml_still_reports(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    path.write_text("[project\n", encoding="utf-8")
    checks = run_doctor(path)
    assert Level.ERROR in levels(checks, "schema")
    assert levels(checks, "secrets") == []


# --- git ------------------------------------------------------------------


def test_doctor_not_a_git_repo(tmp_path: Path) -> None:
    checks = run_doctor(write(tmp_path, ""))
    assert levels(checks, "git") == [Level.WARN]


def test_doctor_git_clean_and_dirty(tmp_path: Path) -> None:
    git_init(tmp_path)
    path = write(tmp_path, "")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-qm",
            "i",
        ],
        check=True,
    )
    assert levels(run_doctor(path), "git-clean") == [Level.OK]
    (tmp_path / "new.txt").write_text("x", encoding="utf-8")
    assert levels(run_doctor(path), "git-clean") == [Level.WARN]


def test_dirty_tree_is_error_when_clean_required(tmp_path: Path) -> None:
    git_init(tmp_path)
    path = write(tmp_path, "[git]\nrequire_clean_worktree = true\n")
    (tmp_path / "notes.txt").write_text("unrelated change")
    assert levels(run_doctor(path), "git-clean") == [Level.ERROR]
    assert runner.invoke(app, ["doctor", "-c", str(path)]).exit_code == 1


# --- permissions ----------------------------------------------------------


def perm_messages(toml_tail: str) -> list[str]:
    config = parse_config('[project]\nname = "x"\n' + toml_tail)
    return [c.message for c in check_permissions(config) if c.level is Level.WARN]


def test_sane_permissions_ok() -> None:
    config = parse_config(
        '[project]\nname = "x"\n[permissions]\nallow = ["read files"]\ndeny = ["rm -rf"]\n'
    )
    assert [c.level for c in check_permissions(config)] == [Level.OK]


@pytest.mark.parametrize("entry", ["*", "all", "Bash(*)"])
def test_broad_allow_warns(entry: str) -> None:
    msgs = perm_messages(f'[permissions]\nallow = ["{entry}"]\ndeny = ["rm"]\n')
    assert any("overly broad" in m for m in msgs)


@pytest.mark.parametrize(
    "entry", ["sudo apt install", "rm -rf build", "git push --force", "curl x | sh"]
)
def test_dangerous_allow_warns(entry: str) -> None:
    msgs = perm_messages(f'[permissions]\nallow = ["{entry}"]\ndeny = ["delete db"]\n')
    assert any("dangerous" in m for m in msgs)


def test_allow_without_deny_warns() -> None:
    assert any("nothing is denied" in m for m in perm_messages('[permissions]\nallow = ["read"]\n'))


def test_allow_conflicting_with_deny_warns() -> None:
    msgs = perm_messages('[permissions]\nallow = ["git push origin main"]\ndeny = ["git push"]\n')
    assert any("conflicts" in m for m in msgs)


def test_no_guard_rails_warns() -> None:
    msgs = perm_messages("[behavior]\nask_before_destructive_actions = false\n")
    assert any("no guard rails" in m for m in msgs)


def test_unenforceable_target_warns() -> None:
    msgs = perm_messages(
        '[permissions]\ndeny = ["rm"]\n[targets]\nenabled = ["claude", "gemini"]\n'
    )
    assert any("gemini cannot enforce" in m for m in msgs)
    assert not any("claude cannot" in m for m in msgs)


# --- init -----------------------------------------------------------------


def test_init_non_interactive_defaults(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    result = runner.invoke(app, ["init", "-c", str(path), "--non-interactive"])
    assert result.exit_code == 0
    config = load_config(path)
    assert config.project.name == tmp_path.name
    assert config.targets.enabled == ["claude"]
    assert config.testing.required is False


def test_init_non_interactive_options(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    result = runner.invoke(
        app,
        [
            "init", "-c", str(path), "--non-interactive", "--name", "demo",
            "--language", "Python", "--test-command", "pytest -q", "--targets", "claude, cursor",
        ],
    )  # fmt: skip
    assert result.exit_code == 0
    config = load_config(path)
    assert config.project.name == "demo"
    assert config.code.language == "Python"
    assert (config.testing.required, config.testing.command) == (True, "pytest -q")
    assert config.targets.enabled == ["claude", "cursor"]


def test_init_interactive(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    result = runner.invoke(
        app, ["init", "-c", str(path)], input="proj\nGo\ngo test ./...\ngemini,codex\n"
    )
    assert result.exit_code == 0
    config = load_config(path)
    assert config.project.name == "proj"
    assert config.testing.command == "go test ./..."
    assert config.targets.enabled == ["gemini", "codex"]


def test_init_interactive_reprompts_on_bad_targets(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    result = runner.invoke(app, ["init", "-c", str(path)], input="p\n\n\nvim\nclaude\n")
    assert result.exit_code == 0
    assert "unknown target" in result.output
    assert load_config(path).targets.enabled == ["claude"]


def test_init_rejects_unknown_target_non_interactive(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    result = runner.invoke(app, ["init", "-c", str(path), "--non-interactive", "--targets", "vim"])
    assert result.exit_code == 1
    assert not path.exists()


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    path.write_text("keep", encoding="utf-8")
    assert runner.invoke(app, ["init", "-c", str(path), "--non-interactive"]).exit_code == 1
    assert path.read_text(encoding="utf-8") == "keep"
    assert (
        runner.invoke(app, ["init", "-c", str(path), "--non-interactive", "--force"]).exit_code == 0
    )


def test_init_then_sync_and_status_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    runner.invoke(app, ["init", "-c", str(path), "--non-interactive", "--targets", "claude,cursor"])
    assert runner.invoke(app, ["sync", "-c", str(path)]).exit_code == 0
    assert runner.invoke(app, ["status", "-c", str(path)]).exit_code == 0


def test_version_flag() -> None:
    from typer.testing import CliRunner

    from middletic.cli.main import app

    for flag in ("--version", "-v"):
        result = CliRunner().invoke(app, [flag])
        assert result.exit_code == 0
        assert result.output.strip() == "Middletic v0.1.0"


def test_doctor_clean_after_init_and_sync(tmp_path: Path) -> None:
    import subprocess

    from typer.testing import CliRunner

    from middletic.cli.main import app

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    cfg = str(tmp_path / "agent.toml")
    runner = CliRunner()
    args = ["init", "-c", cfg, "--non-interactive", "--targets", "claude,cursor"]
    init = runner.invoke(app, args)
    assert init.exit_code == 0 and ".middletic/" in init.output
    assert runner.invoke(app, ["sync", "-c", cfg]).exit_code == 0
    doctor = runner.invoke(app, ["doctor", "-c", cfg])
    assert "[OK   ] git-clean" in doctor.output


def test_sync_warns_on_block_overwrite_and_bumps_timestamp(tmp_path: Path) -> None:
    import json

    from typer.testing import CliRunner

    from middletic.cli.main import app

    cfg = str(tmp_path / "agent.toml")
    runner = CliRunner()
    runner.invoke(app, ["init", "-c", cfg, "--non-interactive"])
    runner.invoke(app, ["sync", "-c", cfg])
    state = tmp_path / ".middletic" / "state.json"

    def forge_stamp() -> None:
        data = json.loads(state.read_text())
        data["last_sync"] = "2000-01-01T00:00:00+00:00"
        state.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    # True no-op: state stays byte-identical.
    forge_stamp()
    before = state.read_bytes()
    assert "Replaced" not in runner.invoke(app, ["sync", "-c", cfg]).output
    assert state.read_bytes() == before

    # Reconciling a drifted block: warns and advances last_sync.
    claude = tmp_path / "CLAUDE.md"
    claude.write_text(claude.read_text().replace("#", "# EDITED", 1))
    result = runner.invoke(app, ["sync", "-c", cfg])
    assert "Replaced manual edits inside managed block in CLAUDE.md" in result.output
    assert json.loads(state.read_text())["last_sync"] != "2000-01-01T00:00:00+00:00"
