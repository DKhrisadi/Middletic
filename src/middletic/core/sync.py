"""Planning and applying a sync, shared by sync/diff/status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from middletic.adapters.base import AgentAdapter, ManagedBlockError, split_managed_block
from middletic.adapters.registry import get_adapter
from middletic.core.ir import build_ir
from middletic.core.loader import ConfigError, parse_config
from middletic.drift.state import (
    AdapterRecord,
    FileRecord,
    State,
    load_state,
    save_state,
    sha256_bytes,
    sha256_text,
)


@dataclass(frozen=True, slots=True)
class FilePlan:
    target: str
    adapter: AgentAdapter
    filename: str
    path: Path
    body: str  # generated managed body (no delimiters)
    existing: str | None  # None when the file does not exist
    updated: str  # full file content after sync

    @property
    def action(self) -> str:
        if self.existing is None:
            return "created"
        return "unchanged" if self.existing == self.updated else "updated"


@dataclass(frozen=True, slots=True)
class SyncPlan:
    root: Path
    config_hash: str
    files: tuple[FilePlan, ...]


def plan_sync(config_path: Path) -> SyncPlan:
    """Compute what a sync would write, without touching the disk.

    Raises ``ConfigError`` for a missing/invalid config and
    ``ManagedBlockError`` if an existing file has a malformed managed block.
    """
    try:
        data = config_path.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {config_path}: {exc}") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid UTF-8") from exc

    config = parse_config(text)
    ir = build_ir(config)
    root = config_path.resolve().parent

    plans: list[FilePlan] = []
    for target_name in config.targets.enabled:
        adapter = get_adapter(target_name)
        for filename, body in adapter.generate(ir).items():
            path = root / filename
            existing = path.read_text(encoding="utf-8") if path.exists() else None
            try:
                updated = adapter.merge(ir, filename, body, existing or "")
            except ManagedBlockError as exc:
                raise ManagedBlockError(f"{filename}: {exc}") from exc
            plans.append(FilePlan(target_name, adapter, filename, path, body, existing, updated))
    return SyncPlan(root=root, config_hash=sha256_bytes(data), files=tuple(plans))


def build_state(plan: SyncPlan, last_sync: str) -> State:
    """State describing the files as they are after ``plan`` is applied."""
    adapters: dict[str, dict[str, FileRecord]] = {}
    versions: dict[str, str] = {}
    for fp in plan.files:
        parts = split_managed_block(fp.updated)
        if parts is None:  # pragma: no cover - merge always yields a block
            raise ManagedBlockError(f"{fp.filename}: generated content has no managed block")
        block, outside = parts
        adapters.setdefault(fp.target, {})[fp.filename] = FileRecord(
            block_hash=sha256_text(block), outside_hash=sha256_text(outside)
        )
        versions[fp.target] = fp.adapter.version
    return State(
        last_sync=last_sync,
        config_hash=plan.config_hash,
        adapters={
            name: AdapterRecord(version=versions[name], files=files)
            for name, files in adapters.items()
        },
    )


def apply_sync(plan: SyncPlan, now: datetime | None = None) -> State:
    """Write changed files and persist state. Returns the saved state.

    ``last_sync`` advances whenever a file is created, updated or reconciled from
    drift; a true no-op (every file already matches) leaves ``state.json``
    byte-identical.
    """
    changed = False
    for fp in plan.files:
        if fp.action != "unchanged":
            changed = True
            fp.path.parent.mkdir(parents=True, exist_ok=True)
            fp.path.write_text(fp.updated, encoding="utf-8")

    stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
    previous = load_state(plan.root)
    state = build_state(plan, stamp)
    if (
        not changed
        and previous is not None
        and previous.model_copy(update={"last_sync": stamp}) == state
    ):
        return previous
    save_state(plan.root, state)
    return state
