#!/usr/bin/env python3
"""Civics Check dashboard -- Textual TUI. America's 250th, with cards.

Usage:
  python3 tui.py
  make tui app=civics-check

Falls back to nothing gracefully: if textual isn't installed, this prints
a one-line message and exits. app.py (pure stdlib) always works regardless.
"""
from __future__ import annotations

import random
import time

import bell
import db
import engine

try:
    from rich.markup import escape
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

    TEXTUAL_OK = True
except ImportError:
    TEXTUAL_OK = False


MODES = [
    ("naturalization", "Naturalization quiz", "quiz"),
    ("missed", "Review missed questions", "quiz"),
    ("states", "State matchup", "states"),
    ("timeline", "Timeline sort", "timeline"),
    ("colonies", "13 Colonies flashcards", "browse"),
    ("on_this_day", "On This Day", "browse"),
    ("quotes", "Quote match", "quotes"),
    ("signers", "Declaration signers", "browse"),
    ("amendments", "Amendment explorer", "browse"),
    ("speed", "Speed round (60s)", "quiz"),
    ("duel", "Pass-the-keyboard duel", "duel"),
    ("stats", "Recent scores", "stats"),
]


def _colonies_cards():
    return [
        (c["name"], f"founded {c['founded']} by {c['founder']}", c["fact"], "")
        for c in engine.load_colonies()
    ]


def _signers_cards():
    return [
        (s["name"], s["state"], s["fact"], "") for s in engine.load_signers()
    ]


def _on_this_day_cards():
    events = engine.today_events()
    if not events:
        return [("No events today", "", "Try July 4th weekend for the good stuff.", "")]
    return [("On this day", "", e, "") for e in events]


def _amendments_cards():
    return [
        (f"Amendment {a['number']}", str(a["year"]), a["summary"], f"{a['year']}")
        for a in engine.load_amendments()
    ]


BROWSE_SOURCES = {
    "colonies": _colonies_cards,
    "on_this_day": _on_this_day_cards,
    "signers": _signers_cards,
    "amendments": _amendments_cards,
}


