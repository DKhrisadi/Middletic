# Contributing to middletic

Thanks for helping! This guide covers setup, the checks CI runs, and how to add support for a new coding agent.

## Development setup

```bash
git clone https://github.com/DKhrisadi/Middletic && cd middletic
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Before opening a PR, run what CI runs:

```bash
ruff check . && ruff format --check . && mypy && pytest
```

## Architecture in one minute

```
agent.toml ──► schema/config.py ──► core/ir.py (UniversalIR) ──► adapters/*.py ──► files
                                                    ▲
                                  capabilities/ (matrix + graceful degradation)
```

- **Schema** (`schema/config.py`): strict Pydantic models; unknown keys are rejected.
- **IR** (`core/ir.py`): plain frozen dataclasses. Adapters only ever see the IR, never raw TOML.
- **Adapters** (`adapters/`): turn the IR into one agent's files.
- **Capabilities** (`capabilities/`): which agent supports what natively, and the caution text added when it doesn't.

## Adding a new adapter

We'll use a hypothetical Windsurf adapter that writes `.windsurfrules`.

### 1. Declare its native capabilities

In [`capabilities/matrix.py`](src/middletic/capabilities/matrix.py), add the agent and the capabilities it supports **natively**. Anything not listed degrades automatically (kept in the file, with a caution block).

```python
_NATIVE = {
    ...
    "windsurf": frozenset({Capability.INSTRUCTIONS, Capability.RULES, Capability.MCP}),
}
```

Only claim `NATIVE` for something the agent genuinely enforces or understands; link its docs in your PR.

### 2. Write the adapter

Most agents just read a markdown file, so subclass `MarkdownAdapter`, which already renders the sections and degradation cautions:

```python
# src/middletic/adapters/windsurf.py
from middletic.adapters.markdown import MarkdownAdapter
from middletic.capabilities.matrix import native_capabilities


class WindsurfAdapter(MarkdownAdapter):
    name = "windsurf"  # the value users put in [targets] enabled
    display_name = "Windsurf"  # used in caution text
    filename = ".windsurfrules"  # path relative to the project root
    capabilities = native_capabilities("windsurf")
```

If the agent needs a preamble in *new* files (as Cursor's YAML frontmatter), override `create_file(ir, filename, body)`; see [`cursor.py`](src/middletic/adapters/cursor.py).

For a non-markdown format, subclass [`AgentAdapter`](src/middletic/adapters/base.py) directly and implement:

| Member | Contract |
| --- | --- |
| `name`, `display_name`, `filename` | Identity and the primary output path. |
| `capabilities: set[Capability]` | Native capabilities (use `native_capabilities(name)`). |
| `generate(ir) -> dict[str, str]` | `{filename: managed_body}`. The body must **not** contain the managed-block delimiters. |
| `version: str` | Bump when output changes for the same IR, so `agent status` can spot stale files. |

You normally don't override `inject_managed_block` or `merge`; they implement the safe merge that preserves hand-written content outside `<!-- middletic:start -->` / `<!-- middletic:end -->`. Adapters must be deterministic: same IR in, same bytes out.

### 3. Register it

In [`adapters/registry.py`](src/middletic/adapters/registry.py), add an instance to `ADAPTERS`, and add the name to the `TargetName` literal in [`schema/config.py`](src/middletic/schema/config.py) so `[targets] enabled` accepts it.

### 4. Test it

1. Add the name to `GOLDEN_NAMES` in [`tests/test_golden.py`](tests/test_golden.py) (`"windsurf": "windsurf.rules"`).
2. Generate and **review** the golden file: `UPDATE_GOLDEN=1 pytest tests/test_golden.py`.
3. Existing tests already assert that the matrix, registry and golden set agree, and they fail if you forget a step.

### 5. Document it

Add a row to the capability matrix and the target list in `README.md`, then confirm `agent adapters` and `agent explain windsurf` look right.

## Other changes

- **New `agent.toml` option:** add it to the schema, the IR, the renderer, and the `FEATURES` table in `capabilities/explain.py`; update goldens and the README reference.
- **Output changes:** regenerate goldens and the files under `examples/` (`agent sync` inside each example). `tests/test_examples.py` fails when they're stale.
- **Demo image:** `python scripts/make_demo.py` regenerates `docs/demo.svg`.

## Commit and PR style

Small, focused PRs with tests. Describe the *why*. Fill in the PR template checklist.
