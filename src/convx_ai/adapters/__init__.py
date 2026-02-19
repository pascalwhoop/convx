from __future__ import annotations

from pathlib import Path

from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .cursor import CursorAdapter


def get_adapter(source_system: str):
    normalized = source_system.strip().lower()
    if normalized == "claude":
        return ClaudeAdapter()
    if normalized == "codex":
        return CodexAdapter()
    if normalized == "cursor":
        return CursorAdapter()
    raise ValueError(f"Unsupported source system: {source_system}")


def default_input_path(source_system: str) -> Path:
    normalized = source_system.strip().lower()
    if normalized == "claude":
        return Path("~/.claude/projects").expanduser()
    if normalized == "codex":
        return Path("~/.codex/sessions").expanduser()
    if normalized == "cursor":
        return Path("~/Library/Application Support/Cursor/User/workspaceStorage").expanduser()
    raise ValueError(f"No default input path for source system: {source_system}")
