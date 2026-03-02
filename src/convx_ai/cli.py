from __future__ import annotations

import getpass
import json
import platform
import shlex
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from convx_ai.adapters import default_input_path, get_adapter
from convx_ai.config import ConvxConfig, create_config_if_missing
from convx_ai.engine import SyncResult, sync_sessions
from convx_ai.utils import sanitize_segment

app = typer.Typer(help="Export AI conversations into a Git repo.", no_args_is_help=True)


def _require_git_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"Path does not exist: {resolved}")
    if not (resolved / ".git").exists():
        raise typer.BadParameter(f"Not a git repository (missing .git): {resolved}")
    return resolved


def _require_git_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"Path does not exist: {resolved}")
    try:
        result = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise typer.BadParameter(f"Failed to run git: {exc}") from exc
    if result.returncode != 0:
        raise typer.BadParameter(f"Not inside a git repository: {resolved}")
    root = Path(result.stdout.strip()).resolve()
    if not root.exists():
        raise typer.BadParameter(f"Resolved git root does not exist: {root}")
    return root


def _resolve_output_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_input(source_system: str, input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path.expanduser().resolve()
    return default_input_path(source_system).resolve()


def _resolve_bool(value: bool | None, default: bool) -> bool:
    return default if value is None else value


def _print_sync_summary(
    result: SyncResult,
    *,
    output_repo: Path,
    history_subpath: str,
    per_source: list[tuple[str, SyncResult]] | None = None,
    dry_run: bool = False,
) -> None:
    console = Console()
    paths = Panel(
        f"[dim]output_repo[/]\n{output_repo}\n\n[dim]history_root[/]\n{output_repo / history_subpath}",
        title="[bold]Output",
        border_style="dim",
    )
    console.print(paths)

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Metric", style="dim")
    table.add_column("Count", justify="right")
    if per_source:
        for source, r in per_source:
            table.add_row(f"[cyan]{source}[/]", f"d={r.discovered} e={r.exported} u={r.updated} s={r.skipped} f={r.filtered}")
        table.add_row("", "")
    table.add_row("[bold]Total discovered[/]", str(result.discovered))
    table.add_row("Exported", str(result.exported))
    table.add_row("Updated", str(result.updated))
    table.add_row("Skipped", str(result.skipped))
    table.add_row("Filtered", str(result.filtered))
    if dry_run:
        table.add_row("[dim]dry_run[/]", "[yellow]true[/]")
    console.print(table)


def _print_result(result: SyncResult, *, output_repo: Path, history_subpath: str) -> None:
    _print_sync_summary(result, output_repo=output_repo, history_subpath=history_subpath, dry_run=result.dry_run)


def _source_systems(value: str) -> list[str]:
    if value.lower() == "all":
        return ["codex", "claude", "cursor"]
    return [sanitize_segment(s.strip()) for s in value.split(",") if s.strip()]


@app.command("sync")
def sync_command(
    source_system: str | None = typer.Option(
        None,
        "--source-system",
        help="Source system(s): codex, claude, cursor, or all (default).",
    ),
    input_path: Path | None = typer.Option(
        None, "--input-path", help="Source sessions path override (per source)."
    ),
    user: str | None = typer.Option(
        None, "--user", help="User namespace in output history path."
    ),
    system_name: str | None = typer.Option(
        None,
        "--system-name",
        help="System namespace in output history path.",
    ),
    history_subpath: str | None = typer.Option(
        None,
        "--history-subpath",
        help="Subpath inside repo where history is written.",
    ),
    dry_run: bool | None = typer.Option(
        None, "--dry-run/--no-dry-run", help="Plan export without writing files."
    ),
    redact: bool | None = typer.Option(
        None, "--redact/--no-redact", help="Redact API keys, tokens, or passwords in output."
    ),
    with_context: bool | None = typer.Option(
        None, "--with-context/--no-with-context", help="Include tool calls and injected context as HTML comments."
    ),
    with_thinking: bool | None = typer.Option(
        None, "--with-thinking/--no-with-thinking", help="Include AI reasoning/thinking blocks as HTML comments."
    ),
    skip_if_contains: str | None = typer.Option(
        None,
        "--skip-if-contains",
        help="Do not sync conversations that contain this string (pass empty to disable).",
    ),
    overwrite: bool | None = typer.Option(
        None, "--overwrite/--no-overwrite", help="Re-export all sessions, ignoring cached fingerprints."
    ),
) -> None:
    """Sync conversations for the current Git repo into it."""
    project_repo = _require_git_root(Path.cwd())
    create_config_if_missing(project_repo)
    config = ConvxConfig.for_repo(project_repo)
    sync_defaults = config.sync
    source_system = source_system or sync_defaults.source_system
    input_path = input_path or (Path(sync_defaults.input_path) if sync_defaults.input_path else None)
    user = user or sync_defaults.user or getpass.getuser()
    system_name = system_name or sync_defaults.system_name or platform.node() or "unknown-system"
    history_subpath = history_subpath or sync_defaults.history_subpath
    dry_run = _resolve_bool(dry_run, sync_defaults.dry_run)
    redact = _resolve_bool(redact, sync_defaults.redact)
    with_context = _resolve_bool(with_context, sync_defaults.with_context)
    with_thinking = _resolve_bool(with_thinking, sync_defaults.with_thinking)
    skip_if_contains = sync_defaults.skip_if_contains if skip_if_contains is None else skip_if_contains
    overwrite = _resolve_bool(overwrite, sync_defaults.overwrite)

    sources = _source_systems(source_system)
    total = SyncResult()
    console = Console()
    for i, source in enumerate(sources, 1):
        step = f"[{i}/{len(sources)}]"
        with console.status(f"{step} Processing {source}...", spinner="dots") as status:
            adapter = get_adapter(source)
            source_input = _resolve_input(source, input_path)
            result = sync_sessions(
                adapter=adapter,
                input_path=source_input,
                output_repo_path=project_repo,
                history_subpath=history_subpath,
                source_system=source,
                user=sanitize_segment(user),
                system_name=sanitize_segment(system_name),
                dry_run=dry_run,
                repo_filter_path=project_repo,
                flat_output=True,
                redact=redact,
                with_context=with_context,
                with_thinking=with_thinking,
                skip_if_contains=skip_if_contains,
                force_overwrite=overwrite,
            )
            total.discovered += result.discovered
            total.exported += result.exported
            total.updated += result.updated
            total.skipped += result.skipped
            total.filtered += result.filtered
            total.dry_run = dry_run
            status.update(
                f"{step} {source}: discovered={result.discovered} exported={result.exported} skipped={result.skipped} filtered={result.filtered}"
            )
        console.print(f"  {source}: discovered={result.discovered} exported={result.exported} updated={result.updated} skipped={result.skipped} filtered={result.filtered}")
    console.print(f"output_repo={project_repo}")
    console.print(f"history_root={project_repo / history_subpath}")
    console.print(
        "discovered={d} exported={e} updated={u} skipped={s} filtered={f} dry_run={dr}".format(
            d=total.discovered,
            e=total.exported,
            u=total.updated,
            s=total.skipped,
            f=total.filtered,
            dr=dry_run,
        )
    )


@app.command("backup")
def backup_command(
    output_path: Path = typer.Option(
        ..., "--output-path", help="Directory to export conversations to (created if missing)."
    ),
    source_system: str | None = typer.Option(
        None, "--source-system", help="Source system(s): codex, claude, cursor, or all (default)."
    ),
    input_path: Path | None = typer.Option(
        None, "--input-path", help="Source sessions path override (per source)."
    ),
    user: str | None = typer.Option(
        None, "--user", help="User namespace in output history path."
    ),
    system_name: str | None = typer.Option(
        None,
        "--system-name",
        help="System namespace in output history path.",
    ),
    history_subpath: str | None = typer.Option(
        None,
        "--history-subpath",
        help="Subpath inside output repo where history is written.",
    ),
    dry_run: bool | None = typer.Option(
        None, "--dry-run/--no-dry-run", help="Plan export without writing files."
    ),
    redact: bool | None = typer.Option(
        None, "--redact/--no-redact", help="Redact API keys, tokens, or passwords in output."
    ),
    with_context: bool | None = typer.Option(
        None, "--with-context/--no-with-context", help="Include tool calls and injected context as HTML comments."
    ),
    with_thinking: bool | None = typer.Option(
        None, "--with-thinking/--no-with-thinking", help="Include AI reasoning/thinking blocks as HTML comments."
    ),
    skip_if_contains: str | None = typer.Option(
        None,
        "--skip-if-contains",
        help="Do not sync conversations that contain this string (pass empty to disable).",
    ),
    overwrite: bool | None = typer.Option(
        None, "--overwrite/--no-overwrite", help="Re-export all sessions, ignoring cached fingerprints."
    ),
) -> None:
    """Full backup of all conversations into a directory (created if missing)."""
    output_repo = _resolve_output_path(output_path)
    config = ConvxConfig.for_repo(output_repo)
    backup_defaults = config.backup
    source_system = source_system or backup_defaults.source_system
    input_path = input_path or (Path(backup_defaults.input_path) if backup_defaults.input_path else None)
    user = user or backup_defaults.user or getpass.getuser()
    system_name = system_name or backup_defaults.system_name or platform.node() or "unknown-system"
    history_subpath = history_subpath or backup_defaults.history_subpath
    dry_run = _resolve_bool(dry_run, backup_defaults.dry_run)
    redact = _resolve_bool(redact, backup_defaults.redact)
    with_context = _resolve_bool(with_context, backup_defaults.with_context)
    with_thinking = _resolve_bool(with_thinking, backup_defaults.with_thinking)
    skip_if_contains = backup_defaults.skip_if_contains if skip_if_contains is None else skip_if_contains
    overwrite = _resolve_bool(overwrite, backup_defaults.overwrite)

    sources = _source_systems(source_system)
    total = SyncResult()
    console = Console()
    for i, source in enumerate(sources, 1):
        step = f"[{i}/{len(sources)}]"
        with console.status(f"{step} Processing {source}...", spinner="dots") as status:
            adapter = get_adapter(source)
            source_input = _resolve_input(source, input_path)
            result = sync_sessions(
                adapter=adapter,
                input_path=source_input,
                output_repo_path=output_repo,
                history_subpath=history_subpath,
                source_system=source,
                user=sanitize_segment(user),
                system_name=sanitize_segment(system_name),
                dry_run=dry_run,
                redact=redact,
                with_context=with_context,
                with_thinking=with_thinking,
                skip_if_contains=skip_if_contains,
                force_overwrite=overwrite,
            )
            total.discovered += result.discovered
            total.exported += result.exported
            total.updated += result.updated
            total.skipped += result.skipped
            total.filtered += result.filtered
            total.dry_run = dry_run
            status.update(
                f"{step} {source}: discovered={result.discovered} exported={result.exported} skipped={result.skipped} filtered={result.filtered}"
            )
        console.print(f"  {source}: discovered={result.discovered} exported={result.exported} updated={result.updated} skipped={result.skipped} filtered={result.filtered}")
    _print_result(total, output_repo=output_repo, history_subpath=history_subpath)


@app.command("explore")
def explore_command(
    output_path: Path = typer.Option(
        Path.cwd(),
        "--output-path",
        help="Directory containing exported conversations.",
    ),
    api_only: bool = typer.Option(
        False,
        "--api-only",
        help="Start API server only (no browser, no static files). For use with Vite dev server.",
    ),
    port: int = typer.Option(
        0,
        "--port",
        help="Port to listen on (0 = pick a free port; --api-only defaults to 7331).",
    ),
) -> None:
    """Browse exported conversations in a web dashboard."""
    import webbrowser

    from convx_ai.search import ensure_index
    from convx_ai.server import ConvxServer

    repo = output_path.expanduser().resolve()
    if not repo.exists():
        raise typer.BadParameter(f"Path does not exist: {repo}")
    index_path = repo / ".convx" / "index.json"
    if not index_path.exists():
        typer.echo("No index found. Run `convx sync` or `convx backup` first.")
        raise typer.Exit(1)
    ensure_index(repo)
    # In --api-only mode the Vite proxy expects port 7331 by default.
    effective_port = port or (7331 if api_only else 0)
    server = ConvxServer(repo, port=effective_port)
    server.serve_forever_in_thread()
    url = f"http://localhost:{server.port}"
    typer.echo(f"convx dashboard running at {url}")
    if api_only:
        typer.echo(f"  Vite proxy: set CONVX_API_PORT={server.port} if not 7331")
    if not api_only:
        webbrowser.open(url)
    typer.echo("Press Ctrl+C to stop.")
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()


@app.command("tui")
def tui_command(
    output_path: Path = typer.Option(
        Path.cwd(),
        "--output-path",
        help="Directory containing exported conversations.",
    ),
) -> None:
    """Browse and search exported conversations in a terminal UI (legacy)."""
    from convx_ai.search import ensure_index
    from convx_ai.tui import ExploreApp

    repo = output_path.expanduser().resolve()
    if not repo.exists():
        raise typer.BadParameter(f"Path does not exist: {repo}")
    index_path = repo / ".convx" / "index.json"
    if not index_path.exists():
        typer.echo("No index found. Run `convx sync` or `convx backup` first.")
        raise typer.Exit(1)
    ensure_index(repo)
    ExploreApp(repo).run()


hooks_app = typer.Typer(help="Install or remove pre-commit hook that runs sync before each commit.")


@hooks_app.command("install")
def hooks_install(
    history_subpath: str | None = typer.Option(
        None,
        "--history-subpath",
        help="Subpath inside repo where history is written (must match sync).",
    ),
) -> None:
    """Install pre-commit hook that runs convx sync before each commit."""
    repo = _require_git_repo(Path.cwd())
    config = ConvxConfig.for_repo(repo)
    history_subpath = history_subpath or config.hooks.history_subpath
    hooks_dir = repo / ".git" / "hooks"
    hook_path = hooks_dir / "pre-commit"
    script = f"""#!/usr/bin/env sh
uv run convx sync --history-subpath {shlex.quote(history_subpath)}
"""
    if hook_path.exists():
        content = hook_path.read_text()
        if "convx sync" in content:
            typer.echo("convx pre-commit hook already installed")
            raise typer.Exit(0)
        typer.echo(f"Existing pre-commit hook at {hook_path}. Prepend convx manually or remove it first.")
        raise typer.Exit(1)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(script)
    hook_path.chmod(0o755)
    typer.echo(f"Installed pre-commit hook at {hook_path}")


@hooks_app.command("uninstall")
def hooks_uninstall() -> None:
    """Remove convx pre-commit hook."""
    repo = _require_git_repo(Path.cwd())
    hook_path = repo / ".git" / "hooks" / "pre-commit"
    if not hook_path.exists():
        typer.echo("No pre-commit hook found")
        raise typer.Exit(0)
    content = hook_path.read_text()
    if "convx sync" not in content:
        typer.echo("pre-commit hook exists but is not from convx")
        raise typer.Exit(0)
    hook_path.unlink()
    typer.echo("Removed convx pre-commit hook")


app.add_typer(hooks_app, name="hooks")


@app.command("stats")
def stats_command(
    output_path: Path = typer.Option(
        Path.cwd(), "--output-path", help="Directory containing exported conversations."
    ),
) -> None:
    """Show index totals and last update time."""
    output_repo = _require_git_repo(output_path.expanduser().resolve())
    index_path = output_repo / ".convx" / "index.json"
    if not index_path.exists():
        typer.echo("index_found=false sessions=0")
        return
    content = index_path.read_text(encoding="utf-8")
    parsed = json.loads(content)
    sessions = parsed.get("sessions", {})
    timestamps = sorted(record.get("updated_at", "") for record in sessions.values())
    last_updated = timestamps[-1] if timestamps else ""
    typer.echo(f"index_found=true sessions={len(sessions)} last_updated={last_updated}")


@app.command("word-stats")
def word_stats_command(
    output_path: Path = typer.Option(
        Path.cwd(), "--output-path", help="Directory containing exported conversations."
    ),
    history_subpath: str | None = typer.Option(
        None, "--history-subpath", help="Subpath where history is written (must match sync/backup)."
    ),
) -> None:
    """Show word count statistics per day per project."""
    from convx_ai.stats import compute_word_series

    repo = output_path.expanduser().resolve()
    config = ConvxConfig.for_repo(repo)
    history_subpath = history_subpath or config.word_stats.history_subpath
    history_path = repo / history_subpath

    if not history_path.exists():
        typer.echo(f"Error: history directory not found at {history_path}")
        raise typer.Exit(1)

    result = compute_word_series(history_path)

    if not result["dates"]:
        typer.echo("No session data found.")
        return

    dates = result["dates"]
    series = result["series"]

    # Compute per-project totals and last active date
    project_totals = {
        project: sum(series[project])
        for project in result["projects"]
    }
    project_last_active = {
        project: max(
            (dates[i] for i, v in enumerate(series[project]) if v > 0),
            default="-",
        )
        for project in result["projects"]
    }

    # Sort projects by total words descending
    ranked = sorted(result["projects"], key=lambda p: project_totals[p], reverse=True)

    console = Console()
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Project", style="bold")
    table.add_column("Total words", justify="right")
    table.add_column("Active days", justify="right")
    table.add_column("Last active", style="dim")

    for project in ranked:
        total = project_totals[project]
        if total == 0:
            continue
        active_days = sum(1 for v in series[project] if v > 0)
        last = project_last_active[project]
        table.add_row(project, f"{total:,}", str(active_days), last)

    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
