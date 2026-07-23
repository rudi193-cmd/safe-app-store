"""
Oakenscroll's Office — where certainty gets graded. b17: OAKOF

Local-first calibration ledger. No cloud required.

Usage:
  python3 app.py
"""
import time
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

import almanac_seam
import calibration
import office_db as db

try:                       # the one-memory seam — optional, standalone-safe
    import fleet_presence as _fleet
except ImportError:
    _fleet = None

VIEWS = ("open", "resolved", "scorecard")
VIEW_TITLES = {"open": "On the record", "resolved": "Graded", "scorecard": "The scorecard"}
_DAY = 86400
_DUE_UNITS = {"d": _DAY, "w": 7 * _DAY, "m": 30 * _DAY}


def parse_due(text: str) -> Optional[int]:
    """'+3d', '+2w', '+1m' → epoch seconds; blank → open-ended."""
    text = text.strip().lower()
    if not text:
        return None
    if text.startswith("+") and text[-1] in _DUE_UNITS and text[1:-1].isdigit():
        return int(time.time()) + int(text[1:-1]) * _DUE_UNITS[text[-1]]
    raise ValueError("due looks like +3d, +2w, or +1m")


def parse_confidence(text: str) -> float:
    """'7' → 0.7 · '85' → 0.85 · '0.6' → 0.6. Enforces the house convention
    (P(true) in 50–99%) here at the prompt, not three steps later."""
    text = text.strip()
    if text.isdigit():
        n = int(text)
        value = n / 10 if len(text) == 1 else n / 100
    else:
        value = float(text)
    if not (0.5 <= value <= 0.99):
        raise ValueError("confidence lives in 50–99% — state the claim in the direction you believe")
    return value


def when(ts: Optional[int]) -> str:
    if ts is None:
        return "—"
    delta = ts - int(time.time())
    sign, delta = ("-", -delta) if delta < 0 else ("", delta)
    if delta < _DAY:
        return f"{sign}{max(delta // 3600, 1)}h"
    return f"{sign}{delta // _DAY}d"


def spark(fraction: Optional[float], width: int = 10) -> str:
    if fraction is None:
        return " " * width
    filled = round(fraction * width)
    return "█" * filled + "·" * (width - filled)


