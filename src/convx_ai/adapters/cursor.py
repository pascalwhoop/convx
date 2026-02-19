from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from convx_ai.models import NormalizedMessage, NormalizedSession
from convx_ai.utils import now_iso


CHAT_DATA_KEY = "workbench.panel.aichat.view.aichat.chatdata"
COMPOSER_DATA_KEY = "composer.composerData"
COMPOSER_PREFIX = "composerData:"


def _folder_to_cwd(folder: str) -> str:
    if not folder or not folder.startswith("file://"):
        return ""
    path = urllib.parse.unquote(folder.removeprefix("file://"))
    return path


def _epoch_ms_to_iso(ms: int | None) -> str:
    if ms is None:
        return now_iso()
    try:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except (ValueError, OSError):
        return now_iso()


def _parse_init_text(init_text: str) -> str:
    if not init_text or not init_text.strip():
        return ""
    try:
        obj = json.loads(init_text)
        root = obj.get("root", {})
        children = root.get("children", [])
        if children:
            first = children[0]
            inner = first.get("children", [])
            if inner and isinstance(inner[0].get("text"), str):
                return inner[0]["text"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return ""


def _parse_composer_bubbles(
    global_db: Path,
    composer_id: str,
    headers: list[dict],
    out: list[NormalizedMessage],
) -> None:
    if not global_db.exists():
        return
    try:
        conn = sqlite3.connect(f"file:{global_db}?mode=ro", uri=True)
        for h in headers:
            mtype = h.get("type")
            bubble_id = h.get("bubbleId")
            if bubble_id is None or mtype not in (1, 2):
                continue
            row = conn.execute(
                "SELECT value FROM cursorDiskKV WHERE key=?",
                (f"bubbleId:{composer_id}:{bubble_id}",),
            ).fetchone()
            if not row:
                continue
            val = row[0]
            text = val.decode("utf-8") if isinstance(val, bytes) else val
            try:
                bubble = json.loads(text)
            except json.JSONDecodeError:
                continue
            msg_text = (bubble.get("text") or "").strip()
            if not msg_text:
                continue
            if mtype == 1:
                out.append(NormalizedMessage(role="user", text=msg_text, kind="user"))
            elif mtype == 2:
                out.append(
                    NormalizedMessage(role="assistant", text=msg_text, kind="assistant")
                )
        conn.close()
    except sqlite3.Error:
        pass


def _extract_user_bubble_text(bubble: dict) -> str:
    if bubble.get("text"):
        return str(bubble["text"]).strip()
    delegate = bubble.get("delegate")
    if isinstance(delegate, dict) and delegate.get("a"):
        return str(delegate["a"]).strip()
    init_text = bubble.get("initText")
    if init_text:
        return _parse_init_text(init_text).strip()
    return ""


@dataclass
class _CursorSession:
    session_type: Literal["chat", "composer"]
    session_id: str
    started_at: str
    cwd: str
    fingerprint: str
    raw: dict
    source_path: str


class CursorAdapter:
    def __init__(self) -> None:
        self._sessions: dict[str, _CursorSession] = {}

    def discover_files(
        self, input_path: Path, *, repo_filter_path: Path | None = None
    ) -> list[Path]:
        self._sessions.clear()
        if not input_path.exists() or not input_path.is_dir():
            return []

        workspace_storage = input_path.resolve()
        global_db = workspace_storage.parent / "globalStorage" / "state.vscdb"

        composer_id_to_cwd: dict[str, str] = {}
        for ws_dir in sorted(workspace_storage.iterdir()):
            if not ws_dir.is_dir():
                continue
            db_path = ws_dir / "state.vscdb"
            wj_path = ws_dir / "workspace.json"
            if not db_path.exists() or not wj_path.exists():
                continue
            try:
                wj = json.loads(wj_path.read_text(encoding="utf-8"))
                folder = wj.get("folder", "")
                cwd = _folder_to_cwd(folder)
            except (json.JSONDecodeError, KeyError):
                cwd = ""
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                row = conn.execute(
                    "SELECT value FROM ItemTable WHERE key=?",
                    (COMPOSER_DATA_KEY,),
                ).fetchone()
                conn.close()
                if row:
                    val = row[0]
                    text = val.decode("utf-8") if isinstance(val, bytes) else val
                    data = json.loads(text)
                    for c in data.get("allComposers", []):
                        cid = c.get("composerId")
                        if cid:
                            composer_id_to_cwd[cid] = cwd
            except (sqlite3.Error, json.JSONDecodeError):
                pass

        def _under_repo(cwd: str) -> bool:
            if not repo_filter_path or not cwd:
                return True
            try:
                Path(cwd).resolve().relative_to(repo_filter_path.resolve())
                return True
            except ValueError:
                return False

        for ws_dir in sorted(workspace_storage.iterdir()):
            if not ws_dir.is_dir():
                continue
            db_path = ws_dir / "state.vscdb"
            wj_path = ws_dir / "workspace.json"
            if not db_path.exists() or not wj_path.exists():
                continue
            try:
                wj = json.loads(wj_path.read_text(encoding="utf-8"))
                cwd = _folder_to_cwd(wj.get("folder", ""))
            except (json.JSONDecodeError, KeyError):
                cwd = ""
            if repo_filter_path and not _under_repo(cwd):
                continue
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                row = conn.execute(
                    "SELECT value FROM ItemTable WHERE key=?",
                    (CHAT_DATA_KEY,),
                ).fetchone()
                conn.close()
                if not row:
                    continue
                val = row[0]
                text = val.decode("utf-8") if isinstance(val, bytes) else val
                data = json.loads(text)
                for tab in data.get("tabs", []):
                    bubbles = tab.get("bubbles", [])
                    if not bubbles:
                        continue
                    has_text = any(
                        (b.get("type") == "user" and _extract_user_bubble_text(b))
                        or (b.get("type") == "ai" and b.get("rawText"))
                        for b in bubbles
                    )
                    if not has_text:
                        continue
                    tab_id = tab.get("tabId", "")
                    if not tab_id:
                        continue
                    fp = hashlib.sha256(
                        json.dumps(tab, sort_keys=True).encode()
                    ).hexdigest()
                    started = _epoch_ms_to_iso(tab.get("lastSendTime"))
                    virtual = f"{db_path}::chat::{tab_id}"
                    self._sessions[virtual] = _CursorSession(
                        session_type="chat",
                        session_id=tab_id,
                        started_at=started,
                        cwd=cwd,
                        fingerprint=fp,
                        raw=tab,
                        source_path=str(db_path),
                    )
            except (sqlite3.Error, json.JSONDecodeError):
                continue

        if global_db.exists():
            try:
                conn = sqlite3.connect(f"file:{global_db}?mode=ro", uri=True)
                rows = conn.execute(
                    "SELECT key, value FROM cursorDiskKV WHERE key LIKE ?",
                    (f"{COMPOSER_PREFIX}%",),
                ).fetchall()
                conn.close()
                for key_row, val_row in rows:
                    key = key_row.decode("utf-8") if isinstance(key_row, bytes) else key_row
                    composer_id = key.removeprefix(COMPOSER_PREFIX)
                    if not composer_id:
                        continue
                    cwd = composer_id_to_cwd.get(composer_id, "")
                    if repo_filter_path and not _under_repo(cwd):
                        continue
                    if val_row is None:
                        continue
                    val = val_row.decode("utf-8") if isinstance(val_row, bytes) else val_row
                    if not val:
                        continue
                    try:
                        data = json.loads(val)
                    except json.JSONDecodeError:
                        continue
                    conv = data.get("conversation", [])
                    headers = data.get("fullConversationHeadersOnly", [])
                    if not conv and not headers:
                        continue
                    fp = hashlib.sha256(
                        json.dumps(conv or headers, sort_keys=True).encode()
                    ).hexdigest()
                    started = _epoch_ms_to_iso(data.get("createdAt"))
                    virtual = f"{global_db}::composer::{composer_id}"
                    self._sessions[virtual] = _CursorSession(
                        session_type="composer",
                        session_id=composer_id,
                        started_at=started,
                        cwd=cwd,
                        fingerprint=fp,
                        raw=data,
                        source_path=str(global_db),
                    )
            except sqlite3.Error:
                pass

        return [Path(k) for k in sorted(self._sessions)]

    def peek_session(self, source_path: Path, source_system: str) -> dict:
        key = str(source_path)
        if key not in self._sessions:
            raise ValueError(f"Unknown Cursor session: {source_path}")
        s = self._sessions[key]
        return {
            "session_id": s.session_id,
            "session_key": f"{source_system}:{s.session_id}",
            "started_at": s.started_at,
            "cwd": s.cwd,
            "fingerprint": s.fingerprint,
        }

    def parse_session(
        self,
        source_path: Path,
        source_system: str,
        user: str,
        system_name: str,
    ) -> NormalizedSession:
        key = str(source_path)
        if key not in self._sessions:
            raise ValueError(f"Unknown Cursor session: {source_path}")
        s = self._sessions[key]
        messages: list[NormalizedMessage] = []
        summary: str | None = None

        if s.session_type == "chat":
            for bubble in s.raw.get("bubbles", []):
                btype = bubble.get("type")
                if btype == "user":
                    text = _extract_user_bubble_text(bubble)
                    if text:
                        messages.append(
                            NormalizedMessage(role="user", text=text, kind="user")
                        )
                elif btype == "ai":
                    raw_text = bubble.get("rawText", "")
                    if raw_text:
                        messages.append(
                            NormalizedMessage(
                                role="assistant",
                                text=raw_text,
                                kind="assistant",
                            )
                        )
        else:
            summary = s.raw.get("name") or None
            conv = s.raw.get("conversation", [])
            headers = s.raw.get("fullConversationHeadersOnly", [])
            if conv:
                for msg in conv:
                    mtype = msg.get("type")
                    text = msg.get("text", "").strip()
                    if not text:
                        continue
                    if mtype == 1:
                        messages.append(
                            NormalizedMessage(role="user", text=text, kind="user")
                        )
                    elif mtype == 2:
                        messages.append(
                            NormalizedMessage(role="assistant", text=text, kind="assistant")
                        )
            elif headers:
                _parse_composer_bubbles(
                    Path(s.source_path),
                    s.session_id,
                    headers,
                    messages,
                )

        return NormalizedSession(
            session_key=f"{source_system}:{s.session_id}",
            source_system=source_system,
            session_id=s.session_id,
            source_path=s.source_path,
            started_at=s.started_at,
            user=user,
            system_name=system_name,
            cwd=s.cwd,
            messages=messages,
            summary=summary,
        )
