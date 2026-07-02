#!/usr/bin/env python3
"""Civics Check dashboard -- Textual TUI. America's 250th, with cards.

Usage:
  python3 tui.py
  make tui app=civics-check

Falls back to nothing gracefully: if textual isn't installed, this prints
a one-line message and exits. app.py (pure stdlib) always works regardless.

Palette follows the SAFE Design System's Terminal-surface token structure
(bg / panel / input / border / fg, one primary accent) -- but civics-check
gets its own accent trio (red/blue/gold) rather than SAFE's orange, per the
house rule that every app carries family resemblance, not a shared skin.
"""
from __future__ import annotations

import datetime
import random
import time

import bell
import db
import engine

try:
    from rich.markup import escape
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
    from textual.message import Message
    from textual.widgets import Footer, Header, Input, Static

    TEXTUAL_OK = True
except ImportError:
    TEXTUAL_OK = False


# ── Palette -- SAFE Terminal token structure, civics-check's own accents ────

BG = "#0d0d0d"
PANEL = "#111111"
INPUT_BG = "#1a1a1a"
BORDER = "#2a2a2a"
FG = "#f5f5f0"
FG_MUTED = "#888888"
RED = "#e63946"
BLUE = "#457b9d"
GOLD = "#f4a300"

MODES = [
    ("naturalization", "Naturalization Quiz", "10 real USCIS questions", "quiz"),
    ("missed", "Missed Review", "resurface what you got wrong", "quiz"),
    ("states", "State Matchup", "capitals + admission order", "states"),
    ("timeline", "Timeline Sort", "order 8 events by year", "timeline"),
    ("colonies", "13 Colonies", "flashcards, founding to founding", "browse"),
    ("on_this_day", "On This Day", "today in the founding era", "browse"),
    ("quotes", "Quote Match", "who said it", "quotes"),
    ("signers", "Declaration Signers", "13 lives, 13 cards", "browse"),
    ("amendments", "Amendment Explorer", "browse or quiz all 27", "browse"),
    ("speed", "Speed Round", "60 seconds, no mercy", "quiz"),
    ("duel", "Pass-the-Keyboard Duel", "two players, one keyboard", "duel"),
]

EAGLE_FRAMES = [
    """
        .  *  .    /=\\   .  *  .
           *   .--( o )--.  *
             _/  /_____\\  \\_
            (___/       \\___)
""",
    """
        .  *  .    /=\\   .  *  .
           *   .--( o )--.  *
            _/  /_______\\  \\_
           (___/         \\___)
""",
]

FIREWORK_FRAMES = [
    "        .        *          .    ",
    "      \\  |  /   \\ | /    .       ",
    "    -- * --  *  -- * --   \\|/    ",
    "      /  |  \\   / | \\   -- * --  ",
    "        '        '        /|\\    ",
]


def _colonies_cards():
    return [
        (c["name"], f"founded {c['founded']} by {c['founder']}", c["fact"], c.get("context", ""), c.get("source", ""))
        for c in engine.load_colonies()
    ]


def _signers_cards():
    return [
        (s["name"], s["state"], s["fact"], s.get("context", ""), s.get("source", ""))
        for s in engine.load_signers()
    ]


def _on_this_day_cards():
    events = engine.today_events()
    if not events:
        return [("No events today", "", "Try July 4th weekend for the good stuff.", "", "")]
    return [("On this day", "", e, "", "") for e in events]


def _amendments_cards():
    return [
        (f"Amendment {a['number']}", str(a["year"]), a["summary"], a.get("context", ""), a.get("source", ""))
        for a in engine.load_amendments()
    ]


BROWSE_SOURCES = {
    "colonies": _colonies_cards,
    "on_this_day": _on_this_day_cards,
    "signers": _signers_cards,
    "amendments": _amendments_cards,
}


