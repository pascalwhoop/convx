from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class NormalizedMessage:
    role: str
    text: str
    timestamp: str | None = None
    # kind classifies how this message is rendered:
    # "user" | "assistant" | "system" | "tool"
    kind: str = "user"


@dataclass
class NormalizedSession:
    session_key: str
    source_system: str
    session_id: str
    source_path: str
    started_at: str
    user: str
    system_name: str
    cwd: str
    messages: list[NormalizedMessage]
    summary: str | None = None
    child_sessions: list["NormalizedSession"] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["messages"] = [asdict(message) for message in self.messages]
        return data
