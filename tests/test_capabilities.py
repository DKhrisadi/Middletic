"""Capability matrix, degradation, and new CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from middletic.adapters.registry import ADAPTERS, get_adapter
from middletic.capabilities.degradation import render_cautions, required_capabilities
from middletic.capabilities.matrix import agent_names, native_capabilities
from middletic.capabilities.model import Capability
from middletic.cli.main import app
from middletic.core.ir import build_ir
from middletic.core.loader import ConfigError, load_config, parse_config

FIXTURE = Path(__file__).parent / "fixtures" / "agent.toml"
runner = CliRunner()


def test_matrix_matches_registry() -> None:
    assert set(agent_names()) == set(ADAPTERS)
    for name, adapter in ADAPTERS.items():
        assert adapter.capabilities == native_capabilities(name)


def test_gemini_permissions_degrade_but_are_kept() -> None:
    body = next(iter(get_adapter("gemini").generate(build_ir(load_config(FIXTURE))).values()))
    assert "Denied: `rm -rf`" in body
    assert "## Important Cautions" in body
    assert "NOT enforced by tooling" in body
    assert "Gemini CLI" in body


def test_claude_has_no_cautions() -> None:
    body = next(iter(get_adapter("claude").generate(build_ir(load_config(FIXTURE))).values()))
    assert "Important Cautions" not in body


def test_no_caution_when_feature_unused() -> None:
    ir = build_ir(parse_config('[project]\nname = "x"\n'))
    assert required_capabilities(ir) == {Capability.INSTRUCTIONS}
    assert render_cautions("Gemini CLI", native_capabilities("gemini"), ir) == ""


def test_cursor_frontmatter_only_on_new_file() -> None:
    adapter = get_adapter("cursor")
    ir = build_ir(load_config(FIXTURE))
    ((filename, body),) = adapter.generate(ir).items()
    created = adapter.merge(ir, filename, body, "")
    assert created.startswith('---\ndescription: "')
    assert "alwaysApply: true\n---\n" in created
    # An existing file's frontmatter is untouched.
    custom = '---\nglobs: "*.py"\n---\n\nmine\n'
    merged = adapter.merge(ir, filename, body, custom)
    assert merged.startswith(custom)


def test_targets_default_and_validation() -> None:
    assert parse_config('[project]\nname = "x"\n').targets.enabled == ["claude"]
    for bad in ("enabled = []", 'enabled = ["vim"]', 'enabled = ["claude", "claude"]'):
        with pytest.raises(ConfigError):
            parse_config(f'[project]\nname = "x"\n[targets]\n{bad}\n')


def test_cli_adapters_lists_all_agents() -> None:
    result = runner.invoke(app, ["adapters"])
    assert result.exit_code == 0
    for name in ADAPTERS:
        assert name in result.output
    assert "native" in result.output and "degrades" in result.output


def test_cli_explain_gemini() -> None:
    result = runner.invoke(app, ["explain", "gemini"])
    assert result.exit_code == 0
    assert "GEMINI.md" in result.output
    assert "permissions.deny" in result.output
    assert "degraded" in result.output
    assert "testing.required" in result.output


def test_cli_explain_unknown() -> None:
    result = runner.invoke(app, ["explain", "vim"])
    assert result.exit_code == 1
