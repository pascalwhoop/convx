from __future__ import annotations

import json
from pathlib import Path

from conversation_exporter.models import NormalizedMessage, NormalizedSession
from conversation_exporter.utils import now_iso


def _collect_user_texts(lines: list[str]) -> set[str]:
    """Collect actual human-typed message texts from event_msg entries."""
    texts: set[str] = set()
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("type") == "event_msg":
            payload = item.get("payload", {})
            if payload.get("type") == "user_message":
                msg = payload.get("message", "")
                if isinstance(msg, str) and msg.strip():
                    texts.add(msg.strip())
    return texts


class CodexAdapter:
    def discover_files(
        self, input_path: Path, *, repo_filter_path: Path | None = None
    ) -> list[Path]:
        if not input_path.exists():
            return []
        return sorted(path for path in input_path.rglob("*.jsonl") if path.is_file())

    def peek_session(self, source_path: Path, source_system: str) -> dict:
        with source_path.open("r", encoding="utf-8") as handle:
            first = handle.readline().strip()
        if not first:
            raise ValueError(f"Empty file: {source_path}")
        first_obj = json.loads(first)
        payload = first_obj.get("payload", {})
        session_id = payload.get("id") or source_path.stem
        started_at = payload.get("timestamp") or first_obj.get("timestamp") or now_iso()
        cwd = payload.get("cwd") or ""
        return {
            "session_id": str(session_id),
            "session_key": f"{source_system}:{session_id}",
            "started_at": str(started_at),
            "cwd": str(cwd),
        }

    def parse_session(
        self,
        source_path: Path,
        source_system: str,
        user: str,
        system_name: str,
    ) -> NormalizedSession:
        messages: list[NormalizedMessage] = []
        session_id = source_path.stem
        started_at: str | None = None
        cwd = ""

        raw_lines = source_path.read_text(encoding="utf-8").splitlines()
        actual_user_texts = _collect_user_texts(raw_lines)

        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            item_type = item.get("type")
            payload = item.get("payload", {})
            timestamp = item.get("timestamp")

            if item_type == "session_meta":
                session_id = str(payload.get("id") or session_id)
                started_at = str(payload.get("timestamp") or timestamp or started_at or now_iso())
                cwd = str(payload.get("cwd") or cwd)
                base_instructions = (payload.get("base_instructions") or {}).get("text", "")
                if base_instructions:
                    messages.append(NormalizedMessage(
                        role="system",
                        text=base_instructions,
                        timestamp=timestamp,
                        kind="system",
                    ))
                continue

            if item_type != "response_item":
                continue

            payload_type = payload.get("type")

            if payload_type == "function_call":
                name = payload.get("name", "unknown_tool")
                arguments = payload.get("arguments", "")
                text = f"[tool_call] {name}\n{arguments}"
                messages.append(NormalizedMessage(
                    role="tool",
                    text=text,
                    timestamp=timestamp,
                    kind="tool",
                ))
                continue

            if payload_type == "function_call_output":
                output = payload.get("output", "")
                call_id = payload.get("call_id", "")
                text = f"[tool_result] call_id={call_id}\n{output}"
                messages.append(NormalizedMessage(
                    role="tool",
                    text=text,
                    timestamp=timestamp,
                    kind="tool",
                ))
                continue

            if payload_type == "reasoning":
                summary_parts = [
                    s.get("text", "")
                    for s in (payload.get("summary") or [])
                    if s.get("type") == "summary_text"
                ]
                text = "\n".join(summary_parts).strip()
                if text:
                    messages.append(NormalizedMessage(
                        role="reasoning",
                        text=text,
                        timestamp=timestamp,
                        kind="system",
                    ))
                continue

            if payload_type != "message":
                continue

            role = str(payload.get("role") or "unknown")
            content_items = payload.get("content", [])
            parts: list[str] = []
            for content in content_items:
                content_type = content.get("type")
                if content_type in {"input_text", "output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            text_value = "\n\n".join(parts).strip()
            if not text_value:
                continue

            if role == "developer":
                messages.append(NormalizedMessage(
                    role="system",
                    text=text_value,
                    timestamp=timestamp,
                    kind="system",
                ))
            elif role == "user":
                if text_value in actual_user_texts:
                    kind = "user"
                else:
                    kind = "system"
                messages.append(NormalizedMessage(
                    role=role,
                    text=text_value,
                    timestamp=timestamp,
                    kind=kind,
                ))
            elif role == "assistant":
                messages.append(NormalizedMessage(
                    role="assistant",
                    text=text_value,
                    timestamp=timestamp,
                    kind="assistant",
                ))
            else:
                messages.append(NormalizedMessage(
                    role=role,
                    text=text_value,
                    timestamp=timestamp,
                    kind="system",
                ))

        if started_at is None:
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
        )
