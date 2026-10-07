"""``agent doctor``: repository diagnostics."""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from middletic.adapters.base import ManagedBlockError
from middletic.capabilities.matrix import native_capabilities
from middletic.capabilities.model import Capability
from middletic.core.loader import ConfigError, parse_config
from middletic.core.sync import plan_sync
from middletic.doctor.secrets import scan
from middletic.drift.state import STATE_DIR
from middletic.schema.config import MiddleticFile


class Level(StrEnum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    level: Level
    message: str


BROAD_ALLOW = re.compile(r"^(\*+|all|any|everything|\w+\(\*+\))$", re.IGNORECASE)
DANGEROUS_ALLOW = re.compile(
    r"(\brm\s+-\w*r\w*f|\bsudo\b|git\s+push\s+.*--force|\bchmod\s+(-R\s+)?777\b|\|\s*(ba)?sh\b"
    r"|\bmkfs\b|\bdd\s+if=)",
    re.IGNORECASE,
)


def check_schema(text: str) -> tuple[Check, MiddleticFile | None]:
    try:
        config = parse_config(text)
    except ConfigError as exc:
        detail = "; ".join(exc.problems) if exc.problems else str(exc)
        return Check("schema", Level.ERROR, f"agent.toml is invalid: {detail}"), None
    return Check("schema", Level.OK, "agent.toml is valid"), config


def check_secrets(text: str) -> list[Check]:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []  # already reported by the schema check
    findings = scan(raw)
    if not findings:
        return [Check("secrets", Level.OK, "no raw secrets detected")]
    return [Check("secrets", Level.WARN, f"{f.path}: {f.reason} (value hidden)") for f in findings]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=15, check=False
    )


def _dirty_paths(root: Path) -> list[str] | None:
    """Absolute paths with uncommitted changes (``None`` if git status failed)."""
    top = _git(root, "rev-parse", "--show-toplevel")
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if top.returncode != 0 or status.returncode != 0:
        return None
    toplevel = Path(top.stdout.strip())
    paths: list[str] = []
    fields = iter(status.stdout.split("\0"))
    for field in fields:
        if len(field) < 4:
            continue
        code, rel = field[:2], field[3:]
        if code[0] in "RC":
            next(fields, None)  # skip the original path of a rename/copy
        paths.append(f"{code}\0{(toplevel / rel).resolve()}")
    return paths


def _own_files(root: Path, config_path: Path) -> set[Path]:
    """Files Middletic itself generates for this project."""
    try:
        return {fp.path.resolve() for fp in plan_sync(config_path).files}
    except (ConfigError, ManagedBlockError):
        return set()


def check_git(root: Path, require_clean: bool, config_path: Path | None = None) -> list[Check]:
    try:
        probe = _git(root, "rev-parse", "--is-inside-work-tree")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [Check("git", Level.WARN, "git is not available")]
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return [Check("git", Level.WARN, "not inside a git repository")]
    checks = [Check("git", Level.OK, "inside a git repository")]
    try:
        entries = _dirty_paths(root)
    except subprocess.TimeoutExpired:
        return [*checks, Check("git-clean", Level.WARN, "git status timed out")]
    if entries is None:
        return [*checks, Check("git-clean", Level.WARN, "could not read git status")]

    # Ignore Middletic's own output: generated target files, the state dir, and a
    # freshly created (untracked) config file.
    state_dir = (root / STATE_DIR).resolve()
    own = _own_files(root, config_path) if config_path else set()
    config_resolved = config_path.resolve() if config_path else None
    foreign = []
    for entry in entries:
        code, raw = entry.split("\0", 1)
        path = Path(raw)
        if path in own or state_dir in path.parents:
            continue
        if path == config_resolved and code == "??":
            continue
        foreign.append(path)
    if foreign:
        level = Level.ERROR if require_clean else Level.WARN
        suffix = " (git.require_clean_worktree is set)" if require_clean else ""
        return [*checks, Check("git-clean", level, f"working tree has uncommitted changes{suffix}")]
    return [*checks, Check("git-clean", Level.OK, "working tree is clean")]


def check_permissions(config: MiddleticFile) -> list[Check]:
    allow, deny = config.permissions.allow, config.permissions.deny
    issues: list[Check] = []

    for entry in allow:
        if BROAD_ALLOW.match(entry.strip()):
            issues.append(
                Check("permissions", Level.WARN, f"allow entry '{entry}' is overly broad")
            )
        elif DANGEROUS_ALLOW.search(entry):
            issues.append(Check("permissions", Level.WARN, f"allow entry '{entry}' is dangerous"))
        for blocked in deny:
            if blocked.lower() in entry.lower():
                issues.append(
                    Check(
                        "permissions",
                        Level.WARN,
                        f"allow entry '{entry}' conflicts with deny '{blocked}'",
                    )
                )
    if allow and not deny:
        issues.append(Check("permissions", Level.WARN, "allow rules are set but nothing is denied"))
    if not config.behavior.ask_before_destructive_actions and not deny:
        issues.append(
            Check(
                "permissions",
                Level.WARN,
                "no deny rules and ask_before_destructive_actions is false: no guard rails",
            )
        )
    if allow or deny:
        for target in config.targets.enabled:
            if Capability.NATIVE_PERMISSIONS not in native_capabilities(target):
                issues.append(
                    Check(
                        "permissions",
                        Level.WARN,
                        f"{target} cannot enforce permissions natively; they are advisory only",
                    )
                )
    return issues or [Check("permissions", Level.OK, "permission boundaries look sane")]


def run_doctor(config_path: Path) -> list[Check]:
    """Run every diagnostic; never raises for user-config problems."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError) as exc:
        return [Check("schema", Level.ERROR, f"cannot read {config_path}: {exc}")]

    schema_check, config = check_schema(text)
    checks = [schema_check, *check_secrets(text)]
    root = config_path.resolve().parent
    checks.extend(
        check_git(root, config.git.require_clean_worktree if config else False, config_path)
    )
    if config is not None:
        checks.extend(check_permissions(config))
    return checks
