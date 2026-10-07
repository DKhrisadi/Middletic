"""``agent`` command-line interface."""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from middletic.adapters.base import ManagedBlockError
from middletic.adapters.registry import ADAPTERS, get_adapter
from middletic.capabilities.explain import explain_lines
from middletic.capabilities.matrix import support_for
from middletic.capabilities.model import Capability, Support
from middletic.core.loader import ConfigError, load_config
from middletic.core.scaffold import parse_targets, render_initial_config
from middletic.core.sync import SyncPlan, apply_sync, plan_sync
from middletic.doctor.checks import Level, run_doctor
from middletic.drift.diff import diff_entries
from middletic.drift.state import StateError, load_state
from middletic.drift.status import FileState, Overall, compute_status


def _package_version() -> str:
    try:
        return metadata.version("middletic")
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"Middletic v{_package_version()}")
        raise typer.Exit()


app = typer.Typer(
    name="agent",
    help="One configuration for every AI coding agent.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show the version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """One configuration for every AI coding agent."""


ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="Path to agent.toml.", dir_okay=False),
]


def _fail(message: str, problems: tuple[str, ...] = ()) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    for problem in problems:
        typer.secho(f"  - {problem}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _plan(config: Path) -> SyncPlan:
    try:
        return plan_sync(config)
    except ConfigError as exc:
        raise _fail(str(exc), exc.problems) from exc
    except ManagedBlockError as exc:
        raise _fail(str(exc)) from exc


@app.command()
def validate(config: ConfigOption = Path("agent.toml")) -> None:
    """Check agent.toml against the schema."""
    try:
        load_config(config)
    except ConfigError as exc:
        raise _fail(str(exc), exc.problems) from exc
    typer.secho(f"{config} is valid.", fg=typer.colors.GREEN)


@app.command()
def sync(
    config: ConfigOption = Path("agent.toml"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would change without writing.")
    ] = False,
) -> None:
    """Generate or update files for every target enabled in agent.toml."""
    plan = _plan(config)
    try:
        report = compute_status(plan, load_state(plan.root))
    except StateError as exc:
        raise _fail(str(exc)) from exc
    for f in report.files:
        if f.state is FileState.BLOCK_EDITED:
            verb = "Would replace" if dry_run else "Replaced"
            typer.secho(
                f"⚠ {verb} manual edits inside managed block in {f.filename}",
                fg=typer.colors.YELLOW,
                bold=True,
            )
    for fp in plan.files:
        if fp.action == "unchanged":
            typer.echo(f"{fp.filename}: up to date")
        elif dry_run:
            typer.echo(f"{fp.filename}: would be {fp.action}")
        else:
            typer.echo(f"{fp.filename}: {fp.action}")
    if not dry_run:
        apply_sync(plan)


@app.command()
def diff(
    config: ConfigOption = Path("agent.toml"),
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Show unified diffs of what sync would change, without writing anything."""
    entries = diff_entries(_plan(config))
    if as_json:
        typer.echo(json.dumps(entries, indent=2))
        return
    changed = [e for e in entries if e["diff"]]
    if not changed:
        typer.echo("No changes.")
        return
    for entry in changed:
        for line in entry["diff"].splitlines():
            color = None
            if line.startswith("+") and not line.startswith("+++"):
                color = typer.colors.GREEN
            elif line.startswith("-") and not line.startswith("---"):
                color = typer.colors.RED
            typer.secho(line, fg=color)


@app.command()
def status(config: ConfigOption = Path("agent.toml")) -> None:
    """Compare files on disk with the last sync. Exits 1 when drifted."""
    plan = _plan(config)
    try:
        state = load_state(plan.root)
    except StateError as exc:
        raise _fail(str(exc)) from exc
    report = compute_status(plan, state)

    synced = report.overall is Overall.SYNCED
    typer.secho(
        f"Status: {report.overall}", fg=typer.colors.GREEN if synced else typer.colors.YELLOW
    )
    if report.never_synced:
        typer.echo("No previous sync recorded (run `agent sync`).")
    else:
        typer.echo(f"Last sync: {report.last_sync}")
        typer.echo(f"Config modified since last sync: {'yes' if report.config_changed else 'no'}")
    for f in report.files:
        ok = f.state is FileState.SYNCED
        typer.secho(
            f"  {f.filename}: {f.state} - {f.detail}",
            fg=typer.colors.GREEN if ok else typer.colors.YELLOW,
        )
        if f.outside_edited:
            typer.echo("    manual edits outside the managed block (preserved by sync)")
    if not synced:
        raise typer.Exit(code=1)


@app.command()
def doctor(config: ConfigOption = Path("agent.toml")) -> None:
    """Run repository diagnostics. Exits 1 if any check fails."""
    checks = run_doctor(config)
    colors = {Level.OK: typer.colors.GREEN, Level.WARN: typer.colors.YELLOW}
    for check in checks:
        typer.secho(
            f"[{check.level.value:<5}] {check.name}: {check.message}",
            fg=colors.get(check.level, typer.colors.RED),
        )
    if any(c.level is Level.ERROR for c in checks):
        raise typer.Exit(code=1)


@app.command()
def init(
    config: ConfigOption = Path("agent.toml"),
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Use options/defaults, never prompt.")
    ] = False,
    name: Annotated[str | None, typer.Option(help="Project name.")] = None,
    language: Annotated[str | None, typer.Option(help="Primary language.")] = None,
    test_command: Annotated[str | None, typer.Option(help="Command that runs tests.")] = None,
    targets: Annotated[
        str | None, typer.Option(help="Comma-separated targets, e.g. claude,cursor.")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Create an initial agent.toml."""
    if config.exists() and not force:
        raise _fail(f"{config} already exists (use --force to overwrite)")

    default_name = config.resolve().parent.name
    if non_interactive:
        name = name if name is not None else default_name
        language = language or ""
        test_command = test_command or ""
        try:
            target_list = parse_targets(targets if targets is not None else "claude")
        except ValueError as exc:
            raise _fail(str(exc)) from exc
    else:
        name = name if name is not None else typer.prompt("Project name", default=default_name)
        language = (
            language
            if language is not None
            else typer.prompt("Primary language", default="", show_default=False)
        )
        test_command = (
            test_command
            if test_command is not None
            else typer.prompt("Test command", default="", show_default=False)
        )
        raw_targets = targets if targets is not None else "claude"
        while True:
            if targets is None:
                raw_targets = typer.prompt(
                    f"Targets ({', '.join(ADAPTERS)}; comma-separated)", default=raw_targets
                )
            try:
                target_list = parse_targets(raw_targets)
                break
            except ValueError as exc:
                if targets is not None:
                    raise _fail(str(exc)) from exc
                typer.secho(f"  {exc}", fg=typer.colors.RED, err=True)

    try:
        text = render_initial_config(name, language, test_command, target_list)
    except ConfigError as exc:
        raise _fail(str(exc), exc.problems) from exc
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    typer.secho(f"Created {config}. Run `agent sync` next.", fg=typer.colors.GREEN)
    typer.echo("")
    typer.echo("Git recommendations:")
    typer.echo("  - Commit agent.toml and the generated instruction files (CLAUDE.md, etc.).")
    typer.echo("  - .middletic/ holds local sync state: add it to .gitignore or commit it,")
    typer.echo("    depending on your team's preference.")


@app.command()
def adapters() -> None:
    """Show the capability matrix: what each agent supports natively vs degrades."""
    table = Table(title="Capability matrix", box=box.SIMPLE_HEAD)
    table.add_column("agent", no_wrap=True)
    for capability in Capability:
        table.add_column(capability.value, no_wrap=True)
    for adapter_name in ADAPTERS:
        cells = [
            "[green]native[/green]"
            if support_for(adapter_name, cap) is Support.NATIVE
            else "[yellow]degrades[/yellow]"
            for cap in Capability
        ]
        table.add_row(adapter_name, *cells)
    console = Console(width=max(Console().width, 100))
    console.print(table)
    console.print(
        "degrades: kept in the generated file as instructions, with a caution block "
        "where enforcement matters."
    )


@app.command()
def explain(
    adapter_name: Annotated[str, typer.Argument(help="Target name, e.g. gemini.")],
) -> None:
    """Explain how universal settings map to a target's format."""
    try:
        adapter = get_adapter(adapter_name)
    except KeyError as exc:
        raise _fail(str(exc.args[0])) from exc

    filename = adapter.filename
    typer.secho(f"{adapter.display_name} ({adapter.name}) -> {filename}", bold=True)
    for line in explain_lines(adapter.display_name, filename, adapter.capabilities):
        typer.echo(f"- {line}")
    for capability in (Capability.HOOKS, Capability.SKILLS):
        state = "native" if capability in adapter.capabilities else "degraded"
        typer.echo(f"- {capability.value} [{capability.value}]: {state}; no universal config yet.")


if __name__ == "__main__":
    app()
