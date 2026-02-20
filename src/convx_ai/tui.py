from __future__ import annotations

import asyncio
import re
from pathlib import Path

from rapidfuzz import fuzz, process
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Label, ListItem, ListView, Markdown

from convx_ai.search import list_sessions, query_index


def _slug_only(basename: str) -> str:
    return re.sub(r"^\d{4}-\d{2}-\d{2}-\d{4}-", "", basename)


def _slug_readable(slug: str) -> str:
    return slug.replace("-", " ")


def _compact_folder(path: str, max_width: int) -> str:
    """Fish-style: abbreviate intermediate segments to first 3 chars, keep last full."""
    if not path:
        return ""
    parts = path.split("/")
    if len(parts) == 1:
        return path[:max_width] if len(path) > max_width else path
    intermediates = [p[:3] for p in parts[:-1]]
    last = parts[-1]
    compacted = "/".join(intermediates) + "/" + last
    if len(compacted) > max_width:
        return "..." + compacted[-(max_width - 3) :]
    return compacted


W_USER = 8
W_DATE = 10
W_SOURCE = 8
W_FOLDER = 26
W_SLUG = 44


def _cell(s: str, width: int) -> str:
    if len(s) > width:
        s = s[: width - 3] + "..."
    return s.ljust(width)[:width]


def _format_session(s: dict) -> str:
    user = _cell((s.get("user") or ""), W_USER)
    date = _cell((s.get("date") or "")[:10], W_DATE)
    source = _cell((s.get("source") or ""), W_SOURCE)
    folder_raw = s.get("folder", "")
    folder = _cell(_compact_folder(folder_raw, W_FOLDER), W_FOLDER)
    slug = _cell(_slug_readable(_slug_only(s.get("title") or "")), W_SLUG)
    return f"{user} {date} {source} {folder} │ {slug}"


class ExploreApp(App[None]):
    CSS_PATH = "explore.css"

    BINDINGS = [
        Binding("escape", "clear_search", "Clear search"),
        Binding("q", "quit", "Quit"),
        Binding("tab", "focus_next", "Next pane", show=False),
        Binding("shift+tab", "focus_previous", "Prev pane", show=False),
        Binding("l", "focus_list", "List", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_home", "Top", show=False),
        Binding("G", "cursor_end", "Bottom", show=False),
    ]

    def __init__(self, repo: Path) -> None:
        super().__init__()
        self.repo = repo
        self.sessions: list[dict] = []
        self.displayed: list[dict] = []
        self._formatted: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Search... (Enter for full-text)", id="search")
            yield ListView(id="sessions")
            with VerticalScroll(id="preview_scroll"):
                yield Markdown("", id="preview")

    def on_mount(self) -> None:
        self.sessions = list_sessions(self.repo)
        self._formatted = [_format_session(s) for s in self.sessions]
        self.displayed = self.sessions
        self._refresh_list()
        self.query_one("#sessions", ListView).focus()

    def _refresh_list(self) -> None:
        lst = self.query_one("#sessions", ListView)
        lst.clear()
        for s in self.displayed:
            lst.append(ListItem(Label(_format_session(s))))
        if self.displayed:
            lst.index = 0
            self._show_preview(self.displayed[0])
        else:
            self._show_preview(None)

    def _show_preview(self, s: dict | None) -> None:
        if s is None:
            self.query_one("#preview", Markdown).update(
                "*Select a session (↑↓ j k) to view conversation.*"
            )
            return
        path = self.repo / s["path"]
        if path.exists():
            content = path.read_text(encoding="utf-8")
            self.query_one("#preview", Markdown).update(content)
        else:
            self.query_one("#preview", Markdown).update("")

    @work(exclusive=True)
    async def _apply_fuzzy(self, query: str) -> None:
        # Debounce: if another keystroke arrives within 80ms this coroutine is
        # cancelled before we touch the DOM at all.
        await asyncio.sleep(0.08)
        if not query.strip():
            self.displayed = self.sessions
        else:
            hits = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: process.extract(
                    query,
                    self._formatted,
                    scorer=fuzz.WRatio,
                    limit=50,
                    score_cutoff=30,
                ),
            )
            self.displayed = [self.sessions[idx] for _, _, idx in hits]
        self._refresh_list()

    @work(exclusive=True)
    async def _run_tantivy(self, query: str) -> None:
        if not query.strip():
            self.displayed = self.sessions
        else:
            self.displayed = await asyncio.get_event_loop().run_in_executor(
                None, lambda: query_index(self.repo, query, limit=50)
            )
        self._refresh_list()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_fuzzy(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._run_tantivy(event.value)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        lst = self.query_one("#sessions", ListView)
        idx = lst.index
        if idx is not None and 0 <= idx < len(self.displayed):
            self._show_preview(self.displayed[idx])

    def action_clear_search(self) -> None:
        self.query_one("#search", Input).value = ""
        self.displayed = self.sessions
        self._refresh_list()

    def action_cursor_down(self) -> None:
        self.query_one("#sessions", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#sessions", ListView).action_cursor_up()

    def action_cursor_home(self) -> None:
        lst = self.query_one("#sessions", ListView)
        lst.index = 0
        if self.displayed:
            self._show_preview(self.displayed[0])

    def action_cursor_end(self) -> None:
        lst = self.query_one("#sessions", ListView)
        if self.displayed:
            lst.index = len(self.displayed) - 1
            self._show_preview(self.displayed[-1])

    def action_focus_list(self) -> None:
        self.query_one("#sessions", ListView).focus()
