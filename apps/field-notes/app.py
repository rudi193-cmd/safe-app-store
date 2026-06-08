"""
Field Notes — local-first notes app. b17: SAPS1

Plain text. Yours forever. No cloud required.

Usage:
  python3 app.py
"""
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Label, Static, TextArea

DB_PATH = Path.home() / ".willow" / "field-notes.db"


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            title   TEXT NOT NULL DEFAULT 'Untitled',
            body    TEXT NOT NULL DEFAULT '',
            created INTEGER NOT NULL,
            updated INTEGER NOT NULL
        )
    """)
    conn.commit()
    return conn


def all_notes() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, title, created, updated FROM notes ORDER BY updated DESC"
        )]


def get_note(note_id: int) -> Optional[dict]:
    with _db() as c:
        row = c.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return dict(row) if row else None


def save_note(title: str, body: str, note_id: Optional[int] = None) -> int:
    now = int(time.time())
    with _db() as c:
        if note_id:
            c.execute(
                "UPDATE notes SET title=?, body=?, updated=? WHERE id=?",
                (title, body, now, note_id)
            )
            return note_id
        cur = c.execute(
            "INSERT INTO notes (title, body, created, updated) VALUES (?,?,?,?)",
            (title, body, now, now)
        )
        return cur.lastrowid


def delete_note(note_id: int) -> bool:
    with _db() as c:
        c.execute("DELETE FROM notes WHERE id=?", (note_id,))
        return True


class FieldNotesApp(App):
    CSS = """
    #sidebar   { width: 32; border-right: solid $primary; }
    #main      { width: 1fr; }
    #title-bar { height: 3; padding: 0 1; }
    #body-area { height: 1fr; }
    #status    { height: 1; color: $text-muted; padding: 0 1; }
    DataTable  { height: 1fr; }
    """

    BINDINGS = [
        Binding("n",      "new_note",    "New"),
        Binding("s",      "save_note",   "Save"),
        Binding("d",      "delete_note", "Delete"),
        Binding("escape", "focus_list",  "List"),
        Binding("q",      "quit",        "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._current_id: Optional[int] = None
        self._note_ids: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Horizontal(
            Vertical(
                DataTable(id="note-list"),
                id="sidebar",
            ),
            Vertical(
                Input(placeholder="Title", id="title-bar"),
                TextArea("", id="body-area"),
                Static("", id="status"),
                id="main",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Field Notes"
        self.sub_title = "local · private · yours"
        self._refresh_list()
        self.query_one("#note-list").focus()

    def _refresh_list(self) -> None:
        table = self.query_one("#note-list", DataTable)
        table.clear(columns=True)
        table.add_columns("Title")
        notes = all_notes()
        self._note_ids = [n["id"] for n in notes]
        for n in notes:
            table.add_row(n["title"][:28])
        self._set_status(f"{len(notes)} note(s)")

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _load_selected(self) -> None:
        table = self.query_one("#note-list", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._note_ids):
            return
        note = get_note(self._note_ids[row])
        if not note:
            return
        self._current_id = note["id"]
        self.query_one("#title-bar", Input).value = note["title"]
        self.query_one("#body-area", TextArea).load_text(note["body"])
        self._set_status(f"note #{note['id']}")

    def on_data_table_row_selected(self, _event) -> None:
        self._load_selected()
        self.query_one("#body-area").focus()

    def action_new_note(self) -> None:
        self._current_id = None
        self.query_one("#title-bar", Input).value = ""
        self.query_one("#body-area", TextArea).load_text("")
        self.query_one("#title-bar").focus()
        self._set_status("new note — press s to save")

    def action_save_note(self) -> None:
        title = self.query_one("#title-bar", Input).value.strip() or "Untitled"
        body  = self.query_one("#body-area", TextArea).text
        self._current_id = save_note(title, body, self._current_id)
        self._refresh_list()
        self._set_status(f"saved: {title}")

    def action_delete_note(self) -> None:
        if self._current_id:
            delete_note(self._current_id)
            self._current_id = None
            self.query_one("#title-bar", Input).value = ""
            self.query_one("#body-area", TextArea).load_text("")
            self._refresh_list()

    def action_focus_list(self) -> None:
        self.query_one("#note-list").focus()

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    FieldNotesApp().run()
