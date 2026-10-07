"""The pre-generated example outputs must match what `agent sync` produces."""

from __future__ import annotations

from pathlib import Path

import pytest

from middletic.core.loader import load_config
from middletic.core.sync import plan_sync
from middletic.doctor.checks import Level, run_doctor

EXAMPLES = Path(__file__).parent.parent / "examples"
EXAMPLE_DIRS = sorted(p for p in EXAMPLES.iterdir() if (p / "agent.toml").exists())


def test_examples_exist() -> None:
    assert {p.name for p in EXAMPLE_DIRS} == {"laravel", "python"}


@pytest.mark.parametrize("example", EXAMPLE_DIRS, ids=lambda p: p.name)
def test_example_outputs_are_up_to_date(example: Path) -> None:
    plan = plan_sync(example / "agent.toml")
    assert len(plan.files) == 4
    for fp in plan.files:
        assert fp.action == "unchanged", f"{fp.filename} is stale: run `agent sync` in {example}"


@pytest.mark.parametrize("example", EXAMPLE_DIRS, ids=lambda p: p.name)
def test_example_configs_are_clean(example: Path) -> None:
    load_config(example / "agent.toml")
    checks = run_doctor(example / "agent.toml")
    assert not [c for c in checks if c.level is Level.ERROR]
    assert [c.level for c in checks if c.name == "secrets"] == [Level.OK]
