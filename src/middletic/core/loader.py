"""Reading and validating ``agent.toml`` from disk."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import ValidationError

from middletic.schema.config import MiddleticFile


class ConfigError(Exception):
    """Raised when ``agent.toml`` is missing, unparsable, or invalid."""

    def __init__(self, message: str, problems: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.problems = problems


def parse_config(text: str) -> MiddleticFile:
    """Parse and validate TOML text."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML: {exc}") from exc
    try:
        return MiddleticFile.model_validate(raw)
    except ValidationError as exc:
        problems = tuple(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigError("agent.toml failed validation", problems) from exc


def load_config(path: Path) -> MiddleticFile:
    """Read, parse, and validate the config file at ``path``."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    return parse_config(text)
