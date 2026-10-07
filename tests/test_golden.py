"""Golden-file tests: deterministic output for every target."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from middletic.adapters.base import AgentAdapter
from middletic.adapters.registry import ADAPTERS
from middletic.cli.main import app
from middletic.core.ir import build_ir
from middletic.core.loader import load_config

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden"
GOLDEN_NAMES = {
    "claude": "CLAUDE.md",
    "codex": "AGENTS.md",
    "gemini": "GEMINI.md",
    "cursor": "agent.mdc",
}

runner = CliRunner()


def _render(adapter: AgentAdapter) -> str:
    ir = build_ir(load_config(FIXTURES / "agent.toml"))
    ((filename, body),) = adapter.generate(ir).items()
    return adapter.merge(ir, filename, body, "")


def test_golden_names_cover_registry() -> None:
    assert set(GOLDEN_NAMES) == set(ADAPTERS)


@pytest.mark.parametrize("name", sorted(GOLDEN_NAMES))
def test_golden_output(name: str) -> None:
    actual = _render(ADAPTERS[name])
    golden = GOLDEN / GOLDEN_NAMES[name]
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.write_text(actual, encoding="utf-8")
    assert actual == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(GOLDEN_NAMES))
def test_golden_output_is_deterministic_and_idempotent(name: str) -> None:
    adapter = ADAPTERS[name]
    ir = build_ir(load_config(FIXTURES / "agent.toml"))
    ((filename, body),) = adapter.generate(ir).items()
    first = adapter.merge(ir, filename, body, "")
    assert adapter.merge(ir, filename, body, first) == first


def test_cli_sync_writes_all_enabled_targets(tmp_path: Path) -> None:
    (tmp_path / "agent.toml").write_bytes((FIXTURES / "agent.toml").read_bytes())
    cfg = str(tmp_path / "agent.toml")

    assert runner.invoke(app, ["sync", "-c", cfg]).exit_code == 0
    for name, golden_name in GOLDEN_NAMES.items():
        written = tmp_path / ADAPTERS[name].filename
        assert written.read_text(encoding="utf-8") == (GOLDEN / golden_name).read_text(
            encoding="utf-8"
        )

    second = runner.invoke(app, ["sync", "-c", cfg])
    assert second.output.count("up to date") == 4
