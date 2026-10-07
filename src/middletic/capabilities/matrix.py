"""The capability matrix: which agent natively supports which capability.

This is the single place to edit when an agent gains or loses a feature.
Anything not listed as native for an agent is treated as degraded.
"""

from __future__ import annotations

from collections.abc import Mapping

from middletic.capabilities.model import Capability, Support

_NATIVE: Mapping[str, frozenset[Capability]] = {
    "claude": frozenset(Capability),
    "codex": frozenset({Capability.INSTRUCTIONS, Capability.MCP, Capability.NATIVE_PERMISSIONS}),
    "gemini": frozenset({Capability.INSTRUCTIONS, Capability.MCP}),
    "cursor": frozenset({Capability.INSTRUCTIONS, Capability.RULES, Capability.MCP}),
}


def agent_names() -> list[str]:
    """Names of all agents in the matrix, in declaration order."""
    return list(_NATIVE)


def native_capabilities(agent: str) -> set[Capability]:
    """Capabilities ``agent`` supports natively."""
    return set(_NATIVE[agent])


def support_for(agent: str, capability: Capability) -> Support:
    """Support level of ``capability`` for ``agent``."""
    return Support.NATIVE if capability in _NATIVE[agent] else Support.DEGRADED
