from __future__ import annotations

import json
from pathlib import Path

from convx_ai.models import NormalizedMessage, NormalizedSession
from convx_ai.utils import now_iso


def _encode_path(path: Path | str) -> str:
    s = str(path).replace("/", "-")
    return s if s.startswith("-") else f"-{s}"


def _project_dir_matches_repo(project_dir_name: str, repo_path: Path) -> bool:
    encoded = _encode_path(repo_path.resolve())
    return project_dir_name == encoded or project_dir_name.startswith(f"{encoded}-")


def _extract_text_from_content(content) -> tuple[str, str]:
    """Returns (text, content_type). content_type can be 'text', 'tool_result', 'tool_use', 'thinking'."""
    if isinstance(content, str):
        return (content.strip(), "text")
    if isinstance(content, list):
        parts: list[str] = []
        primary_type = "text"
        for item in content:
            if not isinstance(item, dict):
                continue
            ct = item.get("type")
            if ct == "text":
                t = item.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
            elif ct == "tool_result":
                primary_type = "tool_result"
                c = item.get("content", "")
                parts.append(str(c))
            elif ct == "tool_use":
                primary_type = "tool_use"
                name = item.get("name", "unknown")
                inp = item.get("input", {})
                parts.append(f"[tool_use] {name}\n{json.dumps(inp, indent=2)}")
            elif ct == "thinking":
                primary_type = "thinking"
                t = item.get("thinking", "")
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
        return ("\n\n".join(parts).strip(), primary_type)
    return ("", "text")


def _parse_claude_jsonl(
    source_path: Path, source_system: str, user: str, system_name: str, *, is_subagent: bool
) -> NormalizedSession:
    messages: list[NormalizedMessage] = []
    session_id = source_path.stem
    if is_subagent and session_id.startswith("agent-"):
        session_id = session_id[len("agent-") :]
    started_at: str | None = None
    cwd = ""

    for line in source_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        obj_type = obj.get("type")
        if obj_type in ("queue-operation", "file-history-snapshot", "summary", "progress"):
            continue
        if obj.get("isMeta"):
            continue

        timestamp = obj.get("timestamp")
        msg = obj.get("message", {})
        content = msg.get("content", [])

        if obj_type == "user":
            text, content_type = _extract_text_from_content(content)
            if not text:
                continue
            if content_type == "tool_result":
                messages.append(
                    NormalizedMessage(role="tool", text=text, timestamp=timestamp, kind="tool")
                )
            else:
                messages.append(
                    NormalizedMessage(role="user", text=text, timestamp=timestamp, kind="user")
                )
            if not started_at and timestamp:
                started_at = timestamp
            if not cwd:
                cwd = obj.get("cwd", "")

        elif obj_type == "assistant":
            text, content_type = _extract_text_from_content(content)
            if not text:
                continue
            if content_type == "tool_use":
                messages.append(
                    NormalizedMessage(role="tool", text=text, timestamp=timestamp, kind="tool")
                )
            elif content_type == "thinking":
                messages.append(
                    NormalizedMessage(role="reasoning", text=text, timestamp=timestamp, kind="thinking")
                )
            else:
                messages.append(
                    NormalizedMessage(
                        role="assistant", text=text, timestamp=timestamp, kind="assistant"
                    )
                )
            if not started_at and timestamp:
                started_at = timestamp
            if not cwd:
                cwd = obj.get("cwd", "")

        elif obj_type == "system":
            text, _ = _extract_text_from_content(content)
            if text:
                messages.append(
                    NormalizedMessage(role="system", text=text, timestamp=timestamp, kind="system")
                )

    if not started_at:
        started_at = now_iso()

    return NormalizedSession(
        session_key=f"{source_system}:{session_id}",
        source_system=source_system,
        session_id=session_id,
        source_path=str(source_path),
        started_at=started_at,
        user=user,
        system_name=system_name,
        cwd=cwd,
        messages=messages,
        child_sessions=None,
    )


class ClaudeAdapter:
    def discover_files(
        self, input_path: Path, *, repo_filter_path: Path | None = None
    ) -> list[Path]:
        if not input_path.exists() or not input_path.is_dir():
            return []
        paths: list[Path] = []
        for project_dir in sorted(input_path.iterdir()):
            if not project_dir.is_dir():
                continue
            name = project_dir.name
            if repo_filter_path and not _project_dir_matches_repo(name, repo_filter_path):
                continue
            index_path = project_dir / "sessions-index.json"
            if index_path.exists():
                try:
                    data = json.loads(index_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {}
                for entry in data.get("entries", []):
                    if entry.get("isSidechain"):
                        continue
                    sid = entry.get("sessionId")
                    if not sid:
                        continue
                    full_path = entry.get("fullPath")
                    p = Path(full_path) if full_path else None
                    if p and p.exists():
                        paths.append(p)
                    else:
                        p = project_dir / f"{sid}.jsonl"
                        if p.exists():
                            paths.append(p)
            else:
                for p in sorted(project_dir.glob("*.jsonl")):
                    if p.is_file():
                        paths.append(p)
        return paths

    def peek_session(self, source_path: Path, source_system: str) -> dict:
        project_dir = source_path.parent
        index_path = project_dir / "sessions-index.json"
        session_id = source_path.stem
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
            else:
                for entry in data.get("entries", []):
                    if entry.get("sessionId") == session_id and not entry.get("isSidechain"):
                        project_path = entry.get("projectPath") or data.get("originalPath", "")
                        return {
                            "session_id": session_id,
                            "session_key": f"{source_system}:{session_id}",
                            "cwd": project_path,
                            "started_at": entry.get("created") or entry.get("modified", ""),
                            "summary": entry.get("summary"),
                            "fingerprint": str(entry.get("fileMtime", "")),
                        }
        if source_path.exists():
            for line in source_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") in ("user", "assistant"):
                    cwd = obj.get("cwd", "")
                    ts = obj.get("timestamp", "")
                    return {
                        "session_id": session_id,
                        "session_key": f"{source_system}:{session_id}",
                        "cwd": cwd,
                        "started_at": ts,
                        "summary": None,
                        "fingerprint": None,
                    }
        raise ValueError(f"Could not peek session: {source_path}")

    def parse_session(
        self,
        source_path: Path,
        source_system: str,
        user: str,
        system_name: str,
    ) -> NormalizedSession:
        session = _parse_claude_jsonl(
            source_path, source_system, user, system_name, is_subagent=False
        )
        subagents_dir = source_path.parent / source_path.stem / "subagents"
        child_sessions: list[NormalizedSession] = []
        if subagents_dir.exists():
            for agent_file in sorted(subagents_dir.glob("agent-*.jsonl")):
                if agent_file.is_file():
                    child = _parse_claude_jsonl(
                        agent_file, source_system, user, system_name, is_subagent=True
                    )
                    child_sessions.append(child)
        session.child_sessions = child_sessions
        return session
