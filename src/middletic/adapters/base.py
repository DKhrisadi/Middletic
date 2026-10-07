"""Adapter contract and the safe managed-block merge algorithm."""

from __future__ import annotations

from abc import ABC, abstractmethod

from middletic.capabilities.model import Capability
from middletic.core.ir import UniversalIR

MANAGED_START = "<!-- middletic:start -->"
MANAGED_END = "<!-- middletic:end -->"


class ManagedBlockError(ValueError):
    """Raised when existing content has a malformed managed block."""


def find_managed_block(content: str) -> tuple[int, int] | None:
    """Locate the managed block as ``(start, end)`` offsets, end being exclusive.

    Returns ``None`` when the content has no delimiters at all. Raises
    ``ManagedBlockError`` for unbalanced, misordered, or duplicated delimiters.
    """
    starts = content.count(MANAGED_START)
    ends = content.count(MANAGED_END)
    if starts == 0 and ends == 0:
        return None
    if starts != 1 or ends != 1:
        raise ManagedBlockError(
            f"Expected exactly one managed block, found {starts} start and {ends} end markers"
        )
    start_idx = content.index(MANAGED_START)
    end_idx = content.index(MANAGED_END)
    if end_idx < start_idx:
        raise ManagedBlockError("Managed block end marker appears before start marker")
    return start_idx, end_idx + len(MANAGED_END)


def split_managed_block(content: str) -> tuple[str, str] | None:
    """Split into ``(block_body, outside)``; ``None`` if there is no block.

    ``block_body`` is the stripped text between the delimiters; ``outside`` is
    everything else (before + after) concatenated.
    """
    span = find_managed_block(content)
    if span is None:
        return None
    start, end = span
    body = content[start + len(MANAGED_START) : end - len(MANAGED_END)].strip()
    return body, content[:start] + content[end:]


class AgentAdapter(ABC):
    """Translates the universal IR into files for one target agent."""

    name: str
    display_name: str
    filename: str  # primary generated file, relative to the project root
    capabilities: set[Capability]  # natively supported capabilities
    version: str = "1"  # bump when generated output changes for the same IR

    @abstractmethod
    def generate(self, ir: UniversalIR) -> dict[str, str]:
        """Return ``{filename: managed_body}``.

        Bodies exclude the delimiters; ``inject_managed_block`` adds them.
        """

    def create_file(self, ir: UniversalIR, filename: str, body: str) -> str:
        """Content for a file that does not exist yet. Override to add a preamble."""
        return self.inject_managed_block("", body)

    def merge(self, ir: UniversalIR, filename: str, body: str, existing: str) -> str:
        """Final file content given the generated body and any existing content."""
        if not existing.strip():
            return self.create_file(ir, filename, body)
        return self.inject_managed_block(existing, body)

    def inject_managed_block(self, existing_content: str, new_content: str) -> str:
        """Insert or replace the managed block, preserving all other content.

        - Empty ``existing_content``: the file becomes just the block.
        - No block present: the block is appended after the existing content.
        - Block present: only the text between the delimiters is replaced.

        Raises ``ManagedBlockError`` for unbalanced, misordered, or duplicated
        delimiters, rather than risk overwriting hand-written content.
        """
        if MANAGED_START in new_content or MANAGED_END in new_content:
            raise ManagedBlockError("Generated content must not contain managed block delimiters")

        block = f"{MANAGED_START}\n{new_content.strip()}\n{MANAGED_END}"

        if not existing_content.strip():
            return block + "\n"

        span = find_managed_block(existing_content)
        if span is None:
            return existing_content.rstrip("\n") + "\n\n" + block + "\n"

        start, end = span
        return existing_content[:start] + block + existing_content[end:]