if TEXTUAL_OK:

    class ModeCard(Static):
        """A dressed-up tile in the mode grid. Click it, it pops out to run."""

        def __init__(self, key, title, subtitle, **kwargs):
            super().__init__(**kwargs)
            self.mode_key = key
            self.mode_title = title
            self.mode_subtitle = subtitle
            self.can_focus = True

        def on_mount(self) -> None:
            self.update(f"[bold]{escape(self.mode_title)}[/bold]\n[dim]{escape(self.mode_subtitle)}[/dim]")

        def on_click(self) -> None:
            self.post_message(self.Picked(self, self.mode_key))

        def on_key(self, event) -> None:
            if event.key == "enter":
                self.post_message(self.Picked(self, self.mode_key))

        class Picked(Message):
            def __init__(self, card: "ModeCard", key: str) -> None:
                self.card = card
                self.key = key
                super().__init__()

    class CivicsCheckApp(App):
        """America's 250th, as a dashboard."""

        TITLE = "CIVICS CHECK"
        SUB_TITLE = "America's 250th -- 1776 * 2026"

        CSS = f"""
        Screen {{
            layout: vertical;
            background: {BG};
            color: {FG};
        }}

        #body {{
            height: 1fr;
        }}

        #sidebar {{
            width: 30;
            background: {PANEL};
            border-right: solid {BORDER};
            padding: 0 1;
        }}

        #sidebar-header {{
            height: 1;
            color: {GOLD};
            text-style: bold;
            padding: 0 1;
            margin-top: 1;
        }}

        #scoreboard {{
            height: 1fr;
        }}

        #ticker {{
            height: 2;
            color: {FG_MUTED};
            padding: 0 1;
            text-style: italic;
        }}

        #main {{
            width: 1fr;
            padding: 0 1;
        }}

        #mode-grid {{
            layout: grid;
            grid-size: 3;
            grid-gutter: 1 2;
            padding: 1;
            height: 1fr;
        }}

        ModeCard {{
            background: {PANEL};
            border: heavy {BORDER};
            padding: 1 2;
            height: 5;
        }}

        ModeCard:hover {{
            border: heavy {GOLD};
            background: {INPUT_BG};
        }}

        ModeCard:focus {{
            border: heavy {BLUE};
        }}

        #eagle-banner {{
            height: 6;
            content-align: center middle;
            color: {BLUE};
            text-style: bold;
        }}

        #runner {{
            height: 1fr;
            display: none;
        }}

        #status-bar {{
            height: 1;
            background: {PANEL};
            color: {GOLD};
            text-style: bold;
            padding: 0 1;
        }}

        #card {{
            height: 1fr;
            border: heavy {FG};
            background: {PANEL};
            padding: 1 2;
            margin-top: 1;
        }}

        #feedback {{
            height: auto;
            max-height: 10;
            border: heavy {GOLD};
            background: {INPUT_BG};
            padding: 1 2;
            margin-top: 1;
            display: none;
        }}

        #firework-overlay {{
            height: 5;
            content-align: center middle;
            color: {RED};
            text-style: bold;
            display: none;
        }}

        #answer-input {{
            height: 3;
            margin-top: 1;
            background: {INPUT_BG};
            border: solid {BORDER};
        }}

        #answer-input:focus {{
            border: solid {GOLD};
        }}
        """

        BINDINGS = [
            Binding("ctrl+c", "quit", "Quit", show=True),
            Binding("escape", "collapse", "Back to modes", show=True),
            Binding("ctrl+b", "bell_easter_egg", "Ring the Bell", show=False),
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
            self.browse_items = []
            self.duel_players = ["Player 1", "Player 2"]
            self.duel_scores = {}
            self.awaiting_duel_setup = 0
            self.timeline_shuffled = []
            self.timeline_correct_order = []
            self.states_current = None
            self.quotes_current = None
            self.quotes_options = []
            self._eagle_frame = 0

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with Vertical(id="sidebar"):
                    yield Static("  SCOREBOARD", id="sidebar-header")
                    yield VerticalScroll(Static("", id="scoreboard-body"), id="scoreboard")
                with Vertical(id="main"):
                    yield Static("", id="firework-overlay")
                    with Vertical(id="mode-select"):
                        yield Static(EAGLE_FRAMES[0], id="eagle-banner")
                        yield Static("", id="ticker")
                        with Grid(id="mode-grid"):
                            for key, title, subtitle, _kind in MODES:
                                yield ModeCard(key, title, subtitle, id=f"card-{key}")
                    with Vertical(id="runner"):
                        yield Static("", id="status-bar")
                        yield Static("", id="card")
                        yield Static("", id="feedback")
                        yield Input(placeholder="your answer", id="answer-input")
            yield Footer()

        def on_mount(self) -> None:
            self._refresh_scoreboard()
            self.query_one("#ticker", Static).update(bell.ticker_plain(engine.load_quotes()))
            self.set_interval(0.7, self._flap_eagle)
            today = datetime.date.today()
            if (today.month, today.day) == (7, 4):
                self._show_fireworks(loud=True)

        def _flap_eagle(self) -> None:
            self._eagle_frame = (self._eagle_frame + 1) % len(EAGLE_FRAMES)
            banner = self.query_one("#eagle-banner", Static)
            if banner.styles.display != "none":
                banner.update(EAGLE_FRAMES[self._eagle_frame])

        def _refresh_scoreboard(self) -> None:
            lines = []
            any_scores = False
            for mode in ["naturalization", "speed", "states", "quotes", "amendment-quiz", "timeline-sort"]:
                rows = db.top_scores(mode, limit=2)
                if rows:
                    any_scores = True
                    lines.append(f"[bold {GOLD}]{mode}[/bold {GOLD}]")
                    for score, total, elapsed_s, played_at in rows:
                        medal = bell.medal(score, total)
                        lines.append(f"  {score}/{total}  [{BLUE}]{medal}[/{BLUE}]")
                    lines.append("")
            if not any_scores:
                lines.append(f"[{FG_MUTED}]No scores yet.\nPick a mode to start.[/{FG_MUTED}]")
            self.query_one("#scoreboard-body", Static).update("\n".join(lines))

        # ── Card grid <-> runner pop/collapse ───────────────────────────────

        def on_mode_card_picked(self, message) -> None:
            for key, label, _subtitle, kind in MODES:
                if key == message.key:
                    self._start_mode(key, label, kind)
                    return

        def action_collapse(self) -> None:
            self.query_one("#runner", Vertical).styles.display = "none"
            self.query_one("#mode-select", Vertical).styles.display = "block"
            self._refresh_scoreboard()
            self.query_one("#mode-grid", Grid).focus()

        def action_bell_easter_egg(self) -> None:
            self.notify(random.choice([
                "THE BELL: I heard that. I have opinions.",
                "THE BELL: still cracked. still here.",
                "THE BELL: ring me again and see what happens. (nothing will happen.)",
                "THE BELL: 250 years and you're pressing buttons at me.",
            ]), title="the Bell", timeout=4)

        def _pop_to_runner(self):
            self.query_one("#mode-select", Vertical).styles.display = "none"
            runner = self.query_one("#runner", Vertical)
            runner.styles.display = "block"
            runner.styles.opacity = 0.0
            runner.styles.animate("opacity", value=1.0, duration=0.25)

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
            self._pop_to_runner()

            if kind == "quiz":
                pool = engine.load_naturalization_questions()
                if key == "missed":
                    ids = db.missed_question_ids(limit=10)
                    if not ids:
                        self._render_card("Missed Questions", "Nothing missed yet -- clean slate.", "")
                        self._update_status("missed-review: nothing to show")
                        self.query_one("#answer-input", Input).placeholder = "press escape to go back"
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
                self._update_status("type numbers in order, space-separated")
                self.query_one("#answer-input", Input).placeholder = "3 1 2 4 5 6 7 8"

            elif kind == "duel":
                self.awaiting_duel_setup = 1
                self._render_card("Pass-the-Keyboard Duel", "", "")
                self._update_status("enter Player 1's name")
                self.query_one("#answer-input", Input).placeholder = "Player 1 name"

            self.query_one("#answer-input", Input).value = ""
            self.query_one("#answer-input", Input).focus()

        # ── Rendering helpers ───────────────────────────────────────────────

        def _render_card(self, title, subtitle, body):
            card = self.query_one("#card", Static)
            text = f"[bold {GOLD}]{escape(title)}[/bold {GOLD}]\n"
            if subtitle:
                text += f"[{FG_MUTED}]{escape(subtitle)}[/{FG_MUTED}]\n"
            text += "\n" + escape(body)
            card.update(text)

        def _update_status(self, text):
            self.query_one("#status-bar", Static).update(f" {text}")

        def _show_feedback(self, verdict_markup, context="", related="", source=""):
            fb = self.query_one("#feedback", Static)
            lines = [verdict_markup]
            if context:
                lines.append(f"[{FG_MUTED}]why:[/{FG_MUTED}] {escape(context)}")
            if related:
                lines.append(f"[{FG_MUTED}]also:[/{FG_MUTED}] {escape(related)}")
            if source:
                lines.append(f"[{FG_MUTED}]source: {escape(source)}[/{FG_MUTED}]")
            fb.update("\n".join(lines))
            fb.styles.display = "block"
            fb.styles.opacity = 0.0
            fb.styles.animate("opacity", value=1.0, duration=0.2)

        def _hide_feedback(self):
            fb = self.query_one("#feedback", Static)
            fb.update("")
            fb.styles.display = "none"

        def _progress(self):
            return f"Q {self.index}/{self.total} -- score {self.score}"

        def _show_fireworks(self, loud=False):
            overlay = self.query_one("#firework-overlay", Static)
            overlay.styles.display = "block"
            frames = FIREWORK_FRAMES * (2 if loud else 1)
            state = {"i": 0, "timer": None}

            def _tick():
                if state["i"] >= len(frames):
                    overlay.styles.display = "none"
                    state["timer"].stop()
                    return
                overlay.update(f"[{GOLD}]{frames[state['i']]}[/{GOLD}]")
                state["i"] += 1

            state["timer"] = self.set_interval(0.15, _tick)

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
            if raw.strip() == "1776":
                self._show_feedback(
                    f"[bold {GOLD}]THE BELL:[/bold {GOLD}] I admire the commitment to the bit. Still not the answer.",
                )
                return
            q = self.pool[self.index]
            correct = engine.answer_matches(raw, q["answers"])
            if correct:
                self.score += 1
                db.clear_miss(q["id"])
                self._show_feedback(f"[bold {GOLD}]{bell.right_plain()}[/bold {GOLD}]", q.get("context", ""), q.get("related_fact", ""), q.get("date", ""))
            else:
                db.record_miss(q["id"])
                accepted = ", ".join(str(a) for a in q["answers"])
                self._show_feedback(
                    f"[bold {RED}]{bell.wrong_plain()}[/bold {RED}]", q.get("context", f"Accepted: {accepted}"), q.get("related_fact", ""), q.get("date", "")
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
            if self.total and self.score == self.total:
                self._show_fireworks()
            self.query_one("#answer-input", Input).placeholder = "press escape to go back"
            self._refresh_scoreboard()

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
            color = GOLD if correct else RED
            verdict = bell.right_plain() if correct else bell.wrong_plain()
            if correct:
                self.score += 1
            self._show_feedback(f"[bold {color}]{verdict}[/bold {color}]", s["fact"], fact, s["admitted"])
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
            correct = pick == q["person"]
            color = GOLD if correct else RED
            verdict = bell.right_plain() if correct else bell.wrong_plain()
            if correct:
                self.score += 1
            context = q.get("context", f"Said by {q['person']}.")
            self._show_feedback(f"[bold {color}]{verdict}[/bold {color}]", context, "", "")
            self.index += 1
            self._render_quote_question()

        # ── Browse ───────────────────────────────────────────────────────────

        def _render_browse_card(self):
            if not self.browse_items:
                return
            title, subtitle, fact, context, source = self.browse_items[self.index % len(self.browse_items)]
            card = self.query_one("#card", Static)
            text = f"[bold {GOLD}]{escape(title)}[/bold {GOLD}]\n[{FG_MUTED}]{escape(subtitle)}[/{FG_MUTED}]\n\n{escape(fact)}"
            if context:
                text += f"\n\n{escape(context)}"
            if source:
                text += f"\n\n[{FG_MUTED}]source: {escape(source)}[/{FG_MUTED}]"
            card.update(text)
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
            total = len(self.timeline_shuffled)
            self._update_status(f"final: {score}/{total} -- {bell.medal(score, total)}")
            db.record_score("timeline-sort", score, total, elapsed)
            if score == total:
                self._show_fireworks()
            self.query_one("#answer-input", Input).placeholder = "press escape to go back"
            self._refresh_scoreboard()

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
            color = GOLD if correct else RED
            verdict = bell.right_plain() if correct else bell.wrong_plain()
            if correct:
                self.duel_scores[player] += 1
            self._show_feedback(f"[bold {color}]{verdict}[/bold {color}]", q.get("context", ""), q.get("related_fact", ""), q.get("date", ""))
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
            if s1 == len(self.pool) or s2 == len(self.pool):
                self._show_fireworks()
            self.query_one("#answer-input", Input).placeholder = "press escape to go back"
            self._refresh_scoreboard()

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


def main():
    if not TEXTUAL_OK:
        print("textual is not installed. Run: pip install -r requirements-tui.txt")
        print("Or use the zero-dependency version: python3 app.py")
        return
    CivicsCheckApp().run()


if __name__ == "__main__":
    main()
