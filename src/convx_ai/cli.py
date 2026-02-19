from __future__ import annotations

import getpass
import json
import platform
import shlex
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from convx_ai.adapters import default_input_path, get_adapter
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


def _resolve_input(source_system: str, input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path.expanduser().resolve()
    return default_input_path(source_system).resolve()


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
    source_system: str = typer.Option(
        "all",
        "--source-system",
        help="Source system(s): codex, claude, cursor, or all (default).",
    ),
    input_path: Path | None = typer.Option(
        None, "--input-path", help="Source sessions path override (per source)."
    ),
    user: str = typer.Option(
        getpass.getuser(), "--user", help="User namespace in output history path."
    ),
    system_name: str = typer.Option(
        platform.node() or "unknown-system",
        "--system-name",
        help="System namespace in output history path.",
    ),
    history_subpath: str = typer.Option(
        "history",
        "--history-subpath",
        help="Subpath inside repo where history is written.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan export without writing files."
    ),
    no_redact: bool = typer.Option(
        False, "--no-redact", help="Do not redact API keys, tokens, or passwords in output."
    ),
    with_context: bool = typer.Option(
        False, "--with-context", help="Include tool calls and injected context as HTML comments."
    ),
    with_thinking: bool = typer.Option(
        False, "--with-thinking", help="Include AI reasoning/thinking blocks as HTML comments."
    ),
) -> None:
    """Sync conversations for the current Git repo into it."""
    project_repo = _require_git_repo(Path.cwd())
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
                redact=not no_redact,
                with_context=with_context,
                with_thinking=with_thinking,
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
        ..., "--output-path", help="Git repo that stores all exported conversations."
    ),
    source_system: str = typer.Option(
        "codex", "--source-system", help="Source: codex, claude, or cursor."
    ),
    input_path: Path | None = typer.Option(
        None, "--input-path", help="Source sessions path override."
    ),
    user: str = typer.Option(
        getpass.getuser(), "--user", help="User namespace in output history path."
    ),
    system_name: str = typer.Option(
        platform.node() or "unknown-system",
        "--system-name",
        help="System namespace in output history path.",
    ),
    history_subpath: str = typer.Option(
        "history",
        "--history-subpath",
        help="Subpath inside output repo where history is written.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan export without writing files."
    ),
    no_redact: bool = typer.Option(
        False, "--no-redact", help="Do not redact API keys, tokens, or passwords in output."
    ),
    with_context: bool = typer.Option(
        False, "--with-context", help="Include tool calls and injected context as HTML comments."
    ),
    with_thinking: bool = typer.Option(
        False, "--with-thinking", help="Include AI reasoning/thinking blocks as HTML comments."
    ),
) -> None:
    """Full backup of all conversations into a target Git repo."""
    output_repo = _require_git_repo(output_path)
    source = sanitize_segment(source_system.lower())
    console = Console()
    with console.status(f"Processing {source}...", spinner="dots") as status:
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
            redact=not no_redact,
            with_context=with_context,
            with_thinking=with_thinking,
        )
        status.update(f"{source}: discovered={result.discovered} exported={result.exported}")
    _print_result(result, output_repo=output_repo, history_subpath=history_subpath)


@app.command("explore")
def explore_command(
    output_path: Path = typer.Option(
        Path.cwd(),
        "--output-path",
        help="Git repo containing exported conversations.",
    ),
) -> None:
    """Browse and search exported conversations in a TUI."""
    from convx_ai.search import ensure_index
    from convx_ai.tui import ExploreApp

    repo = _require_git_repo(output_path)
    index_path = repo / ".convx" / "index.json"
    if not index_path.exists():
        typer.echo("No index found. Run `convx sync` or `convx backup` first.")
        raise typer.Exit(1)
    ensure_index(repo)
    ExploreApp(repo).run()


hooks_app = typer.Typer(help="Install or remove pre-commit hook that runs sync before each commit.")


@hooks_app.command("install")
def hooks_install(
    history_subpath: str = typer.Option(
        "history",
        "--history-subpath",
        help="Subpath inside repo where history is written (must match sync).",
    ),
) -> None:
    """Install pre-commit hook that runs convx sync before each commit."""
    repo = _require_git_repo(Path.cwd())
    hooks_dir = repo / ".git" / "hooks"
    hook_path = hooks_dir / "pre-commit"
    script = f"""#!/usr/bin/env sh
convx sync --history-subpath {shlex.quote(history_subpath)}
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
        ..., "--output-path", help="Git repo containing exported conversations."
    ),
) -> None:
    """Show index totals and last update time."""
    output_repo = _require_git_repo(output_path)
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
