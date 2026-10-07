"""Human-readable explanation of how universal keys map to a target."""

from __future__ import annotations

from dataclasses import dataclass

from middletic.capabilities.degradation import STRATEGIES
from middletic.capabilities.model import Capability


@dataclass(frozen=True, slots=True)
class Feature:
    keys: str
    capability: Capability
    rendering: str


FEATURES: tuple[Feature, ...] = (
    Feature("project.name, project.description", Capability.INSTRUCTIONS, "title and intro"),
    Feature("agent.role", Capability.INSTRUCTIONS, "'Role' section"),
    Feature("behavior.*", Capability.INSTRUCTIONS, "'Behavior' bullets"),
    Feature("code.style, code.language", Capability.RULES, "'Code' bullets"),
    Feature(
        "testing.required",
        Capability.RULES,
        "'Testing' bullet 'Tests are required for every change.'",
    ),
    Feature("testing.command", Capability.RULES, "'Testing' bullet naming the test command"),
    Feature("git.*", Capability.RULES, "'Git' bullets"),
    Feature("permissions.allow", Capability.NATIVE_PERMISSIONS, "'Permissions' Allowed bullets"),
    Feature("permissions.deny", Capability.NATIVE_PERMISSIONS, "'Permissions' Denied bullets"),
    Feature(
        "mcp.<server>",
        Capability.MCP,
        "'MCP Servers' bullets (command, args, env variable names only)",
    ),
)


def explain_lines(display_name: str, filename: str, native: set[Capability]) -> list[str]:
    """One line per universal key describing where it lands for this target."""
    lines: list[str] = []
    for feature in FEATURES:
        line = f"{feature.keys} [{feature.capability}]: {feature.rendering} in {filename}"
        if feature.capability in native:
            lines.append(f"{line}.")
        else:
            summary = STRATEGIES[feature.capability].summary.format(agent=display_name)
            lines.append(f"{line}; degraded: {summary}.")
    return lines
