from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from convx_ai.models import NormalizedMessage, NormalizedSession
from convx_ai.utils import now_iso, sha256_file


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts).strip()
    return ""


def _extract_started_at(data: dict[str, Any]) -> str:
    start_time = data.get("startTime")
    if isinstance(start_time, str) and start_time.strip():
        return start_time
    for message in data.get("messages", []):
        if not isinstance(message, dict):
            continue
        timestamp = message.get("timestamp")
        if isinstance(timestamp, str) and timestamp.strip():
            return timestamp
    return now_iso()


def _serialize_thoughts(thoughts: Any) -> str:
    if not isinstance(thoughts, list):
        return ""
    entries: list[str] = []
    for item in thoughts:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "").strip()
        description = str(item.get("description") or "").strip()
        text = str(item.get("text") or "").strip()
        if subject and description:
            entries.append(f"{subject}: {description}")
        elif description:
            entries.append(description)
        elif text:
            entries.append(text)
    return "\n\n".join(entries).strip()


def _tool_result_summary(tool_call: dict[str, Any]) -> str:
    result_display = tool_call.get("resultDisplay")
    if isinstance(result_display, str) and result_display.strip():
        return result_display.strip()
    result = tool_call.get("result")
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            function_response = first.get("functionResponse")
            if isinstance(function_response, dict):
                response = function_response.get("response")
                if isinstance(response, dict):
                    error = response.get("error")
                    if isinstance(error, str) and error.strip():
                        return f"error: {error.strip()}"
                    output = response.get("output")
                    if isinstance(output, str) and output.strip():
                        return output.strip()
    return json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)


class GeminiAdapter:
    def __init__(self) -> None:
        self._projects_cache: dict[Path, dict[str, str]] = {}

    def _tmp_root(self, input_path: Path) -> Path:
        resolved = input_path.expanduser().resolve()
        tmp_candidate = resolved / "tmp"
        if tmp_candidate.is_dir():
            return tmp_candidate
        return resolved

    def discover_files(
        self, input_path: Path, *, repo_filter_path: Path | None = None
    ) -> list[Path]:
        tmp_root = self._tmp_root(input_path)
        if not tmp_root.exists() or not tmp_root.is_dir():
            return []
        return sorted(
            path
            for path in tmp_root.rglob("session-*.json")
            if path.is_file() and path.parent.name == "chats"
        )

    def _project_root_from_file(self, source_path: Path) -> str:
        marker = source_path.parent.parent / ".project_root"
        if not marker.exists():
            return ""
        try:
            value = marker.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return value

    def _candidate_projects_files(self, source_path: Path) -> list[Path]:
        candidates: list[Path] = []
        for parent in source_path.parents:
            candidate = parent / "projects.json"
            if candidate.exists():
                candidates.append(candidate)
        default_path = Path("~/.gemini/projects.json").expanduser()
        if default_path.exists():
            candidates.append(default_path)
        seen: set[Path] = set()
        unique: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)
        return unique

    def _projects_hash_map(self, projects_path: Path) -> dict[str, str]:
        if projects_path in self._projects_cache:
            return self._projects_cache[projects_path]
        try:
            data = json.loads(projects_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mapping: dict[str, str] = {}
            self._projects_cache[projects_path] = mapping
            return mapping
        projects = data.get("projects", {})
        mapping = {}
        if isinstance(projects, dict):
            for path_str in projects.keys():
                if not isinstance(path_str, str) or not path_str:
                    continue
                digest = hashlib.sha256(path_str.encode("utf-8")).hexdigest()
                if digest not in mapping:
                    mapping[digest] = path_str
        self._projects_cache[projects_path] = mapping
        return mapping

    def _cwd_from_hash(self, source_path: Path, project_hash: str) -> str:
        if not project_hash:
            return ""
        for projects_file in self._candidate_projects_files(source_path):
            mapping = self._projects_hash_map(projects_file)
            if project_hash in mapping:
                return mapping[project_hash]
        return ""

    def _resolve_cwd(self, source_path: Path, project_hash: str) -> str:
        from_file = self._project_root_from_file(source_path)
        if from_file:
            return from_file
        return self._cwd_from_hash(source_path, project_hash)

    def peek_session(self, source_path: Path, source_system: str) -> dict:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not parse Gemini session: {source_path}") from exc
        session_id = str(data.get("sessionId") or source_path.stem)
        project_hash = str(data.get("projectHash") or "")
        return {
            "session_id": session_id,
            "session_key": f"{source_system}:{session_id}",
            "started_at": _extract_started_at(data),
            "cwd": self._resolve_cwd(source_path, project_hash),
            "fingerprint": sha256_file(source_path),
        }

    def parse_session(
        self,
        source_path: Path,
        source_system: str,
        user: str,
        system_name: str,
    ) -> NormalizedSession:
        data = json.loads(source_path.read_text(encoding="utf-8"))
        session_id = str(data.get("sessionId") or source_path.stem)
        project_hash = str(data.get("projectHash") or "")
        started_at = _extract_started_at(data)
        cwd = self._resolve_cwd(source_path, project_hash)
        messages: list[NormalizedMessage] = []

        raw_messages = data.get("messages", [])
        if not isinstance(raw_messages, list):
            raw_messages = []
        for message in raw_messages:
            if not isinstance(message, dict):
                continue
            message_type = str(message.get("type") or "")
            timestamp = message.get("timestamp")
            timestamp_value = str(timestamp) if isinstance(timestamp, str) else None

            if message_type == "user":
                text = _extract_text(message.get("content"))
                if text:
                    messages.append(
                        NormalizedMessage(
                            role="user",
                            text=text,
                            timestamp=timestamp_value,
                            kind="user",
                        )
                    )
                continue

            if message_type == "gemini":
                text = _extract_text(message.get("content"))
                if text:
                    messages.append(
                        NormalizedMessage(
                            role="assistant",
                            text=text,
                            timestamp=timestamp_value,
                            kind="assistant",
                        )
                    )
                thoughts_text = _serialize_thoughts(message.get("thoughts"))
                if thoughts_text:
                    messages.append(
                        NormalizedMessage(
                            role="reasoning",
                            text=thoughts_text,
                            timestamp=timestamp_value,
                            kind="thinking",
                        )
                    )
                tool_calls = message.get("toolCalls", [])
                if not isinstance(tool_calls, list):
                    tool_calls = []
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    name = str(tool_call.get("name") or "unknown_tool")
                    args = tool_call.get("args", {})
                    status = str(tool_call.get("status") or "unknown")
                    call_text = (
                        f"[tool_call] {name}\n"
                        f"{json.dumps(args, indent=2, sort_keys=True, ensure_ascii=False)}"
                    )
                    messages.append(
                        NormalizedMessage(
                            role="tool",
                            text=call_text,
                            timestamp=timestamp_value,
                            kind="tool",
                        )
                    )
                    result_summary = _tool_result_summary(tool_call)
                    result_text = f"[tool_result] {name} status={status}"
                    if result_summary:
                        result_text += f"\n{result_summary}"
                    messages.append(
                        NormalizedMessage(
                            role="tool",
                            text=result_text,
                            timestamp=timestamp_value,
                            kind="tool",
                        )
                    )
                continue

            if message_type in {"info", "warning", "error"}:
                text = _extract_text(message.get("content"))
                if text:
                    messages.append(
                        NormalizedMessage(
                            role="system",
                            text=f"[{message_type}] {text}",
                            timestamp=timestamp_value,
                            kind="system",
                        )
                    )
                continue

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
        )
