"""
The Binder — local-first knowledge browser. b17: SAPS1

Jeles at the desk. The Binder files everything.
Searches your Willow KB. Degrades gracefully when Willow is unavailable.

Usage:
  python3 app.py
"""
import os
import sys
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Label, Static, TextArea

# Willow KB access goes through the injected READ seam (rule #1: KB reads →
# knowledge_search). The seam PREFERS an injected willow-mcp client and only
# falls back to direct Postgres; app.py no longer touches the driver or SQL.
import willow_read


class TheBinderApp(App):
    CSS = """
    #search-bar  { height: 3; padding: 0 1; }
    #results     { width: 40; border-right: solid $primary; }
    #detail      { width: 1fr; padding: 0 1; }
    DataTable    { height: 1fr; }
    #detail-body { height: 1fr; }
    #status      { height: 1; color: $text-muted; padding: 0 1; }
    """

    BINDINGS = [
        Binding("enter",  "search",       "Search", show=False),
        Binding("escape", "focus_search", "Search bar"),
        Binding("q",      "quit",         "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._results: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Search your knowledge base…", id="search-bar")
        yield Horizontal(
            DataTable(id="results"),
            Vertical(
                Static("", id="detail-title"),
                Static("", id="detail-project"),
                TextArea("Select a result to read it.", id="detail-body"),
                id="detail",
            ),
        )
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "The Binder"
        self.sub_title = "local knowledge browser"
        table = self.query_one("#results", DataTable)
        table.add_columns("Title")
        backend = willow_read.active_backend()
        if backend == "mcp":
            self._set_status("Willow (knowledge_search) — type to search")
        elif backend == "postgres":
            self._set_status("Willow (postgres fallback) — type to search")
        else:
            self._set_status("Willow unavailable — no results")
        self.query_one("#search-bar").focus()

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-bar":
            self._do_search(event.value.strip())

    def _do_search(self, query: str) -> None:
        if not query:
            return
        if not willow_read.available():
            self._set_status("Willow unavailable — no results")
            return
        self._results = willow_read.search(query, limit=30)
        table = self.query_one("#results", DataTable)
        table.clear()
        for r in self._results:
            table.add_row(r["title"][:36])
        self._set_status(f"{len(self._results)} result(s) for '{query}'")
        if self._results:
            table.focus()

    def on_data_table_row_selected(self, _event) -> None:
        table = self.query_one("#results", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._results):
            result = self._results[row]
            self.query_one("#detail-title",   Static).update(f"[bold]{result['title']}[/bold]")
            self.query_one("#detail-project", Static).update(f"project: {result.get('project','—')}")
            self.query_one("#detail-body",    TextArea).load_text(result.get("summary", ""))

    def action_search(self) -> None:
        query = self.query_one("#search-bar", Input).value.strip()
        self._do_search(query)

    def action_focus_search(self) -> None:
        self.query_one("#search-bar").focus()

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    TheBinderApp().run()
