"""Textual screens for Law Gazelle detail views and modals."""

from __future__ import annotations

from datetime import date, timedelta

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, TextArea, Input

from case_store import format_detail_text, get_item_detail


class DetailScreen(ModalScreen):
    """Full-item detail view."""

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    DEFAULT_CSS = """
    DetailScreen {
        align: center middle;
    }
    #detail-container {
        width: 92%;
        height: 92%;
        max-width: 120;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #detail-title {
        text-style: bold;
        height: auto;
        margin-bottom: 1;
    }
    #detail-scroll {
        height: 1fr;
        border: solid $primary-darken-2;
    }
    #detail-body {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    #detail-close {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, source_db: str, item_type: str, item_id: str) -> None:
        super().__init__()
        self.source_db = source_db
        self.item_type = item_type
        self.item_id = item_id
        detail = get_item_detail(source_db, item_type, item_id)
        self._title = f"{item_type.upper()} · {item_id}"
        self._text = format_detail_text(detail)

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-container"):
            yield Static(self._title, id="detail-title")
            with VerticalScroll(id="detail-scroll"):
                yield Static(self._text, id="detail-body")
            yield Button("Close (Esc)", id="detail-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "detail-close":
            self.dismiss()


class NoteModal(ModalScreen[str | None]):
    """Add a note to the selected item."""

    DEFAULT_CSS = """
    NoteModal {
        align: center middle;
    }
    #note-modal {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #note-body {
        height: 12;
        margin: 1 0;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, source_db: str, item_type: str, item_id: str) -> None:
        super().__init__()
        self.source_db = source_db
        self.item_type = item_type
        self.item_id = item_id

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"Note for {self.item_type} {self.item_id}"),
            TextArea(id="note-body"),
            Button("Save", variant="primary", id="save-note"),
            Button("Cancel", id="cancel-note"),
            id="note-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-note":
            self.dismiss(None)
            return
        body = self.query_one("#note-body", TextArea).text.strip()
        self.dismiss(body or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SnoozeModal(ModalScreen[str | None]):
    """Snooze item until a date (YYYY-MM-DD) or preset."""

    DEFAULT_CSS = """
    SnoozeModal {
        align: center middle;
    }
    #snooze-modal {
        width: 50;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        default = (date.today() + timedelta(days=7)).isoformat()
        yield Vertical(
            Label("Snooze until (YYYY-MM-DD)"),
            Input(value=default, id="snooze-date"),
            Button("1 day", id="snooze-1d"),
            Button("1 week", id="snooze-1w"),
            Button("Apply", variant="primary", id="snooze-apply"),
            Button("Cancel", id="snooze-cancel"),
            id="snooze-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "snooze-cancel":
            self.dismiss(None)
            return
        if event.button.id == "snooze-1d":
            self.dismiss((date.today() + timedelta(days=1)).isoformat())
            return
        if event.button.id == "snooze-1w":
            self.dismiss((date.today() + timedelta(days=7)).isoformat())
            return
        val = self.query_one("#snooze-date", Input).value.strip()
        self.dismiss(val or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
