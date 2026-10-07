"""Gemini CLI adapter: renders the IR as ``GEMINI.md``."""

from __future__ import annotations

from middletic.adapters.markdown import MarkdownAdapter
from middletic.capabilities.matrix import native_capabilities


class GeminiAdapter(MarkdownAdapter):
    name = "gemini"
    display_name = "Gemini CLI"
    filename = "GEMINI.md"
    capabilities = native_capabilities("gemini")
