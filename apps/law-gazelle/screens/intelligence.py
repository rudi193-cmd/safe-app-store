"""AI result viewer — review-only; save is explicit from parent."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class IntelligenceScreen(ModalScreen):
    """Show local LLM output (briefing, draft, or ranking)."""

    BINDINGS = [("escape", "close", "Close")]

    DEFAULT_CSS = """
    IntelligenceScreen {
        align: center middle;
    }
    #intel-container {
        width: 95%;
        height: 92%;
        max-width: 120;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    #intel-title {
        text-style: bold;
        height: auto;
        margin-bottom: 1;
    }
    #intel-meta {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #intel-scroll {
        height: 1fr;
        border: solid $primary-darken-2;
    }
    #intel-body {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        title: str,
        body: str,
        *,
        meta: str = "",
        suggested_filename: str | None = None,
        draft_body: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._meta = meta
        self._suggested_filename = suggested_filename
        self._draft_body = draft_body

    def compose(self) -> ComposeResult:
        with Vertical(id="intel-container"):
            yield Static(self._title, id="intel-title")
            if self._meta:
                yield Static(self._meta, id="intel-meta")
            with VerticalScroll(id="intel-scroll"):
                yield Static(self._body, id="intel-body")
            if self._suggested_filename and self._draft_body:
                yield Button(
                    f"Save draft to Nest ({self._suggested_filename})",
                    id="intel-save",
                    variant="warning",
                )
            yield Button("Close (Esc)", id="intel-close", variant="primary")

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "intel-close":
            self.dismiss()
        elif event.button.id == "intel-save" and self._draft_body and self._suggested_filename:
            import document_store

            result = document_store.save_document(
                self._suggested_filename,
                self._draft_body,
                dest="nest",
            )
            if result.get("ok"):
                self.app.notify(f"Saved → {result.get('path')}", severity="information")
                self.dismiss()
            else:
                self.app.notify(result.get("error", "Save failed"), severity="error")