class OfficeApp(App):
    TITLE = "Oakenscroll's Office"
    CSS = """
    #dew     { padding: 0 1; border: round $warning; height: auto; min-height: 3; display: none; }
    #dew.visible { display: block; }
    #board   { height: 1fr; }
    #card    { height: 1fr; padding: 1 2; display: none; }
    #card.visible { display: block; }
    #status  { padding: 0 1; color: $text-muted; height: 1; }
    #capture { display: none; }
    #capture.visible { display: block; }
    """
    BINDINGS = [
        Binding("n", "state_claim", "State a claim"),
        Binding("t", "resolve_true", "True"),
        Binding("f", "resolve_false", "False"),
        Binding("o", "resolve_void", "Void"),
        Binding("s", "snooze", "Snooze"),
        Binding("e", "cite", "Cite & grade"),
        Binding("c", "revise", "Change mind"),
        Binding("tab", "cycle_view", "View", priority=True),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.view = "open"
        self.mode: Optional[str] = None    # None | claim | confidence | due | revise | cite
        self.draft: dict = {}
        self.dew: list[dict] = []          # due predictions awaiting the person
        self.snoozed: set[str] = set()
        self.citing_pid: Optional[str] = None   # cite-and-grade in progress
        self.candidates: list[dict] = []        # almanac sources on the board

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("", id="dew")
            yield DataTable(id="board")
            yield Static("", id="card")
            yield Static("", id="status")
            yield Input(id="capture")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#board", DataTable).cursor_type = "row"
        self.reload_dew()
        self.refresh_all()

    # ---------- the dew: due predictions surface one at a time ----------

    def reload_dew(self) -> None:
        self.dew = [d for d in db.due_now() if d["id"] not in self.snoozed]

    def active_due(self) -> Optional[dict]:
        return self.dew[0] if self.dew else None

    def render_dew(self) -> None:
        panel = self.query_one("#dew", Static)
        item = self.active_due()
        if not item:
            panel.remove_class("visible")
            return
        panel.add_class("visible")
        panel.update(
            f"[b]Due ({len(self.dew)} waiting):[/b] {item['claim']}\n"
            f"You said [b]{item['confidence']:.0%}[/b] — "
            "[b]t[/b]rue · [b]f[/b]alse · v[b]o[/b]id · [b]s[/b]nooze"
        )

    # ---------- rendering ----------

    def refresh_all(self) -> None:
        self.render_dew()
        board = self.query_one("#board", DataTable)
        card = self.query_one("#card", Static)
        if self.citing_pid and self.candidates:
            board.display = True
            card.remove_class("visible")
            self.render_candidates()
        elif self.view == "scorecard":
            board.display = False
            card.add_class("visible")
            card.update(self.scorecard_text())
        else:
            board.display = True
            card.remove_class("visible")
            self.render_board()
        self.render_status()
        self.announce_presence()

    def announce_presence(self) -> None:
        """Publish this ledger's calibration into the one memory (no-op if no
        shared store, no-op if the seam isn't installed)."""
        if _fleet is None:
            return
        s = calibration.summary(db.resolved_pairs())
        n = s["n"]
        summary = (f"{n} graded, brier {s['brier']:.2f}" if n else "no graded predictions yet")
        _fleet.announce(
            "oakenscrolls-office", summary,
            {"graded": n, "open": len(db.ledger("open"))},
        )

    def render_candidates(self) -> None:
        """The pick board: almanac sources matching the cite query. Selecting
        one and pressing t/f grades the prediction with that citation."""
        board = self.query_one("#board", DataTable)
        board.clear(columns=True)
        board.add_columns("vertical", "source", "publisher", "status")
        for i, c in enumerate(self.candidates):
            board.add_row(
                c["vertical"], c["title"] or c["entry_id"], c["publisher"] or "—",
                c["status"] or "?", key=str(i),
            )
        board.focus()

    def render_board(self) -> None:
        board = self.query_one("#board", DataTable)
        board.clear(columns=True)  # the cite flow swaps the column set
        board.add_columns("conf", "claim", "due", "age", "rev")
        if self.view == "open":
            for r in db.ledger("open"):
                board.add_row(
                    f"{r['confidence']:.0%}", r["claim"], when(r["due"]),
                    when(r["stated_at"]).lstrip("-"), str(r["revisions"]) or "0",
                    key=r["id"],
                )
        else:
            for r in db.ledger():
                if r["status"] == "open":
                    continue
                verdict = "VOID" if r["status"] == "voided" else ("✓" if r["outcome"] else "✗")
                if r["evidence"]:
                    verdict += " †"  # graded with a citation
                board.add_row(
                    f"{r['confidence']:.0%}", r["claim"], verdict,
                    when(r["resolved_at"]).lstrip("-"), str(r["revisions"]),
                    key=r["id"],
                )

    def scorecard_text(self) -> str:
        pairs = db.resolved_pairs()
        s = calibration.summary(pairs)
        if not s["n"]:
            return (
                "[dim]No graded predictions yet.\n\n"
                "State claims ([b]n[/b]), let the world weigh in, "
                "and the curve appears here.[/dim]"
            )
        lines = [
            f"[b]Graded:[/b] {s['n']}   [b]Brier:[/b] {s['brier']:.3f}   "
            f"[b]Log:[/b] {s['log_score']:.3f}",
            f"[b]You say[/b] {s['mean_confidence']:.0%} · [b]you deliver[/b] {s['hit_rate']:.0%} · "
            + (
                f"[b]overconfident by {s['overconfidence']:+.0%}[/b]"
                if s["overconfidence"] > 0.02 else
                f"[b]underconfident by {s['overconfidence']:+.0%}[/b]"
                if s["overconfidence"] < -0.02 else
                "[b]well calibrated[/b]"
            ),
            "",
            "  stated      said   hit    n",
        ]
        for b in calibration.bins(pairs):
            label = f"{b['lo']:.0%}–{b['hi']:.0%}"
            if b["n"]:
                lines.append(
                    f"  {label:<10} {b['mean_confidence']:>5.0%} {b['hit_rate']:>5.0%} "
                    f"{b['n']:>4}  {spark(b['hit_rate'])}"
                )
            else:
                lines.append(f"  {label:<10} [dim]— unspoken —[/dim]")
        return "\n".join(lines)

    def render_status(self) -> None:
        if self.citing_pid and self.candidates:
            claim = db.current(self.citing_pid)["claim"]
            self.query_one("#status", Static).update(
                f"Citing for: “{claim}” — pick a source, then [b]t[/b]/[b]f[/b] · Esc cancels"
            )
            return
        n_open = len(db.ledger("open"))
        n_res = len(db.ledger("resolved"))
        self.query_one("#status", Static).update(
            f"{VIEW_TITLES[self.view]} · {n_open} on the record · {n_res} graded · ΔΣ=42"
        )

    # ---------- selection ----------

    def selected_id(self) -> Optional[str]:
        if self.view == "scorecard":
            return None
        board = self.query_one("#board", DataTable)
        if board.row_count == 0:
            return None
        try:
            return board.coordinate_to_cell_key(board.cursor_coordinate).row_key.value
        except Exception:
            return None

    def target_id(self) -> Optional[str]:
        """t/f/o act on the surfaced due item first, else the selected open row."""
        item = self.active_due()
        if item:
            return item["id"]
        return self.selected_id() if self.view == "open" else None

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
        self.draft = {}
        box = self.query_one("#capture", Input)
        box.remove_class("visible")
        self.query_one("#board", DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        try:
            if self.mode == "claim":
                if not text:
                    self.close_input()
                    return
                self.draft = {"claim": text}
                self.open_input("confidence", "How sure? 5–9 → 50–90%, or exact like 85 — Esc cancels")
            elif self.mode == "confidence":
                self.draft["confidence"] = parse_confidence(text)
                self.open_input("due", "Due? +3d / +2w / +1m, or Enter for open-ended")
            elif self.mode == "due":
                db.state_claim(self.draft["claim"], self.draft["confidence"], parse_due(text))
                self.close_input()
                self.reload_dew()
                self.refresh_all()
            elif self.mode == "revise":
                pid = self.draft.get("pid")
                if pid:
                    db.revise(pid, parse_confidence(text))
                self.close_input()
                self.refresh_all()
            elif self.mode == "cite":
                if not text:
                    self.citing_pid = None
                    self.close_input()
                    self.refresh_all()
                    return
                found = almanac_seam.search(text)
                if not found:
                    box = self.query_one("#capture", Input)
                    box.placeholder = (
                        "nothing matched in the local almanacs — refine, or Esc to grade unciteds"
                        if almanac_seam.verticals()
                        else "no local almanac clones found (set ALMANAC_DATA_ROOT) — Esc cancels"
                    )
                    box.value = ""
                    return
                self.candidates = found
                self.close_input()
                self.refresh_all()
        except (ValueError, KeyError) as err:
            self.query_one("#capture", Input).placeholder = f"{err} — try again, Esc cancels"
            self.query_one("#capture", Input).value = ""

    def on_key(self, event) -> None:
        if event.key != "escape":
            return
        if self.mode:
            if self.mode == "cite":
                self.citing_pid = None
            self.close_input()
            self.refresh_all()
        elif self.citing_pid:
            self.citing_pid = None
            self.candidates = []
            self.refresh_all()

    # ---------- actions ----------

    def action_state_claim(self) -> None:
        if not self.mode:
            self.open_input("claim", "State the claim, in the direction you believe — Esc cancels")

    def _grade(self, outcome: Optional[bool], voided: bool = False) -> None:
        if self.mode:
            return
        if self.citing_pid and self.candidates:
            if voided:  # a void needs no citation
                return
            picked = self.selected_id()
            try:
                candidate = self.candidates[int(picked)]
            except (TypeError, ValueError, IndexError):
                return
            try:
                db.resolve(self.citing_pid, bool(outcome),
                           evidence=almanac_seam.citation(candidate))
            except (ValueError, KeyError):
                pass
            self.citing_pid = None
            self.candidates = []
            self.reload_dew()
            self.refresh_all()
            return
        pid = self.target_id()
        if not pid:
            return
        try:
            if voided:
                db.void(pid)
            else:
                db.resolve(pid, bool(outcome))
        except (ValueError, KeyError):
            return
        self.reload_dew()
        self.refresh_all()

    def action_resolve_true(self) -> None:
        self._grade(True)

    def action_resolve_false(self) -> None:
        self._grade(False)

    def action_resolve_void(self) -> None:
        self._grade(None, voided=True)

    def action_cite(self) -> None:
        """Cite & grade: search the local almanac-data clones for the source
        that settles this claim, then t/f with the citation pinned."""
        if self.mode or self.citing_pid:
            return
        pid = self.target_id()
        if not pid:
            return
        self.citing_pid = pid
        self.open_input("cite", "Which source settles it? Search the local almanacs — Esc cancels")

    def action_snooze(self) -> None:
        item = self.active_due()
        if item:
            self.snoozed.add(item["id"])
            self.reload_dew()
            self.refresh_all()

    def action_revise(self) -> None:
        if self.mode or self.view != "open":
            return
        pid = self.selected_id()
        if pid:
            self.draft = {"pid": pid}
            self.open_input("revise", "New confidence (the old one stays on the record) — Esc cancels")

    def action_cycle_view(self) -> None:
        if self.mode:
            return
        self.view = VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        self.refresh_all()


def main() -> None:
    OfficeApp().run()


if __name__ == "__main__":
    main()
