"""Detect raw secrets in ``agent.toml`` (values are never echoed)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ENV_REF = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
SENSITIVE_NAME = re.compile(r"(?i)(key|token|secret|passw(or)?d|credential|auth)")

TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI-style API key", re.compile(r"sk-[A-Za-z0-9_\-]{16,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("AWS access key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack token", re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("Bearer token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "credential assignment",
        re.compile(r"(?i)(?:api[_-]?key|token|secret|passw(?:or)?d)\s*[=:]\s*(?!\$\{)\S{6,}"),
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    path: str  # e.g. ``mcp.github.env.GITHUB_TOKEN``
    reason: str


def _scan_string(path: str, value: str, in_env: bool, key: str | None) -> Finding | None:
    if in_env and key and value and SENSITIVE_NAME.search(key) and not ENV_REF.match(value):
        return Finding(path, "literal value for a sensitive-looking variable; use ${ENV_VAR}")
    for label, pattern in TOKEN_PATTERNS:
        if pattern.search(value):
            return Finding(path, f"looks like a {label}; use ${{ENV_VAR}} instead")
    return None


def scan(raw: dict[str, Any]) -> list[Finding]:
    """Walk parsed TOML and report string values that look like raw secrets."""
    findings: list[Finding] = []

    def walk(node: Any, path: str, in_env: bool, key: str | None) -> None:
        if isinstance(node, dict):
            # Direct children of an ``env`` table are environment variables.
            children_are_env = key == "env"
            for child_key, child in node.items():
                child_path = f"{path}.{child_key}" if path else str(child_key)
                walk(child, child_path, children_are_env, str(child_key))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]", False, key)
        elif isinstance(node, str):
            finding = _scan_string(path, node, in_env, key)
            if finding:
                findings.append(finding)

    walk(raw, "", False, None)
    return findings
