"""Persistent sync state stored in ``.middletic/state.json``."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

STATE_DIR = ".middletic"
STATE_FILE = "state.json"


class StateError(Exception):
    """Raised when the state file exists but cannot be read."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileRecord(_Model):
    block_hash: str  # SHA-256 of the managed block body
    outside_hash: str  # SHA-256 of everything outside the block


class AdapterRecord(_Model):
    version: str
    files: dict[str, FileRecord]


class State(_Model):
    schema_version: int = 1
    last_sync: str  # ISO-8601 UTC
    config_hash: str  # SHA-256 of agent.toml bytes
    adapters: dict[str, AdapterRecord]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def state_path(root: Path) -> Path:
    return root / STATE_DIR / STATE_FILE


def load_state(root: Path) -> State | None:
    """Load state, or ``None`` if the project has never been synced."""
    path = state_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StateError(f"Cannot read {path}: {exc}") from exc
    try:
        return State.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise StateError(f"Corrupt state file {path}: {exc}") from exc


def save_state(root: Path, state: State) -> None:
    """Atomically write state (temp file + rename)."""
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(state.model_dump(), indent=2, sort_keys=True) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
