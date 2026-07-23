"""
The Nightstand — set heavy things down; pick up one bite. b17: NSTND

Local-first load triage. No cloud required.

Usage:
  python3 app.py
"""
import time
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

import nightstand_db as db

WEIGHT_GLYPH = {"heavy": "###", "medium": "## ", "light": "#  "}
VIEWS = ("down", "done", "archived")
VIEW_TITLES = {"down": "On the nightstand", "done": "Done", "archived": "Archived"}


def age(ts: int) -> str:
    delta = int(time.time()) - ts
    if delta < 3600:
        return f"{max(delta // 60, 1)}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


class NightstandApp(App):
    TITLE = "The Nightstand"
    CSS = """
    #inhand  { padding: 0 1; border: round $primary; height: auto; min-height: 3; }
    #things  { height: 1fr; }
    #status  { padding: 0 1; color: $text-muted; height: 1; }
    #capture { display: none; }
    #capture.visible { display: block; }
    """
    BINDINGS = [
        Binding("n", "set_down", "Set one down"),
        Binding("1", "hand_me_one", "Hand me one"),
        Binding("enter", "pick_up", "Pick up", priority=False),
        Binding("d", "done", "Done"),
        Binding("b", "set_back", "Back down"),
        Binding("a", "archive", "Archive"),
        Binding("v", "cycle_view", "View"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.view = "down"
        self.mode: Optional[str] = None       # None | "capture" | "bite"
        self.pending_id: Optional[int] = None  # thing awaiting a bite

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("", id="inhand")
            yield DataTable(id="things")
            yield Static("", id="status")
            yield Input(id="capture")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#things", DataTable)
        table.cursor_type = "row"
        table.add_columns("wt", "what", "down for", "pickups")
        self.refresh_all()

    # ---------- rendering ----------

    def refresh_all(self) -> None:
        self.render_inhand()
        self.render_table()
        self.render_status()

    def render_inhand(self) -> None:
        held = db.in_hand()
        panel = self.query_one("#inhand", Static)
        if not held:
            panel.update(
                "[dim]Nothing in your hands. "
                "Press [b]1[/b] and the nightstand will hand you something small.[/dim]"
            )
            return
        bite = held["bite"] or "(no bite named — just start)"
        panel.update(
            f"[b]In your hands:[/b] {held['what']}\n"
            f"[b]The one bite:[/b] {bite}"
        )

    def render_table(self) -> None:
        table = self.query_one("#things", DataTable)
        table.clear()
        for t in db.list_things(self.view):
            table.add_row(
                WEIGHT_GLYPH.get(t["weight"], "## "),
                t["what"],
                age(t["set_down"]),
                str(t["pickups"]),
                key=str(t["id"]),
            )
        table.border_title = VIEW_TITLES[self.view]

    def render_status(self) -> None:
        c = db.counts()
        down = c.get("down", 0)
        heavy = c.get("heavy_down", 0)
        done = c.get("done", 0)
        self.query_one("#status", Static).update(
            f"{VIEW_TITLES[self.view]} · {down} down ({heavy} heavy) · {done} finished all-time"
        )

    # ---------- selection ----------

    def selected_id(self) -> Optional[int]:
        table = self.query_one("#things", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            return int(row_key.value)
        except Exception:
            return None

    # ---------- input modes ----------

    def open_input(self, mode: str, placeholder: str) -> None:
        self.mode = mode
        box = self.query_one("#capture", Input)
        box.placeholder = placeholder
        box.value = ""
        box.add_class("visible")
        box.focus()

    def close_input(self) -> None:
        self.mode = None
        box = self.query_one("#capture", Input)
        box.remove_class("visible")
        self.query_one("#things", DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if self.mode == "capture":
            if text:
                weight = "medium"
                if text.endswith("!"):
                    weight, text = "heavy", text.rstrip("!").strip()
                elif text.endswith("~"):
                    weight, text = "light", text.rstrip("~").strip()
                if text:
                    db.set_down(text, weight)
            self.close_input()
            self.refresh_all()
        elif self.mode == "bite":
            if self.pending_id is not None:
                db.pick_up(self.pending_id, text or None)
                self.pending_id = None
            self.close_input()
            self.refresh_all()

    def on_key(self, event) -> None:
        if self.mode and event.key == "escape":
            self.pending_id = None
            self.close_input()

    # ---------- actions ----------

    def action_set_down(self) -> None:
        self.open_input(
            "capture",
            "What's weighing on you? (end with ! if heavy, ~ if light) — Esc to cancel",
        )

    def _start_pickup(self, thing_id: int) -> None:
        self.pending_id = thing_id
        self.open_input(
            "bite",
            "What's the one bite? (Enter to skip, Esc to cancel)",
        )

    def action_pick_up(self) -> None:
        if self.mode or self.view != "down":
            return
        thing_id = self.selected_id()
        if thing_id is not None:
            self._start_pickup(thing_id)

    def action_hand_me_one(self) -> None:
        if self.mode:
            return
        offered = db.hand_me_one()
        if offered:
            self._start_pickup(offered["id"])

    def action_done(self) -> None:
        if self.mode:
            return
        held = db.in_hand()
        if held:
            db.mark_done(held["id"])
            self.refresh_all()

    def action_set_back(self) -> None:
        if self.mode:
            return
        held = db.in_hand()
        if held:
            db.set_back(held["id"])
            self.refresh_all()

    def action_archive(self) -> None:
        if self.mode or self.view == "archived":
            return
        thing_id = self.selected_id()
        if thing_id is not None:
            db.archive(thing_id)
            self.refresh_all()

    def action_cycle_view(self) -> None:
        if self.mode:
            return
        self.view = VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        self.refresh_all()


if __name__ == "__main__":
    NightstandApp().run()
