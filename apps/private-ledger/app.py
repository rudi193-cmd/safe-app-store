"""
Private Ledger — local-first financial ledger. b17: SAPS1

No cloud. No subscriptions. Your numbers, on your machine.

Usage:
  python3 app.py
"""
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

DB_PATH = Path.home() / ".willow" / "private-ledger.db"

CATEGORIES = [
    "income", "housing", "food", "transport", "health",
    "utilities", "entertainment", "savings", "other",
]


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date  TEXT NOT NULL,
            description TEXT NOT NULL,
            amount      REAL NOT NULL,
            direction   TEXT NOT NULL CHECK(direction IN ('in','out')),
            category    TEXT NOT NULL DEFAULT 'other',
            created     INTEGER NOT NULL
        )
    """)
    conn.commit()
    return conn


def all_entries() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM entries ORDER BY entry_date DESC, id DESC"
        )]


def add_entry(entry_date: str, description: str, amount: float,
              direction: str, category: str) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO entries (entry_date,description,amount,direction,category,created) "
            "VALUES (?,?,?,?,?,?)",
            (entry_date, description, amount, direction, category, int(time.time()))
        )
        return cur.lastrowid


def delete_entry(entry_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM entries WHERE id=?", (entry_id,))


def balance(entries: list[dict]) -> float:
    return sum(e["amount"] if e["direction"] == "in" else -e["amount"] for e in entries)


class AddEntryScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        cats = [(c.title(), c) for c in CATEGORIES]
        dirs = [("Money in  (+)", "in"), ("Money out (-)", "out")]
        yield Vertical(
            Label("Add Entry", id="modal-title"),
            Label("Date (YYYY-MM-DD)"),
            Input(value=str(date.today()), id="date-input"),
            Label("Description"),
            Input(placeholder="Rent, salary, groceries…", id="desc-input"),
            Label("Amount"),
            Input(placeholder="0.00", id="amount-input"),
            Select(dirs,  id="dir-select",  value="out"),
            Select(cats,  id="cat-select",  value="other"),
            Horizontal(
                Button("Add", variant="primary", id="add-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        try:
            entry_date  = self.query_one("#date-input",   Input).value.strip()
            description = self.query_one("#desc-input",   Input).value.strip()
            amount      = float(self.query_one("#amount-input", Input).value.strip() or "0")
            direction   = str(self.query_one("#dir-select", Select).value)
            category    = str(self.query_one("#cat-select", Select).value)
        except (ValueError, TypeError):
            return
        if not description or amount <= 0:
            return
        self.dismiss({
            "entry_date": entry_date, "description": description,
            "amount": amount, "direction": direction, "category": category,
        })


class PrivateLedgerApp(App):
    CSS = """
    #modal-content { background: $surface; border: solid $primary; padding: 1 2; width: 64; height: auto; }
    #modal-title   { text-style: bold; margin-bottom: 1; }
    AddEntryScreen { align: center middle; }
    #balance-bar   { height: 3; padding: 0 1; color: $success; }
    DataTable      { height: 1fr; }
    #status        { height: 1; color: $text-muted; padding: 0 1; }
    """

    BINDINGS = [
        Binding("n", "add_entry",    "New"),
        Binding("d", "delete_entry", "Delete"),
        Binding("r", "refresh",      "Refresh"),
        Binding("q", "quit",         "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._entry_ids: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="balance-bar")
        yield DataTable(id="ledger")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Private Ledger"
        self.sub_title = "local · private · yours"
        self._refresh()

    def _refresh(self) -> None:
        entries = all_entries()
        self._entry_ids = [e["id"] for e in entries]
        table = self.query_one("#ledger", DataTable)
        table.clear(columns=True)
        table.add_columns("Date", "Description", "Category", "Amount")
        for e in entries:
            sign = "+" if e["direction"] == "in" else "-"
            table.add_row(
                e["entry_date"],
                e["description"][:30],
                e["category"],
                f"{sign}${e['amount']:.2f}",
            )
        bal = balance(entries)
        sign = "+" if bal >= 0 else ""
        self.query_one("#balance-bar", Static).update(
            f"Balance: {sign}${bal:.2f}   ({len(entries)} entries)"
        )
        self.query_one("#status", Static).update("n=new  d=delete  q=quit")

    def action_add_entry(self) -> None:
        def on_dismiss(result):
            if result:
                add_entry(**result)
                self._refresh()
        self.push_screen(AddEntryScreen(), on_dismiss)

    def action_delete_entry(self) -> None:
        table = self.query_one("#ledger", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._entry_ids):
            delete_entry(self._entry_ids[row])
            self._refresh()

    def action_refresh(self) -> None:
        self._refresh()

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    PrivateLedgerApp().run()
