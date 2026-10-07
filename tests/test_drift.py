"""State, diff, and status (drift detection)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from middletic.adapters.base import MANAGED_END, MANAGED_START, split_managed_block
from middletic.cli.main import app
from middletic.core.sync import apply_sync, plan_sync
from middletic.drift.state import (
    StateError,
    load_state,
    save_state,
    sha256_bytes,
    sha256_text,
    state_path,
)
from middletic.drift.status import FileState, Overall, compute_status

FIXTURE = Path(__file__).parent / "fixtures" / "agent.toml"
runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "agent.toml").write_bytes(FIXTURE.read_bytes())
    return tmp_path


def cfg(project: Path) -> str:
    return str(project / "agent.toml")


def sync(project: Path) -> None:
    assert runner.invoke(app, ["sync", "-c", cfg(project)]).exit_code == 0


def states(project: Path) -> dict[str, FileState]:
    plan = plan_sync(project / "agent.toml")
    report = compute_status(plan, load_state(project))
    return {f.filename: f.state for f in report.files}


# --- state ----------------------------------------------------------------


def test_sync_writes_state(project: Path) -> None:
    sync(project)
    state = load_state(project)
    assert state is not None
    assert state.config_hash == sha256_bytes((project / "agent.toml").read_bytes())
    assert set(state.adapters) == {"claude", "codex", "gemini", "cursor"}
    record = state.adapters["claude"]
    assert record.version == "1"
    claude = (project / "CLAUDE.md").read_text(encoding="utf-8")
    parts = split_managed_block(claude)
    assert parts is not None
    assert record.files["CLAUDE.md"].block_hash == sha256_text(parts[0])
    assert state.last_sync.endswith("+00:00")


def test_state_json_is_stable_when_nothing_changes(project: Path) -> None:
    sync(project)
    before = state_path(project).read_bytes()
    sync(project)
    assert state_path(project).read_bytes() == before


def test_dry_run_writes_no_state(project: Path) -> None:
    runner.invoke(app, ["sync", "-c", cfg(project), "--dry-run"])
    assert not state_path(project).exists()


def test_last_sync_uses_injected_clock(project: Path) -> None:
    plan = plan_sync(project / "agent.toml")
    state = apply_sync(plan, now=datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC))
    assert state.last_sync == "2030-01-02T03:04:05+00:00"


def test_corrupt_state_raises(project: Path) -> None:
    path = state_path(project)
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError):
        load_state(project)
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 1


def test_save_state_roundtrip(project: Path) -> None:
    sync(project)
    state = load_state(project)
    assert state is not None
    save_state(project, state)
    assert load_state(project) == state


# --- diff -----------------------------------------------------------------


def test_diff_new_files_and_no_writes(project: Path) -> None:
    result = runner.invoke(app, ["diff", "-c", cfg(project)])
    assert result.exit_code == 0
    assert "--- /dev/null" in result.output
    assert "+++ b/CLAUDE.md" in result.output
    assert not (project / "CLAUDE.md").exists()
    assert not state_path(project).exists()


def test_diff_no_changes_after_sync(project: Path) -> None:
    sync(project)
    result = runner.invoke(app, ["diff", "-c", cfg(project)])
    assert "No changes." in result.output


def test_diff_shows_only_managed_block_change(project: Path) -> None:
    sync(project)
    (project / "agent.toml").write_text(
        FIXTURE.read_text(encoding="utf-8").replace("Senior Python engineer", "Staff engineer"),
        encoding="utf-8",
    )
    before = (project / "CLAUDE.md").read_text(encoding="utf-8")
    result = runner.invoke(app, ["diff", "-c", cfg(project)])
    assert "-Senior Python engineer" in result.output
    assert "+Staff engineer" in result.output
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == before


def test_diff_json(project: Path) -> None:
    sync(project)
    (project / "CLAUDE.md").unlink()
    result = runner.invoke(app, ["diff", "-c", cfg(project), "--json"])
    data = json.loads(result.output)
    by_file = {e["file"]: e for e in data}
    assert by_file["CLAUDE.md"]["action"] == "created"
    assert by_file["CLAUDE.md"]["diff"].startswith("--- /dev/null")
    assert by_file["AGENTS.md"]["action"] == "unchanged"
    assert by_file["AGENTS.md"]["diff"] == ""


# --- status ---------------------------------------------------------------


def test_status_never_synced(project: Path) -> None:
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 1
    assert "DRIFTED" in result.output
    assert "No previous sync" in result.output
    assert set(states(project).values()) == {FileState.MISSING}


def test_status_synced(project: Path) -> None:
    sync(project)
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 0
    assert "Status: SYNCED" in result.output
    assert "Config modified since last sync: no" in result.output


def test_status_config_modified(project: Path) -> None:
    sync(project)
    (project / "agent.toml").write_text(
        FIXTURE.read_text(encoding="utf-8").replace("concise", "friendly"), encoding="utf-8"
    )
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 1
    assert "Config modified since last sync: yes" in result.output
    assert set(states(project).values()) == {FileState.STALE}


def test_status_comment_only_config_change_is_drifted(project: Path) -> None:
    sync(project)
    (project / "agent.toml").write_text(
        "# note\n" + FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    plan = plan_sync(project / "agent.toml")
    report = compute_status(plan, load_state(project))
    assert report.config_changed
    assert report.overall is Overall.DRIFTED
    assert {f.state for f in report.files} == {FileState.SYNCED}


def test_status_missing_file(project: Path) -> None:
    sync(project)
    (project / "GEMINI.md").unlink()
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 1
    assert "GEMINI.md: MISSING" in result.output
    assert states(project)["GEMINI.md"] is FileState.MISSING
    assert states(project)["CLAUDE.md"] is FileState.SYNCED


def test_status_removed_block_counts_as_missing(project: Path) -> None:
    sync(project)
    (project / "AGENTS.md").write_text("# just mine\n", encoding="utf-8")
    assert states(project)["AGENTS.md"] is FileState.MISSING


def test_status_edit_inside_block(project: Path) -> None:
    sync(project)
    path = project / "CLAUDE.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Senior Python engineer", "HACKED"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 1
    assert "CLAUDE.md: BLOCK_EDITED" in result.output
    assert "outside the managed block" not in result.output


def test_status_edit_outside_block_is_preserved_and_not_drift(project: Path) -> None:
    sync(project)
    path = project / "CLAUDE.md"
    path.write_text("# My notes\n\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert result.exit_code == 0
    assert "Status: SYNCED" in result.output
    assert "manual edits outside the managed block" in result.output


def test_status_inside_and_outside_edits_reported_separately(project: Path) -> None:
    sync(project)
    path = project / "CLAUDE.md"
    text = path.read_text(encoding="utf-8").replace("concise", "chatty")
    path.write_text(text + "\nFooter\n", encoding="utf-8")
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    assert "BLOCK_EDITED" in result.output
    assert "manual edits outside the managed block" in result.output


def test_status_malformed_block(project: Path) -> None:
    sync(project)
    (project / "CLAUDE.md").write_text(f"{MANAGED_START}\nbroken\n", encoding="utf-8")
    result = runner.invoke(app, ["status", "-c", cfg(project)])
    # plan_sync refuses malformed blocks outright rather than guessing.
    assert result.exit_code == 1
    assert MANAGED_END not in (project / "CLAUDE.md").read_text(encoding="utf-8")


def test_resync_heals_drift(project: Path) -> None:
    sync(project)
    path = project / "CLAUDE.md"
    path.write_text(path.read_text(encoding="utf-8").replace("concise", "chatty"), encoding="utf-8")
    sync(project)
    assert runner.invoke(app, ["status", "-c", cfg(project)]).exit_code == 0


def test_status_invalid_config(project: Path) -> None:
    (project / "agent.toml").write_text("[project]\n", encoding="utf-8")
    assert runner.invoke(app, ["status", "-c", cfg(project)]).exit_code == 1
