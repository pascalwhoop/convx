from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from convx_ai.models import NormalizedSession
from convx_ai.redact import redact_secrets
from convx_ai.render import first_user_text, render_json, render_markdown
from convx_ai.utils import (
    atomic_write_json,
    atomic_write_text,
    format_basename_timestamp,
    now_iso,
    sanitize_segment,
    sha256_file,
    slugify,
)


@dataclass
class SyncResult:
    discovered: int = 0
    exported: int = 0
    skipped: int = 0
    filtered: int = 0
    updated: int = 0
    dry_run: bool = False


def _load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {"version": 1, "sessions": {}}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "sessions": {}}
    sessions = raw.get("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
    return {"version": raw.get("version", 1), "sessions": sessions}


def _relative_cwd_parts(cwd: str) -> list[str]:
    path = Path(cwd) if cwd else Path("unknown")
    parts = list(path.parts)
    if len(parts) >= 3 and parts[0] == "/" and parts[1] in {"Users", "home"}:
        parts = parts[3:]
    elif parts and parts[0] == "/":
        parts = parts[1:]
    if not parts:
        parts = ["unknown"]
    return [sanitize_segment(part) for part in parts]


def _build_output_dir(base_dir: Path, session: NormalizedSession, *, flat: bool = False) -> Path:
    if flat:
        return base_dir / sanitize_segment(session.user) / sanitize_segment(session.source_system)
    path = base_dir / sanitize_segment(session.user) / sanitize_segment(session.source_system) / sanitize_segment(session.system_name)
    for part in _relative_cwd_parts(session.cwd):
        path = path / part
    return path


def _session_basename(session: NormalizedSession, preferred: str | None) -> str:
    if preferred:
        return preferred
    stamp = format_basename_timestamp(session.started_at)
    seed = session.summary or first_user_text(session)
    slug = slugify(seed, default=slugify(session.session_id[-8:] if session.session_id else "session"))
    return f"{stamp}-{slug}"


def _session_contains(session: NormalizedSession, needle: str) -> bool:
    if not needle:
        return False
    for msg in session.messages:
        if msg.text and needle in msg.text:
            return True
    if session.child_sessions:
        for child in session.child_sessions:
            if _session_contains(child, needle):
                return True
    return False


def _is_under_repo(cwd: str, repo_path: Path) -> bool:
    if not cwd:
        return False
    resolved_repo = repo_path.resolve()
    try:
        Path(cwd).resolve().relative_to(resolved_repo)
        return True
    except ValueError:
        cwd_parts = [part for part in Path(cwd).parts if part not in {"", "/"}]
        repo_name = resolved_repo.name
        if repo_name in cwd_parts:
            return True
        return False


def sync_sessions(
    *,
    adapter,
    input_path: Path,
    output_repo_path: Path,
    history_subpath: str,
    source_system: str,
    user: str,
    system_name: str,
    dry_run: bool = False,
    repo_filter_path: Path | None = None,
    flat_output: bool = False,
    redact: bool = True,
    with_context: bool = False,
    with_thinking: bool = False,
    skip_if_contains: str = "CONVX_NO_SYNC",
) -> SyncResult:
    history_root = output_repo_path / history_subpath
    index_path = output_repo_path / ".convx" / "index.json"
    index = _load_index(index_path)
    records: dict = index["sessions"]

    result = SyncResult(dry_run=dry_run)
    for source_path in adapter.discover_files(input_path, repo_filter_path=repo_filter_path):
        result.discovered += 1
        try:
            peek = adapter.peek_session(source_path, source_system)
        except (ValueError, OSError):
            result.filtered += 1
            continue
        fingerprint = peek.get("fingerprint") or sha256_file(source_path)
        session_key = peek["session_key"]
        cwd = str(peek.get("cwd", ""))
        if repo_filter_path and not _is_under_repo(cwd, repo_filter_path):
            result.filtered += 1
            continue

        prior = records.get(session_key, {})
        if prior.get("fingerprint") == fingerprint:
            markdown_rel = prior.get("markdown_path")
            json_rel = prior.get("json_path")
            if markdown_rel and json_rel:
                md_exists = (output_repo_path / markdown_rel).exists()
                json_exists = (output_repo_path / json_rel).exists()
                if md_exists and json_exists:
                    result.skipped += 1
                    continue

        try:
            session = adapter.parse_session(source_path, source_system, user, system_name)
        except (ValueError, OSError, KeyError, json.JSONDecodeError):
            result.filtered += 1
            continue
        if repo_filter_path and not _is_under_repo(session.cwd, repo_filter_path):
            result.filtered += 1
            continue
        if _session_contains(session, skip_if_contains):
            result.filtered += 1
            continue
        try:
            out_dir = _build_output_dir(history_root, session, flat=flat_output)
            basename = _session_basename(session, prior.get("basename"))

            if session.child_sessions is not None:
                session_dir = out_dir / basename
                markdown_path = session_dir / "index.md"
                json_path = session_dir / ".index.json"
                if not dry_run:
                    atomic_write_text(
                        markdown_path,
                        redact_secrets(
                            render_markdown(session, with_context=with_context, with_thinking=with_thinking),
                            redact=redact,
                        ),
                    )
                    atomic_write_text(json_path, redact_secrets(render_json(session), redact=redact))
                    for child in session.child_sessions:
                        atomic_write_text(
                            session_dir / f"agent-{child.session_id}.md",
                            redact_secrets(
                                render_markdown(child, with_context=with_context, with_thinking=with_thinking),
                                redact=redact,
                            ),
                        )
            else:
                markdown_path = out_dir / f"{basename}.md"
                json_path = out_dir / f".{basename}.json"
                if not dry_run:
                    atomic_write_text(
                        markdown_path,
                        redact_secrets(
                            render_markdown(session, with_context=with_context, with_thinking=with_thinking),
                            redact=redact,
                        ),
                    )
                    atomic_write_text(json_path, redact_secrets(render_json(session), redact=redact))

            now = now_iso()
            records[session_key] = {
                "session_key": session_key,
                "fingerprint": fingerprint,
                "source_system": source_system,
                "source_path": str(source_path),
                "markdown_path": str(markdown_path.relative_to(output_repo_path)),
                "json_path": str(json_path.relative_to(output_repo_path)),
                "basename": basename,
                "updated_at": now,
                "started_at": session.started_at,
            }
            if prior:
                result.updated += 1
            else:
                result.exported += 1
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            result.filtered += 1
            continue

    if not dry_run:
        try:
            _ensure_convx_gitignore(output_repo_path)
            atomic_write_json(index_path, index)
        except OSError:
            pass
    return result


def _ensure_convx_gitignore(repo_path: Path) -> None:
    gitignore = repo_path / ".convx" / ".gitignore"
    content = "*\n!.gitignore\n"
    if not gitignore.exists() or gitignore.read_text() != content:
        atomic_write_text(gitignore, content)
