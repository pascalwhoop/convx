from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def slugify(value: str, default: str = "session", max_len: int = 60) -> str:
    lowered = re.sub(r"\s+", "-", value.strip().lower())
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", lowered).strip("-._")
    if not cleaned:
        cleaned = default
    return cleaned[:max_len].rstrip("-._") or default


def sanitize_segment(segment: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", segment).strip(".-")
    return cleaned or "unknown"


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_basename_timestamp(value: str) -> str:
    parsed = parse_iso_datetime(value)
    return parsed.strftime("%Y-%m-%d-%H%M")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_json(path: Path, content: dict) -> None:
    serialized = json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    atomic_write_text(path, serialized)
