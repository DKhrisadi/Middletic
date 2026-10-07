"""Cursor adapter: renders the IR as ``.cursor/rules/agent.mdc``."""

from __future__ import annotations

import json

from middletic.adapters.markdown import MarkdownAdapter
from middletic.capabilities.matrix import native_capabilities
from middletic.core.ir import UniversalIR


class CursorAdapter(MarkdownAdapter):
    name = "cursor"
    display_name = "Cursor"
    filename = ".cursor/rules/agent.mdc"
    capabilities = native_capabilities("cursor")

    def create_file(self, ir: UniversalIR, filename: str, body: str) -> str:
        """Prefix new files with Cursor's YAML frontmatter.

        The frontmatter lives outside the managed block, so users may edit it
        (e.g. to add ``globs``) and later syncs will leave it alone.
        """
        description = json.dumps(
            f"Middletic-managed project rules for {ir.project_name}", ensure_ascii=False
        )
        frontmatter = f"---\ndescription: {description}\nalwaysApply: true\n---\n\n"
        return frontmatter + super().create_file(ir, filename, body)
