from __future__ import annotations

import re
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label, ListItem, ListView, Markdown

from convx_ai.search import list_sessions, query_index
from textual.fuzzy import FuzzySearch


def _slug_only(basename: str) -> str:
    return re.sub(r"^\d{4}-\d{2}-\d{2}-\d{4}-", "", basename)


def _format_session(s: dict) -> str:
    user = s.get("user", "")
    date = (s.get("date") or "")[:10]
    source = s.get("source", "")
    slug = _slug_only(s.get("title") or "")[:50]
    return f"{user:8} {date} {source:8} {slug}"


class ExploreApp(App[None]):
    CSS_PATH = "explore.css"

    BINDINGS = [
        Binding("escape", "clear_search", "Clear search"),
        Binding("q", "quit", "Quit"),
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
        self.fuzzy = FuzzySearch()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Search... (Enter for full-text)", id="search")
            with Horizontal():
                yield ListView(id="sessions")
                with VerticalScroll(id="preview_scroll"):
                    yield Markdown("", id="preview")

    def on_mount(self) -> None:
        self.sessions = list_sessions(self.repo)
        self.displayed = self.sessions
        self._refresh_list()
        self.query_one("#search", Input).focus()

    def _refresh_list(self) -> None:
        lst = self.query_one("#sessions", ListView)
        lst.clear()
        for s in self.displayed:
            lst.append(ListItem(Label(_format_session(s))))
        if self.displayed:
            lst.index = 0
            self._show_preview(self.displayed[0])

    def _show_preview(self, s: dict) -> None:
        path = self.repo / s["path"]
        if path.exists():
            content = path.read_text(encoding="utf-8")
            self.query_one("#preview", Markdown).update(content)
        else:
            self.query_one("#preview", Markdown).update("")

    def _apply_fuzzy(self, query: str) -> None:
        if not query.strip():
            self.displayed = self.sessions
        else:
            matched = []
            for s in self.sessions:
                score, _ = self.fuzzy.match(query, _format_session(s))
                if score > 0:
                    matched.append((score, s))
            matched.sort(key=lambda x: -x[0])
            self.displayed = [s for _, s in matched]
        self._refresh_list()

    def _run_tantivy(self, query: str) -> None:
        if not query.strip():
            self.displayed = self.sessions
        else:
            self.displayed = query_index(self.repo, query, limit=50)
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
