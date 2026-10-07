"""Drift detection: compare files on disk with recorded state and expected output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from middletic.adapters.base import ManagedBlockError, split_managed_block
from middletic.core.sync import FilePlan, SyncPlan
from middletic.drift.state import State, sha256_text


class FileState(StrEnum):
    SYNCED = "SYNCED"
    MISSING = "MISSING"  # file absent, or its managed block was removed
    BLOCK_EDITED = "BLOCK_EDITED"  # manual edits inside the managed block
    STALE = "STALE"  # block untouched but differs from what the config generates
    MALFORMED = "MALFORMED"  # broken managed-block delimiters


class Overall(StrEnum):
    SYNCED = "SYNCED"
    DRIFTED = "DRIFTED"


@dataclass(frozen=True, slots=True)
class FileStatus:
    target: str
    filename: str
    state: FileState
    outside_edited: bool  # manual edits outside the block (preserved by sync)
    detail: str


@dataclass(frozen=True, slots=True)
class StatusReport:
    overall: Overall
    config_changed: bool
    never_synced: bool
    last_sync: str | None
    files: tuple[FileStatus, ...]


def _file_status(fp: FilePlan, state: State | None) -> FileStatus:
    def make(file_state: FileState, detail: str, outside: bool = False) -> FileStatus:
        return FileStatus(fp.target, fp.filename, file_state, outside, detail)

    if fp.existing is None:
        return make(FileState.MISSING, "file does not exist")

    try:
        parts = split_managed_block(fp.existing)
    except ManagedBlockError as exc:
        return make(FileState.MALFORMED, str(exc))
    if parts is None:
        return make(FileState.MISSING, "managed block was removed")

    block, outside = parts
    adapter_record = state.adapters.get(fp.target) if state else None
    record = adapter_record.files.get(fp.filename) if adapter_record else None
    outside_edited = record is not None and sha256_text(outside) != record.outside_hash
    block_hash = sha256_text(block)

    if record is not None and block_hash != record.block_hash:
        return make(
            FileState.BLOCK_EDITED,
            "manual edits inside the managed block (sync will overwrite them)",
            outside_edited,
        )
    if block_hash != sha256_text(fp.body.strip()):
        return make(FileState.STALE, "managed block differs from current config", outside_edited)
    return make(FileState.SYNCED, "up to date", outside_edited)


def compute_status(plan: SyncPlan, state: State | None) -> StatusReport:
    """Classify every enabled target file and the project as a whole."""
    files = tuple(_file_status(fp, state) for fp in plan.files)
    config_changed = state is not None and state.config_hash != plan.config_hash
    never_synced = state is None
    drifted = never_synced or config_changed or any(f.state is not FileState.SYNCED for f in files)
    return StatusReport(
        overall=Overall.DRIFTED if drifted else Overall.SYNCED,
        config_changed=config_changed,
        never_synced=never_synced,
        last_sync=state.last_sync if state else None,
        files=files,
    )
