"""Strict Pydantic models describing the ``agent.toml`` file format."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    """Base model: unknown keys are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectConfig(_Strict):
    name: str = Field(min_length=1)
    description: str = ""


class AgentSection(_Strict):
    role: str = ""


class BehaviorConfig(_Strict):
    tone: str = ""
    explain_changes: bool = True
    ask_before_destructive_actions: bool = True


class CodeConfig(_Strict):
    style: str = ""
    language: str = ""


class TestingConfig(_Strict):
    # Not a pytest test class despite the name.
    __test__ = False

    required: bool = False
    command: str = ""

    @model_validator(mode="after")
    def _command_needed_when_required(self) -> Self:
        if self.required and not self.command.strip():
            raise ValueError("'command' must be set when 'required' is true")
        return self


class GitConfig(_Strict):
    branch_prefix: str = ""
    require_clean_worktree: bool = False


class PermissionsConfig(_Strict):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)

    @field_validator("allow", "deny")
    @classmethod
    def _no_blank_entries(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("entries must be non-empty strings")
        return value

    @model_validator(mode="after")
    def _no_overlap(self) -> Self:
        overlap = sorted(set(self.allow) & set(self.deny))
        if overlap:
            raise ValueError(f"entries cannot be both allowed and denied: {', '.join(overlap)}")
        return self


class McpServerConfig(_Strict):
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


TargetName = Literal["claude", "codex", "gemini", "cursor"]


def _default_targets() -> list[TargetName]:
    return ["claude"]


class TargetsConfig(_Strict):
    enabled: list[TargetName] = Field(default_factory=_default_targets)

    @field_validator("enabled")
    @classmethod
    def _non_empty_unique(cls, value: list[TargetName]) -> list[TargetName]:
        if not value:
            raise ValueError("at least one target must be enabled")
        if len(set(value)) != len(value):
            raise ValueError("targets must be unique")
        return value


class MiddleticFile(_Strict):
    """Root model of ``agent.toml``."""

    project: ProjectConfig
    agent: AgentSection = Field(default_factory=AgentSection)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    code: CodeConfig = Field(default_factory=CodeConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    targets: TargetsConfig = Field(default_factory=TargetsConfig)
    mcp: dict[str, McpServerConfig] = Field(default_factory=dict)