if TEXTUAL_OK:

    class CivicsCheckApp(App):
        """America's 250th, as a dashboard."""

        TITLE = "CIVICS CHECK"
        SUB_TITLE = "America's 250th -- 1776 * 2026"

        CSS = """
        Screen {
            layout: vertical;
        }

        #body {
            height: 1fr;
        }

        #sidebar {
            width: 30;
            border-right: solid $primary-darken-2;
        }

        #sidebar-header {
            height: 1;
            background: $primary-darken-3;
            color: $text;
            text-style: bold;
            padding: 0 1;
        }

        #mode-list {
            height: 1fr;
        }

        #main {
            width: 1fr;
            padding: 0 1;
        }

        #status-bar {
            height: 1;
            background: $panel;
            color: $text;
            text-style: bold;
            padding: 0 1;
        }

        #card {
            height: 1fr;
            border: heavy white;
            padding: 1 2;
            margin-top: 1;
        }

        #feedback {
            height: auto;
            max-height: 10;
            border: heavy $accent;
            padding: 1 2;
            margin-top: 1;
            display: none;
        }

        #answer-input {
            height: 3;
            margin-top: 1;
        }
        """

        BINDINGS = [
            Binding("ctrl+c", "quit", "Quit", show=True),
            Binding("ctrl+l", "focus_list", "Modes", show=True),
            Binding("escape", "focus_input", "Focus input", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.kind = None
            self.mode_key = None
            self.mode_name = ""
            self.pool = []
            self.index = 0
            self.score = 0
            self.total = 0
            self.start_time = None
            self.time_limit = None
            self.expected = []
            self.browse_items = []
            self.duel_players = ["Player 1", "Player 2"]
            self.duel_scores = {}
            self.duel_turn = 0
            self.awaiting_duel_setup = 0
            self.timeline_shuffled = []
            self.timeline_correct_order = []
            self.states_current = None
            self.quotes_current = None
            self.quotes_options = []

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with Vertical(id="sidebar"):
                    yield Static("  MODES", id="sidebar-header")
                    yield ListView(id="mode-list")
                with Vertical(id="main"):
                    yield Static("", id="status-bar")
                    yield Static(bell.EAGLE_PLAIN, id="card")
                    yield Static("", id="feedback")
                    yield Input(placeholder="pick a mode from the list", id="answer-input")
            yield Footer()

        def on_mount(self) -> None:
            mode_list = self.query_one("#mode-list", ListView)
            for key, label, _kind in MODES:
                mode_list.append(ListItem(Label(label), id=f"mode-{key}"))
            mode_list.index = 0
            mode_list.focus()
            self._update_status(f"welcome -- {bell.ticker_plain(engine.load_quotes())}")

        # ── Mode selection ──────────────────────────────────────────────────

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            idx = event.list_view.index
            if idx is None or idx >= len(MODES):
                return
            key, label, kind = MODES[idx]
            self._start_mode(key, label, kind)

        def _start_mode(self, key, label, kind):
            self.mode_key = key
            self.mode_name = label
            self.kind = kind
            self.index = 0
            self.score = 0
            self.total = 0
            self.start_time = time.time()
            self.time_limit = 60 if key == "speed" else None
            self._hide_feedback()

            if kind == "quiz":
                pool = engine.load_naturalization_questions()
                if key == "missed":
                    ids = db.missed_question_ids(limit=10)
                    if not ids:
                        self._render_card("Missed Questions", "Nothing missed yet -- clean slate.", "")
                        self._update_status("missed-review: nothing to show")
                        self.query_one("#answer-input", Input).placeholder = "pick another mode"
                        return
                    self.pool = engine.pick_questions(pool, len(ids), ids)
                elif key == "speed":
                    self.pool = engine.pick_questions(pool, 100)
                else:
                    self.pool = engine.pick_questions(pool, 10)
                self.total = len(self.pool)
                self._render_quiz_question()

            elif kind == "states":
                self.pool = engine.load_states()
                random.shuffle(self.pool)
                self.total = min(8, len(self.pool))
                self._render_states_question()

            elif kind == "quotes":
                self.pool = engine.load_quotes()
                random.shuffle(self.pool)
                self.total = min(6, len(self.pool))
                self._render_quote_question()

            elif kind == "browse":
                self.browse_items = BROWSE_SOURCES[key]()
                self.index = 0
                self._render_browse_card()

            elif kind == "timeline":
                events = engine.load_timeline_events()
                sample = random.sample(events, min(8, len(events)))
                self.timeline_shuffled = sample[:]
                random.shuffle(self.timeline_shuffled)
                self.timeline_correct_order = sorted(
                    range(len(self.timeline_shuffled)), key=lambda i: self.timeline_shuffled[i]["year"]
                )
                lines = "\n".join(
                    f"  {i + 1}. {e['event']}" for i, e in enumerate(self.timeline_shuffled)
                )
                self._render_card(
                    "Timeline Sort",
                    "Put these in chronological order (earliest first).",
                    lines,
                )
                self._update_status("type numbers in order, space-separated, e.g. '3 1 2 4 5 6 7 8'")
                self.query_one("#answer-input", Input).placeholder = "3 1 2 4 5 6 7 8"

            elif kind == "duel":
                self.awaiting_duel_setup = 1
                self._render_card("Pass-the-Keyboard Duel", "", "")
                self._update_status("enter Player 1's name")
                self.query_one("#answer-input", Input).placeholder = "Player 1 name"

            elif kind == "stats":
                self._render_stats()

            self.query_one("#answer-input", Input).value = ""
            if kind != "browse" or True:
                self.query_one("#answer-input", Input).focus()

        # ── Rendering helpers ───────────────────────────────────────────────

        def _render_card(self, title, subtitle, body):
            card = self.query_one("#card", Static)
            text = f"[bold]{escape(title)}[/bold]\n"
            if subtitle:
                text += f"[dim]{escape(subtitle)}[/dim]\n"
            text += "\n" + escape(body)
            card.update(text)

        def _update_status(self, text):
            self.query_one("#status-bar", Static).update(f" {text}")

        def _show_feedback(self, verdict_markup, context="", related="", date_tag=""):
            fb = self.query_one("#feedback", Static)
            lines = [verdict_markup]
            if context:
                lines.append(f"[dim]why:[/dim] {escape(context)}")
            if related:
                lines.append(f"[dim]also:[/dim] {escape(related)}")
            if date_tag:
                lines.append(f"[dim]{escape(date_tag)}[/dim]")
            fb.update("\n".join(lines))
            fb.styles.display = "block"

        def _hide_feedback(self):
            fb = self.query_one("#feedback", Static)
            fb.update("")
            fb.styles.display = "none"

        def _progress(self):
            return f"Q {self.index}/{self.total} -- score {self.score}"

        # ── Quiz (naturalization / missed / speed) ──────────────────────────

        def _render_quiz_question(self):
            if self.time_limit and (time.time() - self.start_time) > self.time_limit:
                self._finish_quiz()
                return
            if self.index >= len(self.pool):
                self._finish_quiz()
                return
            q = self.pool[self.index]
            self._render_card(
                f"Q{self.index + 1}. {q['question']}",
                f"{q['category']} / {q['subcategory']}",
                "",
            )
            self._update_status(self._progress())
            self.query_one("#answer-input", Input).placeholder = "your answer"

        def _answer_quiz(self, raw):
            q = self.pool[self.index]
            correct = engine.answer_matches(raw, q["answers"])
            if correct:
                self.score += 1
                db.clear_miss(q["id"])
                self._show_feedback(f"[bold green]{bell.right_plain()}[/bold green]", q.get("context", ""), q.get("related_fact", ""), q.get("date", ""))
            else:
                db.record_miss(q["id"])
                accepted = ", ".join(str(a) for a in q["answers"])
                self._show_feedback(
                    f"[bold red]{bell.wrong_plain()}[/bold red]", q.get("context", f"Accepted: {accepted}"), q.get("related_fact", ""), q.get("date", "")
                )
            self.index += 1
            if self.time_limit and (time.time() - self.start_time) > self.time_limit:
                self._finish_quiz()
            elif self.index >= len(self.pool):
                self._finish_quiz()
            else:
                self._render_quiz_question()

        def _finish_quiz(self):
            elapsed = time.time() - self.start_time if self.start_time else None
            self._render_card("Round complete", "", bell.telegram_plain(self.mode_key, self.score, self.total, elapsed))
            self._update_status(f"final: {self.score}/{self.total} -- {bell.medal(self.score, self.total)}")
            db.record_score(self.mode_key, self.score, self.total, elapsed)
            self.query_one("#answer-input", Input).placeholder = "pick another mode"

        # ── State matchup ────────────────────────────────────────────────────

        def _render_states_question(self):
            if self.index >= self.total:
                self._finish_quiz()
                return
            s = self.pool[self.index]
            mode = random.choice(["capital", "order"])
            self.states_current = (s, mode)
            if mode == "capital":
                q_text = f"What is the capital of {s['name']}?"
            else:
                q_text = f"{s['name']} was admitted as the __th state. (number)"
            self._render_card(f"Q{self.index + 1}. {q_text}", "State Matchup", "")
            self._update_status(self._progress())

        def _answer_states(self, raw):
            s, mode = self.states_current
            expected = [s["capital"]] if mode == "capital" else [str(s["order"])]
            correct = engine.answer_matches(raw, expected)
            fact = f"Capital: {s['capital']} -- admitted #{s['order']} ({s['admitted']})"
            if correct:
                self.score += 1
                self._show_feedback(f"[bold green]{bell.right_plain()}[/bold green]", s["fact"], fact, s["admitted"])
            else:
                self._show_feedback(f"[bold red]{bell.wrong_plain()}[/bold red]", s["fact"], fact, s["admitted"])
            self.index += 1
            self._render_states_question()

        # ── Quote match ──────────────────────────────────────────────────────

        def _render_quote_question(self):
            if self.index >= self.total:
                self._finish_quiz()
                return
            q = self.pool[self.index]
            options = [q["person"]] + q["distractors"]
            random.shuffle(options)
            self.quotes_current = q
            self.quotes_options = options
            body = "\n".join(f"  {i + 1}. {opt}" for i, opt in enumerate(options))
            self._render_card(f'Q{self.index + 1}. "{q["quote"]}"', "Who said it? (enter the number)", body)
            self._update_status(self._progress())

        def _answer_quote(self, raw):
            q = self.quotes_current
            try:
                pick = self.quotes_options[int(raw.strip()) - 1]
            except (ValueError, IndexError):
                pick = ""
            if pick == q["person"]:
                self.score += 1
                self._show_feedback(f"[bold green]{bell.right_plain()}[/bold green]", f"Said by {q['person']}.", "", "")
            else:
                self._show_feedback(f"[bold red]{bell.wrong_plain()}[/bold red]", f"It was {q['person']}.", "", "")
            self.index += 1
            self._render_quote_question()

        # ── Browse ───────────────────────────────────────────────────────────

        def _render_browse_card(self):
            if not self.browse_items:
                return
            title, subtitle, fact, date_tag = self.browse_items[self.index % len(self.browse_items)]
            self._render_card(title, subtitle, fact)
            n = len(self.browse_items)
            self._update_status(f"{self.index + 1}/{n} -- press enter for next")
            self.query_one("#answer-input", Input).placeholder = "press enter for next"

        def _advance_browse(self):
            self.index += 1
            if self.index >= len(self.browse_items):
                self.index = 0
            self._render_browse_card()

        # ── Timeline ─────────────────────────────────────────────────────────

        def _answer_timeline(self, raw):
            try:
                user_order = [int(x) - 1 for x in raw.split()]
            except ValueError:
                user_order = []
            score = sum(
                1 for a, b in zip(user_order, self.timeline_correct_order) if a == b
            )
            lines = "\n".join(
                f"  {self.timeline_shuffled[i]['year']} -- {self.timeline_shuffled[i]['event']}"
                for i in self.timeline_correct_order
            )
            elapsed = time.time() - self.start_time
            self._render_card("Round complete", "Actual chronological order:", lines)
            self._update_status(f"final: {score}/{len(self.timeline_shuffled)} -- {bell.medal(score, len(self.timeline_shuffled))}")
            db.record_score("timeline-sort", score, len(self.timeline_shuffled), elapsed)
            self.query_one("#answer-input", Input).placeholder = "pick another mode"

        # ── Duel ─────────────────────────────────────────────────────────────

        def _answer_duel_setup(self, raw):
            name = raw.strip()
            if self.awaiting_duel_setup == 1:
                self.duel_players[0] = name or "Player 1"
                self.awaiting_duel_setup = 2
                self._update_status(f"enter {self.duel_players[1]}'s name (or press enter)")
                self.query_one("#answer-input", Input).placeholder = "Player 2 name"
                return
            self.duel_players[1] = name or "Player 2"
            self.awaiting_duel_setup = 0
            self.duel_scores = {p: 0 for p in self.duel_players}
            self.duel_turn = 0
            self.pool = engine.pick_questions(engine.load_naturalization_questions(), 10)
            self.total = len(self.pool)
            self.index = 0
            self._render_duel_question()

        def _render_duel_question(self):
            if self.index >= len(self.pool):
                self._finish_duel()
                return
            player = self.duel_players[self.index % 2]
            q = self.pool[self.index]
            self._render_card(f"Q{self.index + 1}. {q['question']}", f"{player}'s turn", "")
            self._update_status(
                f"{self.duel_players[0]}: {self.duel_scores[self.duel_players[0]]}  |  "
                f"{self.duel_players[1]}: {self.duel_scores[self.duel_players[1]]}"
            )

        def _answer_duel(self, raw):
            player = self.duel_players[self.index % 2]
            q = self.pool[self.index]
            correct = engine.answer_matches(raw, q["answers"])
            if correct:
                self.duel_scores[player] += 1
                self._show_feedback(f"[bold green]{bell.right_plain()}[/bold green]", q.get("context", ""), q.get("related_fact", ""), q.get("date", ""))
            else:
                self._show_feedback(f"[bold red]{bell.wrong_plain()}[/bold red]", q.get("context", ""), q.get("related_fact", ""), q.get("date", ""))
            self.index += 1
            self._render_duel_question()

        def _finish_duel(self):
            p1, p2 = self.duel_players
            s1, s2 = self.duel_scores[p1], self.duel_scores[p2]
            if s1 == s2:
                result = "It's a tie!"
            else:
                winner = p1 if s1 > s2 else p2
                result = f"{winner} wins!"
            self._render_card("Duel complete", f"{p1}: {s1}  |  {p2}: {s2}", result)
            db.record_score(f"duel:{p1}-vs-{p2}", max(s1, s2), len(self.pool))
            self.query_one("#answer-input", Input).placeholder = "pick another mode"

        # ── Stats ────────────────────────────────────────────────────────────

        def _render_stats(self):
            lines = []
            any_scores = False
            for mode in ["naturalization", "speed", "states", "quotes", "amendments", "timeline-sort"]:
                rows = db.top_scores(mode, limit=3)
                if rows:
                    any_scores = True
                    lines.append(f"[bold]{mode}[/bold]")
                    for score, total, elapsed_s, played_at in rows:
                        t = f", {elapsed_s:.1f}s" if elapsed_s else ""
                        lines.append(f"  {score}/{total}{t}  ({played_at})")
            if not any_scores:
                lines.append("No scores recorded yet -- play a round first.")
            card = self.query_one("#card", Static)
            card.update("[bold]Recent Scores[/bold]\n\n" + "\n".join(lines))
            self._update_status("stats")
            self.query_one("#answer-input", Input).placeholder = "pick another mode"

        # ── Input dispatch ───────────────────────────────────────────────────

        def on_input_submitted(self, event: Input.Submitted) -> None:
            raw = event.value
            event.input.value = ""
            if self.kind == "quiz":
                self._answer_quiz(raw)
            elif self.kind == "states":
                self._answer_states(raw)
            elif self.kind == "quotes":
                self._answer_quote(raw)
            elif self.kind == "browse":
                self._advance_browse()
            elif self.kind == "timeline":
                self._answer_timeline(raw)
            elif self.kind == "duel":
                if self.awaiting_duel_setup:
                    self._answer_duel_setup(raw)
                else:
                    self._answer_duel(raw)

        def action_focus_list(self) -> None:
            self.query_one("#mode-list", ListView).focus()

        def action_focus_input(self) -> None:
            self.query_one("#answer-input", Input).focus()


def main():
    if not TEXTUAL_OK:
        print("textual is not installed. Run: pip install -r requirements-tui.txt")
        print("Or use the zero-dependency version: python3 app.py")
        return
    CivicsCheckApp().run()


if __name__ == "__main__":
    main()
