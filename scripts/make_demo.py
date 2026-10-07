#!/usr/bin/env python3
"""Record a real ``agent`` session and render it as an animated SVG.

Runs ``agent init`` / ``agent sync`` / ``agent status`` in a throwaway
directory, captures their actual output, and writes ``docs/demo.svg``.
Standard library only; requires the ``agent`` command to be installed.

    python scripts/make_demo.py [-o docs/demo.svg]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

COMMANDS: list[list[str]] = [
    [
        "agent",
        "init",
        "--non-interactive",
        "--name",
        "demo",
        "--targets",
        "claude,codex,gemini,cursor",
    ],
    ["agent", "sync"],
    ["agent", "status"],
]

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
BG, FG = "#0d1117", "#c9d1d9"
GREEN, YELLOW, CYAN, DIM = "#3fb950", "#d29922", "#58a6ff", "#8b949e"
CHAR_W, LINE_H, PAD_X, TOP = 8.43, 22, 24, 52
STEP = 0.35  # seconds between lines appearing
GREEN_WORDS = re.compile(r"\b(created|updated|up to date|SYNCED|valid)\b")
YELLOW_WORDS = re.compile(r"\b(DRIFTED|MISSING|BLOCK_EDITED|STALE)\b")

Line = tuple[str, str]  # (text, color)


def find_agent() -> str:
    sibling = Path(sys.executable).parent / "agent"
    found = str(sibling) if sibling.exists() else shutil.which("agent")
    if not found:
        sys.exit("error: `agent` not found; run `pip install -e .` first")
    return found


def record() -> list[Line]:
    """Run the commands for real and return colourised transcript lines."""
    agent = find_agent()
    lines: list[Line] = []
    with tempfile.TemporaryDirectory(prefix="middletic-demo-") as tmp:
        for command in COMMANDS:
            shown = " ".join(command[:2] if command[1] == "init" else command)
            shown = shown + " ..." if command[1] == "init" else shown
            lines.append((f"$ {shown}", CYAN))
            result = subprocess.run(
                [agent, *command[1:]], cwd=tmp, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                sys.exit(f"error: `{shown}` exited {result.returncode}:\n{result.stderr}")
            lines.extend((out, FG) for out in result.stdout.splitlines())
            lines.append(("", FG))
    return lines[:-1]


def tspans(text: str, base: str) -> str:
    """Escape ``text`` and wrap status words in coloured spans."""
    out: list[str] = []
    pos = 0
    matches = sorted(
        [(m.start(), m.end(), GREEN) for m in GREEN_WORDS.finditer(text)]
        + [(m.start(), m.end(), YELLOW) for m in YELLOW_WORDS.finditer(text)]
    )
    for start, end, color in matches:
        out.append(escape(text[pos:start]))
        out.append(f'<tspan fill="{color}">{escape(text[start:end])}</tspan>')
        pos = end
    out.append(escape(text[pos:]))
    return "".join(out)


def render_svg(lines: list[Line]) -> str:
    width = int(max(len(t) for t, _ in lines) * CHAR_W + PAD_X * 2)
    width = max(width, 520)
    height = TOP + len(lines) * LINE_H + 20
    rows: list[str] = []
    for i, (text, color) in enumerate(lines):
        if not text:
            continue
        y = TOP + i * LINE_H
        rows.append(
            f'<text x="{PAD_X}" y="{y}" fill="{color}" class="l" '
            f'style="animation-delay:{i * STEP:.2f}s" xml:space="preserve">'
            f"{tspans(text, color)}</text>"
        )
    body = "\n  ".join(rows)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" role="img" aria-label="agent sync terminal demo">
  <style>
    text {{ font-family: {FONT}; font-size: 14px; }}
    .l {{ opacity: 0; animation: show 0.01s forwards; }}
    @keyframes show {{ to {{ opacity: 1; }} }}
  </style>
  <rect width="{width}" height="{height}" rx="10" fill="{BG}"/>
  <rect width="{width}" height="32" rx="10" fill="#161b22"/>
  <rect y="22" width="{width}" height="10" fill="#161b22"/>
  <circle cx="20" cy="16" r="6" fill="#ff5f56"/>
  <circle cx="40" cy="16" r="6" fill="#ffbd2e"/>
  <circle cx="60" cy="16" r="6" fill="#27c93f"/>
  <text x="{width // 2}" y="21" fill="{DIM}" text-anchor="middle" \
style="font-size:12px">agent sync</text>
  {body}
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("-o", "--output", type=Path, default=Path("docs/demo.svg"))
    args = parser.parse_args()
    svg = render_svg(record())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
