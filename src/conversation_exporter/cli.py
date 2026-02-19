from __future__ import annotations

import getpass
import platform
from pathlib import Path

import typer

from conversation_exporter.adapters import default_input_path, get_adapter
from conversation_exporter.engine import SyncResult, sync_sessions
from conversation_exporter.utils import sanitize_segment

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


def _print_result(result, *, output_repo: Path, history_subpath: str) -> None:
    typer.echo(f"output_repo={output_repo}")
    typer.echo(f"history_root={output_repo / history_subpath}")
    typer.echo(
        "discovered={d} exported={e} updated={u} skipped={s} filtered={f} dry_run={dr}".format(
            d=result.discovered,
            e=result.exported,
            u=result.updated,
            s=result.skipped,
            f=result.filtered,
            dr=result.dry_run,
        )
    )


def _source_systems(value: str) -> list[str]:
    if value.lower() == "all":
        return ["codex", "claude"]
    return [sanitize_segment(s.strip()) for s in value.split(",") if s.strip()]


@app.command("sync")
def sync_command(
    source_system: str = typer.Option(
        "all",
        "--source-system",
        help="Source system(s): codex, claude, or all (default).",
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
) -> None:
    """Sync conversations for the current Git repo into it."""
    project_repo = _require_git_repo(Path.cwd())
    sources = _source_systems(source_system)
    total = SyncResult()
    for source in sources:
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
        )
        total.discovered += result.discovered
        total.exported += result.exported
        total.updated += result.updated
        total.skipped += result.skipped
        total.filtered += result.filtered
        total.dry_run = dry_run
    typer.echo(f"output_repo={project_repo}")
    typer.echo(f"history_root={project_repo / history_subpath}")
    typer.echo(
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
        "codex", "--source-system", help="Conversation source system."
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
) -> None:
    """Full backup of all conversations into a target Git repo."""
    output_repo = _require_git_repo(output_path)
    source = sanitize_segment(source_system.lower())
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
    )
    _print_result(result, output_repo=output_repo, history_subpath=history_subpath)


@app.command("stats")
def stats_command(
    output_path: Path = typer.Option(
        ..., "--output-path", help="Git repo containing exported conversations."
    ),
) -> None:
    output_repo = _require_git_repo(output_path)
    index_path = output_repo / ".convx" / "index.json"
    if not index_path.exists():
        typer.echo("index_found=false sessions=0")
        return
    content = index_path.read_text(encoding="utf-8")
    import json

    parsed = json.loads(content)
    sessions = parsed.get("sessions", {})
    timestamps = sorted(record.get("updated_at", "") for record in sessions.values())
    last_updated = timestamps[-1] if timestamps else ""
    typer.echo(f"index_found=true sessions={len(sessions)} last_updated={last_updated}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
