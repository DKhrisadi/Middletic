"""Universal Intermediate Representation (IR).

The IR is plain, immutable data that adapters consume. It deliberately does not
import or expose the Pydantic schema, so adapters never depend on the raw TOML
layout and the file format can evolve independently of target agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from middletic.schema.config import MiddleticFile


@dataclass(frozen=True, slots=True)
class McpServerIR:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env_keys: tuple[str, ...] = ()  # names only; values may be secrets


@dataclass(frozen=True, slots=True)
class UniversalIR:
    project_name: str
    project_description: str = ""
    role: str = ""
    tone: str = ""
    explain_changes: bool = True
    confirm_destructive_actions: bool = True
    code_style: str = ""
    language: str = ""
    tests_required: bool = False
    test_command: str = ""
    branch_prefix: str = ""
    require_clean_worktree: bool = False
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    mcp_servers: tuple[McpServerIR, ...] = field(default_factory=tuple)


def build_ir(config: MiddleticFile) -> UniversalIR:
    """Lower a validated ``agent.toml`` model into the universal IR."""
    return UniversalIR(
        project_name=config.project.name,
        project_description=config.project.description.strip(),
        role=config.agent.role.strip(),
        tone=config.behavior.tone.strip(),
        explain_changes=config.behavior.explain_changes,
        confirm_destructive_actions=config.behavior.ask_before_destructive_actions,
        code_style=config.code.style.strip(),
        language=config.code.language.strip(),
        tests_required=config.testing.required,
        test_command=config.testing.command.strip(),
        branch_prefix=config.git.branch_prefix.strip(),
        require_clean_worktree=config.git.require_clean_worktree,
        allow=tuple(config.permissions.allow),
        deny=tuple(config.permissions.deny),
        mcp_servers=tuple(
            McpServerIR(
                name=name,
                command=server.command,
                args=tuple(server.args),
                env_keys=tuple(sorted(server.env)),
            )
            for name, server in sorted(config.mcp.items())
        ),
    )
