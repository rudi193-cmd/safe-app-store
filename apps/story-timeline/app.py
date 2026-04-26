"""
Story Timeline — quick and dirty narrative timeline tracker.
Built by Professor Oakenscroll for the r/LLMPhysics community.
Free. Local. No $70 subscription required.

Run: python3 app.py
"""
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    DataTable, Footer, Header, Input, Label,
    Button, Select, Static, TextArea
)
from textual.screen import ModalScreen

import timeline_db as db


STORIES = []


def _refresh_stories():
    global STORIES
    STORIES = db.get_stories()


class AddEventScreen(ModalScreen):
    """Modal form for adding a new event."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        _refresh_stories()
        story_opts = [(s, s) for s in STORIES] + [("+ New story", "__new__")]
        yield Vertical(
            Label("Add Timeline Event", id="modal-title"),
            Label("Story"),
            Select(story_opts, id="story-select", value=STORIES[0] if STORIES else "__new__"),
            Input(placeholder="New story name (if above is '+ New story')", id="new-story"),
            Label("In-world date (e.g. Day 3, Year 412, 2031-06-15)"),
            Input(placeholder="World date", id="world-date"),
            Label("Location"),
            Input(placeholder="Location", id="location"),
            Label("Characters (comma-separated)"),
            Input(placeholder="Alice, Bob, The Stranger", id="characters"),
            Label("Summary"),
            TextArea(id="summary"),
            Horizontal(
                Button("Add Event", variant="primary", id="add-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        story_val = self.query_one("#story-select", Select).value
        if story_val == "__new__":
            story_val = self.query_one("#new-story", Input).value.strip() or "default"
        world_date = self.query_one("#world-date", Input).value.strip()
        location = self.query_one("#location", Input).value.strip()
        chars_raw = self.query_one("#characters", Input).value.strip()
        characters = [c.strip() for c in chars_raw.split(",") if c.strip()]
        summary = self.query_one("#summary", TextArea).text.strip()
        if not world_date or not summary:
            return
        db.add_event(
            story=story_val,
            world_date=world_date,
            location=location,
            characters=characters,
            summary=summary,
        )
        self.dismiss(True)


class TimelineApp(App):
    CSS = """
    #modal-content {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 70;
        height: auto;
        max-height: 90vh;
    }
    #modal-title { text-style: bold; margin-bottom: 1; }
    AddEventScreen { align: center middle; }
    #filter-bar { height: 3; }
    #story-filter { width: 30; }
    #char-filter { width: 30; }
    #status { height: 1; color: $text-muted; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("a", "add_event", "Add event"),
        Binding("d", "delete_event", "Delete"),
        Binding("e", "export", "Export MD"),
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self._current_story = None
        self._current_char = None

    def compose(self) -> ComposeResult:
        _refresh_stories()
        story_opts = [("All stories", "__all__")] + [(s, s) for s in STORIES]
        yield Header(show_clock=True)
        yield Horizontal(
            Label("Story: "),
            Select(story_opts, id="story-filter", value="__all__"),
            Label("  Character: "),
            Input(placeholder="filter by character...", id="char-filter"),
            id="filter-bar",
        )
        yield DataTable(id="timeline-table")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Story Timeline"
        self.sub_title = "Professor Oakenscroll's Quick & Dirty Timeline Tracker"
        self._build_table()

    def _build_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("ID", "Date", "Location", "Characters", "Summary")
        story = None if self._current_story == "__all__" else self._current_story
        events = db.get_events(story=story, character=self._current_char or None)
        for e in events:
            chars = ", ".join(e["characters"][:3])
            if len(e["characters"]) > 3:
                chars += f" +{len(e['characters'])-3}"
            summary = e["summary"][:60] + ("…" if len(e["summary"]) > 60 else "")
            table.add_row(str(e["id"]), e["world_date"], e["location"] or "—", chars or "—", summary)
        status = self.query_one("#status", Static)
        status.update(f"{len(events)} event(s)" + (f"  |  story: {story}" if story else "") +
                      (f"  |  character: {self._current_char}" if self._current_char else ""))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "story-filter":
            self._current_story = None if event.value == "__all__" else event.value
            self._build_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "char-filter":
            self._current_char = event.value.strip() or None
            self._build_table()

    def action_add_event(self) -> None:
        def on_dismiss(result):
            if result:
                _refresh_stories()
                self._build_table()
        self.push_screen(AddEventScreen(), on_dismiss)

    def action_delete_event(self) -> None:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if row < 0:
            return
        cell = table.get_cell_at((row, 0))
        if cell and db.delete_event(int(cell)):
            self._build_table()

    def action_export(self) -> None:
        story = None if self._current_story == "__all__" else self._current_story
        md = db.export_markdown(story=story)
        name = f"timeline-{story or 'all'}.md"
        import pathlib
        out = pathlib.Path.home() / "Desktop" / name
        out.write_text(md)
        self.query_one("#status", Static).update(f"Exported → {out}")

    def action_refresh(self) -> None:
        _refresh_stories()
        self._build_table()


if __name__ == "__main__":
    TimelineApp().run()
