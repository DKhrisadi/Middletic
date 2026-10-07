"""Registry of available target adapters."""

from __future__ import annotations

from middletic.adapters.base import AgentAdapter
from middletic.adapters.claude import ClaudeAdapter
from middletic.adapters.codex import CodexAdapter
from middletic.adapters.cursor import CursorAdapter
from middletic.adapters.gemini import GeminiAdapter

ADAPTERS: dict[str, AgentAdapter] = {
    adapter.name: adapter
    for adapter in (ClaudeAdapter(), CodexAdapter(), GeminiAdapter(), CursorAdapter())
}


def get_adapter(name: str) -> AgentAdapter:
    """Look up an adapter by name; raises ``KeyError`` listing valid names."""
    try:
        return ADAPTERS[name]
    except KeyError:
        raise KeyError(f"Unknown adapter '{name}'. Available: {', '.join(ADAPTERS)}") from None
