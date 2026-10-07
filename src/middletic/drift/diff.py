"""Non-destructive unified diffs of what a sync would change."""

from __future__ import annotations

import difflib
from typing import TypedDict

from middletic.core.sync import FilePlan, SyncPlan


class DiffEntry(TypedDict):
    target: str
    file: str
    action: str
    diff: str


def unified_diff(fp: FilePlan) -> str:
    """Unified diff for one file; empty string when unchanged."""
    if fp.action == "unchanged":
        return ""
    old = (fp.existing or "").splitlines(keepends=True)
    new = fp.updated.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old,
            new,
            fromfile="/dev/null" if fp.existing is None else f"a/{fp.filename}",
            tofile=f"b/{fp.filename}",
        )
    )


def diff_entries(plan: SyncPlan) -> list[DiffEntry]:
    return [
        DiffEntry(target=fp.target, file=fp.filename, action=fp.action, diff=unified_diff(fp))
        for fp in plan.files
    ]
