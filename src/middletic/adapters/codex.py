"""Codex adapter: renders the IR as ``AGENTS.md``."""

from __future__ import annotations

from middletic.adapters.markdown import MarkdownAdapter
from middletic.capabilities.matrix import native_capabilities


class CodexAdapter(MarkdownAdapter):
    name = "codex"
    display_name = "Codex"
    filename = "AGENTS.md"
    capabilities = native_capabilities("codex")
