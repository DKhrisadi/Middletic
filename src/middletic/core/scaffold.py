"""Generating an initial ``agent.toml`` for ``agent init``."""

from __future__ import annotations

from typing import Any

import tomli_w

from middletic.adapters.registry import ADAPTERS
from middletic.core.loader import parse_config


def parse_targets(raw: str) -> list[str]:
    """Parse a comma-separated target list; raises ``ValueError`` if invalid."""
    targets = [t.strip().lower() for t in raw.split(",") if t.strip()]
    if not targets:
        raise ValueError("choose at least one target")
    unknown = [t for t in targets if t not in ADAPTERS]
    if unknown:
        raise ValueError(
            f"unknown target(s): {', '.join(unknown)}. Available: {', '.join(ADAPTERS)}"
        )
    return list(dict.fromkeys(targets))


def render_initial_config(name: str, language: str, test_command: str, targets: list[str]) -> str:
    """Build, validate, and serialise a starter ``agent.toml``.

    Raises ``ConfigError`` if the answers do not form a valid config.
    """
    data: dict[str, Any] = {"project": {"name": name.strip()}}
    if language.strip():
        data["code"] = {"language": language.strip()}
    if test_command.strip():
        data["testing"] = {"required": True, "command": test_command.strip()}
    data["targets"] = {"enabled": targets}
    text = tomli_w.dumps(data)
    parse_config(text)  # guarantees the generated file validates
    return text
