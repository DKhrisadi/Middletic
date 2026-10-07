"""Vocabulary shared by adapters, the capability matrix, and the CLI."""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    """Features a target agent may or may not support natively."""

    INSTRUCTIONS = "instructions"
    RULES = "rules"
    MCP = "mcp"
    HOOKS = "hooks"
    SKILLS = "skills"
    NATIVE_PERMISSIONS = "native_permissions"


class Support(StrEnum):
    """How an agent handles a capability."""

    NATIVE = "native"
    DEGRADED = "degraded"
