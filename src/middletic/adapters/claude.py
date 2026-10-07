"""Claude Code adapter: renders the IR as ``CLAUDE.md`` markdown."""

from __future__ import annotations

from middletic.adapters.markdown import MarkdownAdapter
from middletic.capabilities.matrix import native_capabilities


class ClaudeAdapter(MarkdownAdapter):
    name = "claude"
    display_name = "Claude Code"
    filename = "CLAUDE.md"
    capabilities = native_capabilities("claude")
