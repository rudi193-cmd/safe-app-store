"""Source Trail TUI — paste text, verify claims, browse history."""

from __future__ import annotations

import sys
import os
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static, TextArea
from textual import work

# safe_integration lives one level up (apps/source-trail/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import safe_integration as _si


class ClaimItem(ListItem):
    def __init__(self, claim: dict[str, Any]) -> None:
        super().__init__()
        self._claim = claim

    def compose(self) -> ComposeResult:
        matched = self._claim.get("matched", False)
        icon = "✓" if matched else "✗"
        color = "green" if matched else "red"
        conf = self._claim.get("confidence")
        conf_str = f"{conf:.2f}" if conf is not None else "—"
        source = self._claim.get("source", "—")
        text = (self._claim.get("claim") or "")[:72]
        yield Static(f"[{color}]{icon}[/] {text}\n    [dim]{source}[/] conf={conf_str}")


class HistoryItem(ListItem):
    def __init__(self, row: dict[str, Any]) -> None:
        super().__init__()
        self._row = row

    def compose(self) -> ComposeResult:
        matched = self._row.get("matched", False)
        icon = "✓" if matched else "✗"
        color = "green" if matched else "dim"
        text = (self._row.get("claim_text") or "")[:60]
        doc = self._row.get("document_ref") or ""
        doc_str = f"[dim]{doc}[/] " if doc else ""
        yield Static(f"[{color}]{icon}[/] {doc_str}{text}")


class SourceTrailApp(App):
    """Source Trail — Claim Verifier."""

    TITLE = "SOURCE TRAIL"
    SUB_TITLE = "Claim Verifier"

    CSS = """
    Screen {
        background: #0d0d0d;
    }
    #input-label {
        height: 1;
        color: #9a7b3c;
        margin: 0 1;
    }
    TextArea {
        height: 8;
        border: solid #2a2a2a;
        margin: 0 1;
    }
    #status {
        height: 1;
        color: #666;
        margin: 0 1;
    }
    #panels {
        height: 1fr;
        margin: 0 1;
    }
    #claims-panel {
        width: 2fr;
        border: solid #2a2a2a;
        margin-right: 1;
    }
    #history-panel {
        width: 1fr;
        border: solid #2a2a2a;
    }
    .panel-label {
        height: 1;
        background: #1a1a1a;
        color: #9a7b3c;
        padding: 0 1;
    }
    ListView {
        background: transparent;
    }
    ListItem {
        padding: 0 1;
        height: auto;
    }
    ListItem:hover {
        background: #1a1510;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "verify", "Verify"),
        Binding("ctrl+l", "clear_input", "Clear"),
        Binding("ctrl+h", "load_history", "History"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Paste text below — Ctrl+R to verify", id="input-label")
        yield TextArea(id="input")
        yield Static("", id="status")
        with Horizontal(id="panels"):
            with Vertical(id="claims-panel"):
                yield Static("CLAIMS", classes="panel-label")
                yield ListView(id="claims-list")
            with Vertical(id="history-panel"):
                yield Static("HISTORY", classes="panel-label")
                yield ListView(id="history-list")
        yield Footer()

    def on_mount(self) -> None:
        self._load_history()

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def action_clear_input(self) -> None:
        self.query_one("#input", TextArea).clear()
        self.query_one("#claims-list", ListView).clear()
        self._set_status("")

    def action_load_history(self) -> None:
        self._load_history()

    @work(thread=True)
    def _load_history(self) -> None:
        rows = _si.query("", limit=20)
        list_view = self.query_one("#history-list", ListView)
        self.call_from_thread(list_view.clear)
        for row in rows:
            self.call_from_thread(list_view.append, HistoryItem(row))

    def action_verify(self) -> None:
        text = self.query_one("#input", TextArea).text.strip()
        if not text:
            self._set_status("Nothing to verify.")
            return
        self._set_status("[yellow]Verifying…[/]")
        self.query_one("#claims-list", ListView).clear()
        self._run_verify(text)

    @work(thread=True)
    def _run_verify(self, text: str) -> None:
        result = _si.verify(text)

        if not result.get("ok"):
            err = result.get("error", "unknown error")
            self.call_from_thread(self._set_status, f"[red]Error:[/] {err}")
            return

        claims = result.get("claims", [])
        matched = result.get("matched", 0)
        total = result.get("total", 0)
        stored = result.get("stored", 0)

        claims_view = self.query_one("#claims-list", ListView)
        for claim in claims:
            self.call_from_thread(claims_view.append, ClaimItem(claim))

        self.call_from_thread(
            self._set_status,
            f"[green]{matched}[/]/{total} matched · {stored} stored",
        )
        self._load_history()


def main() -> None:
    SourceTrailApp().run()
