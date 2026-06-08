"""Workflow screens — drafting packet viewer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class PacketScreen(ModalScreen):
    """Show drafting packet markdown for an action card."""

    BINDINGS = [("escape", "close", "Close")]

    DEFAULT_CSS = """
    PacketScreen {
        align: center middle;
    }
    #packet-container {
        width: 95%;
        height: 92%;
        max-width: 120;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #packet-title {
        text-style: bold;
        height: auto;
        margin-bottom: 1;
    }
    #packet-scroll {
        height: 1fr;
        border: solid $primary-darken-2;
    }
    #packet-body {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="packet-container"):
            yield Static(self._title, id="packet-title")
            with VerticalScroll(id="packet-scroll"):
                yield Static(self._body, id="packet-body")
            yield Button("Close (Esc)", id="packet-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "packet-close":
            self.dismiss()
