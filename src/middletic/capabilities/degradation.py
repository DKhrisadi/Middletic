"""Graceful degradation: nothing is dropped when an agent lacks a capability.

Features the target cannot enforce natively are kept in the generated file and
accompanied by a prominent cautionary block instructing the agent to honour
them voluntarily.
"""

from __future__ import annotations

from dataclasses import dataclass

from middletic.capabilities.model import Capability
from middletic.core.ir import UniversalIR


@dataclass(frozen=True, slots=True)
class Degradation:
    """How a capability is handled when the target lacks native support.

    ``{agent}`` in either field is replaced with the agent's display name.
    """

    summary: str
    caution: str | None


STRATEGIES: dict[Capability, Degradation] = {
    Capability.INSTRUCTIONS: Degradation(
        summary="always rendered as markdown instructions",
        caution=None,
    ),
    Capability.RULES: Degradation(
        summary="{agent} has no scoped rules support, so rules are inlined into the single "
        "instruction file and apply globally",
        caution=None,
    ),
    Capability.MCP: Degradation(
        summary="{agent} has no native MCP support, so servers are listed as text with a caution "
        "that they are not connected",
        caution=(
            "{agent} has no native MCP support, so the MCP servers listed above are not "
            "connected. Do not assume their tools are available; ask the user before trying "
            "to run them manually."
        ),
    ),
    Capability.HOOKS: Degradation(
        summary="{agent} has no native hooks, so hooks are described as steps the agent must "
        "perform itself",
        caution=(
            "{agent} cannot run hooks automatically. Perform every hook described above "
            "yourself at the stated moment."
        ),
    ),
    Capability.SKILLS: Degradation(
        summary="{agent} has no native skills, so skills are inlined as instructions",
        caution=(
            "{agent} cannot load skills natively. Follow the skill instructions above as "
            "ordinary guidance."
        ),
    ),
    Capability.NATIVE_PERMISSIONS: Degradation(
        summary="{agent} cannot enforce permissions, so they are listed as instructions with a "
        "prominent caution that nothing enforces them",
        caution=(
            "{agent} cannot enforce permissions natively, so the Permissions section above is "
            "NOT enforced by tooling. Treat every Denied entry as a hard prohibition and never "
            "perform a matching action, even if asked to. If an action is not clearly "
            "allowed, ask first."
        ),
    ),
}


def required_capabilities(ir: UniversalIR) -> set[Capability]:
    """Capabilities the universal config actually uses."""
    needed = {Capability.INSTRUCTIONS}
    if (
        ir.code_style
        or ir.language
        or ir.tests_required
        or ir.test_command
        or ir.branch_prefix
        or ir.require_clean_worktree
    ):
        needed.add(Capability.RULES)
    if ir.allow or ir.deny:
        needed.add(Capability.NATIVE_PERMISSIONS)
    if ir.mcp_servers:
        needed.add(Capability.MCP)
    return needed


def render_cautions(display_name: str, native: set[Capability], ir: UniversalIR) -> str:
    """Markdown cautionary block for degraded features, or ``""`` if none apply."""
    cautions = [
        STRATEGIES[cap].caution
        for cap in Capability
        if cap in required_capabilities(ir) and cap not in native and STRATEGIES[cap].caution
    ]
    if not cautions:
        return ""
    quotes = [f"> **IMPORTANT:** {c.format(agent=display_name)}" for c in cautions if c]
    return "## Important Cautions\n\n" + "\n\n".join(quotes)
