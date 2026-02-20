from __future__ import annotations

import json
import shutil
from pathlib import Path


def _schema():
    from tantivy import SchemaBuilder

    return (
        SchemaBuilder()
        .add_text_field("session_key", stored=True)
        .add_text_field("title", stored=True)
        .add_text_field("content")
        .add_text_field("date", stored=True)
        .add_text_field("source", stored=True)
        .add_text_field("path", stored=True)
        .build()
    )


def ensure_index(repo: Path) -> None:
    index_path = repo / ".convx" / "index.json"
    search_dir = repo / ".convx" / "search-index"
    if not index_path.exists():
        return
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    sessions = index_data.get("sessions", {})
    if not sessions:
        return
    if search_dir.exists() and index_path.stat().st_mtime <= search_dir.stat().st_mtime:
        return
    if search_dir.exists():
        shutil.rmtree(search_dir)
    search_dir.mkdir(parents=True)
    from tantivy import Document, Index

    schema = _schema()
    index = Index(schema=schema, path=str(search_dir))
    writer = index.writer(heap_size=15_000_000, num_threads=1)
    for record in sessions.values():
        md_path = repo / record["markdown_path"]
        if not md_path.exists():
            continue
        content = md_path.read_text(encoding="utf-8")
        doc = Document()
        doc.add_text("session_key", record["session_key"])
        doc.add_text("title", record.get("basename", ""))
        doc.add_text("content", content)
        doc.add_text("date", record.get("started_at") or record.get("updated_at", ""))
        doc.add_text("source", record.get("source_system", ""))
        doc.add_text("path", record["markdown_path"])
        writer.add_document(doc)
    writer.commit()
    index.reload()


def _user_from_path(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "history":
        return parts[1]
    return ""


def _folder_from_path(path: str) -> str:
    """Directory subpath after history/user/source (empty when flat)."""
    parts = path.split("/")
    if len(parts) <= 4 or parts[0] != "history":
        return ""
    return "/".join(parts[3:-1])


def list_sessions(repo: Path) -> list[dict]:
    index_path = repo / ".convx" / "index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    sessions = data.get("sessions", {})
    out = []
    for r in sessions.values():
        path = r["markdown_path"]
        date = r.get("started_at") or r.get("updated_at", "")
        out.append(
            {
                "session_key": r["session_key"],
                "title": r.get("basename", ""),
                "date": date,
                "source": r.get("source_system", ""),
                "path": path,
                "user": _user_from_path(path),
                "folder": _folder_from_path(path),
            }
        )
    out.sort(key=lambda x: x["path"])
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def query_index(repo: Path, q: str, limit: int = 50) -> list[dict]:
    from tantivy import Index

    search_dir = repo / ".convx" / "search-index"
    if not search_dir.exists():
        return []
    schema = _schema()
    index = Index(schema=schema, path=str(search_dir))
    index.reload()
    searcher = index.searcher()
    try:
        query = index.parse_query(q, ["title", "content"])
    except (ValueError, Exception):
        return []
    hits = searcher.search(query, limit).hits
    out = []
    for _, doc_address in hits:
        doc = searcher.doc(doc_address)
        def _v(name: str) -> str:
            try:
                vals = doc[name]
                return str(vals[0]) if vals else ""
            except (KeyError, IndexError):
                return ""
        path = _v("path")
        out.append(
            {
                "session_key": _v("session_key"),
                "title": _v("title"),
                "date": _v("date"),
                "source": _v("source"),
                "path": path,
                "user": _user_from_path(path),
                "folder": _folder_from_path(path),
            }
        )
    return out
