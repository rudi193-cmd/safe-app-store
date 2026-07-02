#!/usr/bin/env python3
"""Civics Check — Freedom 250 fair map TUI (Textual).

Surface: parchment civics fair with pavilion lanes.
Underground: DIENAMIC debate easter egg (109 or ctrl+d).

Usage:
  python3 tui.py
  make tui
"""
from __future__ import annotations

import datetime
import random

import bell
import db
import engine
import tui_art
from civics.session import ActivitySession

try:
    from rich.markup import escape
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import Input, ListItem, ListView, Static

    TEXTUAL_OK = True
except ImportError:
    TEXTUAL_OK = False

# ── Parchment surface (civics_tui_scope.json) ─────────────────────────────────
# Richer amber than #e8d4a8 — reads as parchment on bright terminals, not white.

PARCHMENT = "#c9a85c"
PARCHMENT_DEEP = "#b89248"
PARCHMENT_LIGHT = "#e2c992"
INK = "#1a1008"
INK_MUTED = "#4a3828"
ACCENT = "#3d5166"
BRASS = "#6b4e0a"
RULE = "#8a7040"
NAVY = "#1a2744"
NAVY_LIGHT = "#2a3d66"
STRIPES = "#8b1a1a"
GOLD = "#d4a017"
FLAG_FIELD = "#2a4a8a"
FLAG_STAR = "#f0e4c8"
CREAM = "#f0e4c8"
CURTAIN_BG = "#3f0c0c"  # matches tui_art curtain texture background

# DIENAMIC underground
DEBATE_BG = "#e8d100"
DEBATE_FG = "#0a0a0a"
OBAMA_COLOR = "#00bcd4"
TRUMP_COLOR = "#d97706"

FIREWORK_FRAMES = tui_art.FIREWORK_FRAMES


def span(text: str, fg: str, bg: str, bold: bool = False) -> str:
    style = f"bold {fg} on {bg}" if bold else f"{fg} on {bg}"
    return f"[{style}]{escape(text)}[/]"


def source_markup(source: str, fg: str = INK_MUTED, link_fg: str = ACCENT) -> str:
    """Two framings, one line each: where we got it, and where to keep going.

    Returns "" when there is no source. The learn-more line is an OSC 8
    hyperlink — clickable in terminals that support it, plain text elsewhere.
    """
    if not source:
        return ""
    out = f"[{fg}]source: {escape(source)}[/{fg}]"
    resolved = engine.resolve_source(source)
    if resolved:
        out += (
            f"\n[link='{resolved['url']}'][bold {link_fg}]"
            f"⧉ learn more — {escape(resolved['label'])}"
            f"[/bold {link_fg}][/link]"
        )
    return out


def _motto_for_today() -> str:
    return tui_art.MOTTOS[datetime.date.today().toordinal() % len(tui_art.MOTTOS)]


def _fair_day_lines() -> tuple[str, str]:
    """Return (fair_day banner, numerology line) from today's fair schedule."""
    try:
        entry = engine.fair_day()
    except FileNotFoundError:
        return "", ""
    if not entry:
        return "", ""
    fair = f"{entry.get('title', '')} · {entry.get('theme', '')}".strip(" ·")
    num_line = ""
    theme = entry.get("theme", "")
    for key, (num, gloss) in tui_art.FAIR_DAY_NUMBERS.items():
        if key.lower() in theme.lower() or theme.lower() in key.lower():
            num_line = f"{num} · {gloss}"
            break
    return fair[:52], num_line


def _session_catalog_card(session: ActivitySession | None) -> dict | None:
    if not session or session.index >= session.total:
        return None
    if session.kind == "browse":
        cards = session.catalog.pool_for_activity(session.activity_id)
        return cards[session.index] if session.index < len(cards) else None
    if session.index < len(session._pool):
        card = session._pool[session.index]
        cid = card.get("card_id") or card.get("id")
        if cid:
            full = session.catalog.card(str(cid))
            return full or card
        return card
    return None


def _activity_lane_pavilion(activity_id: str) -> tuple[str, str]:
    return engine.activity_lane_pavilion(activity_id)


def activities_for_pavilion(pavilion_id: str) -> list[dict]:
    return engine.activities_for_pavilion(pavilion_id)


def primary_activity_id(pavilion_id: str) -> str | None:
    return engine.primary_activity_id(pavilion_id)


def pavilion_activities(pavilion_id: str) -> list[tuple[str, str, str]]:
    return engine.pavilion_activity_menu(pavilion_id)


# App-wide base — Textual's default theme paints widgets white unless overridden here.
APP_BASE_CSS = f"""
Screen {{
    background: {PARCHMENT};
    color: {INK};
}}
Static, Horizontal, Vertical, VerticalScroll {{
    background: {PARCHMENT};
    color: {INK};
}}
ListView {{
    background: {PARCHMENT};
    border: none;
    scrollbar-color: {ACCENT};
    scrollbar-background: {PARCHMENT_DEEP};
}}
ListView:focus {{
    background: {PARCHMENT};
}}
ListItem {{
    padding: 0 1;
    background: {PARCHMENT};
    color: {INK};
}}
ListItem Static {{
    background: {PARCHMENT};
    color: {INK};
}}
ListItem:hover, ListItem:hover Static {{
    background: {PARCHMENT_DEEP};
}}
ListItem.--highlight, ListItem.--highlight Static {{
    background: {ACCENT};
    color: {PARCHMENT_LIGHT};
}}
Input {{
    background: {PARCHMENT_DEEP};
    color: {INK};
    border: tall {RULE};
}}
Input:focus {{
    border: tall {BRASS};
}}
"""


if TEXTUAL_OK:

    from textual.app import App

    def enter_underground(app: App) -> None:
        """Ceremonial rupture: parchment fair → DIENAMIC debate."""
        app.push_screen(FallThroughScreen())

    class FallThroughScreen(Screen):
        """109-second energy in three frames — floor gives way."""

        CSS = f"""
        FallThroughScreen {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
            align: center middle;
        }}
        #fall-text {{
            width: 100%;
            height: 100%;
            content-align: center middle;
            text-style: bold;
            background: {DEBATE_BG};
            color: {DEBATE_FG};
        }}
        """

        def compose(self) -> ComposeResult:
            yield Static("", id="fall-text")

        def on_mount(self) -> None:
            self._frame = 0
            self._timer = self.set_interval(0.45, self._tick)

        def _tick(self) -> None:
            frames = tui_art.FALL_THROUGH_FRAMES
            widget = self.query_one("#fall-text", Static)
            if self._frame < len(frames):
                widget.update(f"[bold]{escape(frames[self._frame])}[/bold]")
                self._frame += 1
                return
            self._timer.stop()
            self.app.pop_screen()
            self.app.push_screen(DebateScreen())

    STAGE_CSS = APP_BASE_CSS + f"""
    #ceremony-band {{
        height: {tui_art.HERO_ROWS};
        max-height: {tui_art.HERO_ROWS};
        background: {NAVY};
        border-bottom: heavy {GOLD};
    }}
    #hero-field {{
        width: 100%;
        height: {tui_art.HERO_ROWS};
        max-height: {tui_art.HERO_ROWS};
        background: {NAVY};
    }}
    #stage-body {{
        height: 1fr;
        min-height: 12;
    }}
    #stage-center {{
        width: 1fr;
        height: 1fr;
    }}
    #curtain-left, #curtain-right {{
        width: {tui_art.CURTAIN_W};
        min-width: {tui_art.CURTAIN_W};
        height: 1fr;
        background: {CURTAIN_BG};
        overflow: hidden hidden;
    }}
    """

    class StageScreen(Screen):
        """Permanent scenery: hero star field above, curtains flanking.

        Subclasses fill the center via compose_stage()."""

        def __init__(self) -> None:
            super().__init__()
            self._star_phase = 0
            self._sparkle_mode = "normal"
            self._ripple_tick = 0
            self._landmark_accent = ""

        def _hero_context(self) -> tui_art.HeroContext:
            fair, num = _fair_day_lines()
            return tui_art.HeroContext(motto=_motto_for_today(), fair_day=fair, number_line=num)

        def compose_stage(self) -> ComposeResult:
            return
            yield  # pragma: no cover — makes this a generator; subclasses override

        def compose(self) -> ComposeResult:
            with Horizontal(id="ceremony-band"):
                # markup=False — star glyphs must never parse as Rich tags
                yield Static("", id="hero-field", markup=False)
            with Horizontal(id="stage-body"):
                yield Static(tui_art.curtain_rich(), id="curtain-left", markup=False)
                with Vertical(id="stage-center"):
                    yield from self.compose_stage()
                yield Static(tui_art.curtain_rich(), id="curtain-right", markup=False)

        def _render_hero(self) -> None:
            field = self.query_one("#hero-field", Static)
            width = field.size.width or self.app.size.width
            ctx = self._hero_context()
            if self._landmark_accent:
                ctx.landmark_accent = self._landmark_accent
            field.update(
                tui_art.hero_field(
                    width,
                    tui_art.HERO_ROWS,
                    self._star_phase,
                    ctx,
                    sparkle_mode=self._sparkle_mode,
                    ripple_tick=self._ripple_tick,
                )
            )

        def on_resize(self, event) -> None:
            self._render_hero()

        def _sparkle(self, ticks: int = 8, mode: str = "normal", accent: str = "") -> None:
            """Event flourish: cycle star brightness, optional bell ripple or landmark glow."""
            self._sparkle_mode = mode
            self._landmark_accent = accent
            state: dict = {"n": 0, "timer": None}

            def tick() -> None:
                state["n"] += 1
                if state["n"] > ticks:
                    if state["timer"]:
                        state["timer"].stop()
                    self._star_phase = 0
                    self._sparkle_mode = "normal"
                    self._ripple_tick = 0
                    self._landmark_accent = ""
                else:
                    self._star_phase = (self._star_phase + 1) % 3
                    self._ripple_tick = state["n"]
                self._render_hero()

            state["timer"] = self.set_interval(0.18, tick)

    class FairMapScreen(StageScreen):
        """Pavilion fair — lanes as paths, not a dashboard grid."""

        BINDINGS = [
            Binding("enter", "visit", "Visit pavilion", show=True),
            Binding("left", "focus_lanes", "Lanes", show=False),
            Binding("right", "focus_pavilions", "Pavilions", show=False),
            Binding("q", "quit_app", "Quit", show=True),
            Binding("s", "sources", "Sources", show=True),
            Binding("ctrl+b", "ring_bell", "Ring the Bell", show=False),
            Binding("ctrl+d", "debate", "Debate", show=False),
        ]

        CSS = STAGE_CSS + f"""
        FairMapScreen {{
            background: {PARCHMENT};
        }}
        #firework-banner {{
            height: 1;
            text-align: center;
            color: {STRIPES};
            background: {PARCHMENT};
            display: none;
        }}
        #fair-body {{
            height: 1fr;
            min-height: 12;
        }}
        #lane-col {{
            width: 28;
            height: 1fr;
            padding: 0 1;
        }}
        #lane-list, #pavilion-list {{
            height: 1fr;
            min-height: 8;
        }}
        #pavilion-col {{
            width: 1fr;
            height: 1fr;
        }}
        #lane-label, #pavilion-label {{
            height: 1;
            padding: 0 1;
            color: {NAVY};
            text-style: bold;
            background: {PARCHMENT_LIGHT};
        }}
        #preview-col {{
            width: 30;
            height: 1fr;
            border-left: tall {NAVY};
            background: {PARCHMENT_LIGHT};
        }}
        #preview {{
            height: 1fr;
            padding: 0 1;
            color: {INK};
        }}
        #flare-plaza {{
            height: 1;
            padding: 0 1;
            color: {NAVY};
            background: {CREAM};
            border-top: tall {GOLD};
        }}
        #footline {{
            height: 1;
            padding: 0 1;
            color: {CREAM};
            background: {NAVY};
            border-top: heavy {GOLD};
        }}
        """

        def __init__(self) -> None:
            super().__init__()
            self._lanes: list[dict] = []
            self._pavilions_by_lane: dict[str, list[dict]] = {}
            self._current_lane_id: str | None = None
            self._fair_day_label = "open all week"

        def compose_stage(self) -> ComposeResult:
            yield Static("", id="firework-banner")
            with Horizontal(id="fair-body"):
                with Vertical(id="lane-col"):
                    yield Static(" LANES", id="lane-label")
                    yield ListView(id="lane-list")
                with Vertical(id="pavilion-col"):
                    yield Static(" PAVILIONS", id="pavilion-label")
                    yield ListView(id="pavilion-list")
                with Vertical(id="preview-col"):
                    yield Static("", id="preview")
                    yield Static(tui_art.FLARE_PLAZA, id="flare-plaza")
            yield Static("", id="footline")

        def on_mount(self) -> None:
            cat = engine.get_catalog()
            self._lanes = [ln for ln in cat.lanes if not ln.get("hidden")]
            self._pavilions_by_lane = {}
            for p in engine.pavilions(hidden=False):
                lane = p.get("lane", "schoolhouse")
                self._pavilions_by_lane.setdefault(lane, []).append(p)
            # synthetic lane — the Record Room is a TUI page, not a catalog activity
            self._lanes.append({"id": "_record_room", "label": "Record Room"})
            self._pavilions_by_lane["_record_room"] = [{
                "id": "_sources",
                "label": "Sources & Further Reading",
                "subtitle": "learn more here · where we got the info",
                "default_tier": "know",
            }]

            lane_list = self.query_one("#lane-list", ListView)
            for ln in self._lanes:
                label = tui_art.LANE_ICONS.get(ln["id"], ln["label"])
                lane_list.append(ListItem(Static(label)))
            if self._lanes:
                lane_list.index = 0
                self._select_lane(0)
            try:
                day = engine.fair_day()
                if day:
                    self._fair_day_label = day.get("title", self._fair_day_label)
            except FileNotFoundError:
                pass
            self.call_after_refresh(self._render_hero)
            self._refresh_footline()
            lane_list.focus()
            today = datetime.date.today()
            if (today.month, today.day) == (7, 4):
                self._show_fireworks(loud=True)
                self._sparkle(ticks=20)

        def _show_fireworks(self, loud: bool = False) -> None:
            banner = self.query_one("#firework-banner", Static)
            banner.styles.display = "block"
            frames = tui_art.FIREWORK_FRAMES * (3 if loud else 1)
            state = {"i": 0, "timer": None}

            def tick() -> None:
                if state["i"] >= len(frames):
                    banner.styles.display = "none"
                    if state["timer"]:
                        state["timer"].stop()
                    return
                banner.update(f"[bold {STRIPES}]{frames[state['i']]}[/bold {STRIPES}]")
                state["i"] += 1

            state["timer"] = self.set_interval(0.14, tick)

        def _refresh_footline(self) -> None:
            # Lanes live in the grid now — no rail. Keys, one score, one quote.
            quote = bell.ticker_plain(engine.load_quotes())
            if len(quote) > 44:
                quote = quote[:41] + "..."
            bits = ["↑↓ ←→ · Enter · S sources · Ctrl+B bell · Q quit"]
            rows = db.top_scores("naturalization", limit=1)
            if rows:
                s, t, _, _ = rows[0]
                bits.append(f"nat {s}/{t}")
            bits.append(self._fair_day_label[:22])
            self.query_one("#footline", Static).update(
                f" {' · '.join(bits)}  │  \"{escape(quote)}\""
            )

        def _hero_context(self) -> tui_art.HeroContext:
            ctx = super()._hero_context()
            lane_label = tui_art.LANE_ICONS.get(self._current_lane_id or "", "")
            pavs = self._pavilions_by_lane.get(self._current_lane_id or "", [])
            idx = self.query_one("#pavilion-list", ListView).index
            pavilion_id = ""
            pavilion_label = ""
            if pavs and idx is not None and 0 <= idx < len(pavs):
                pavilion_id = pavs[idx]["id"]
                pavilion_label = pavs[idx]["label"]
            if pavilion_label:
                ctx.caption = f"{lane_label} · {pavilion_label}"[:58]
            elif lane_label:
                ctx.caption = lane_label[:58]
            ctx.canton = tui_art.canton_for_lane(self._current_lane_id, pavilion_id or None)
            ctx.nat_pass_hint = self._current_lane_id == "citizenship_court"
            ctx.record_room = self._current_lane_id == "_record_room"
            return ctx

        def _select_lane(self, index: int) -> None:
            if not self._lanes:
                return
            lane = self._lanes[index]
            self._current_lane_id = lane["id"]
            pavs = self._pavilions_by_lane.get(lane["id"], [])
            pavilion_list = self.query_one("#pavilion-list", ListView)
            pavilion_list.clear()
            for p in pavs:
                tier = p.get("default_tier", "show")
                icon = tui_art.PAVILION_ICONS.get(tier, "·")
                pavilion_list.append(
                    ListItem(Static(f"{icon}  {p['label']}  [{tier}]", markup=False))
                )
            if pavs:
                pavilion_list.index = 0
                self._update_preview(0)
            else:
                self.query_one("#preview", Static).update("[dim]No tents on this lane yet.[/dim]")
            self._render_hero()

        def _update_preview(self, index: int) -> None:
            pavs = self._pavilions_by_lane.get(self._current_lane_id or "", [])
            if not pavs or index >= len(pavs):
                return
            p = pavs[index]
            tier = p.get("default_tier", "show")
            icon = tui_art.PAVILION_ICONS.get(tier, "·")
            if p["id"] == "_sources":
                self.query_one("#preview", Static).update(
                    f"[bold {NAVY}]{icon} {escape(p['label'])}[/bold {NAVY}]\n"
                    f"[{STRIPES}]{escape(p.get('subtitle', ''))}[/{STRIPES}]\n\n"
                    f"Every citation in the fair, linked —\n"
                    f"and shelves worth reading past it.\n\n"
                    f"[{ACCENT}]Enter to open · S works anywhere[/{ACCENT}]"
                )
                return
            acts = pavilion_activities(p["id"])
            act_lines = "\n".join(f"  · {label} ({hint})" for _aid, label, hint in acts) or "  · browse"
            extra = ""
            if p["id"] == "amendments":
                extra = "\n\n[bold]Press A[/bold] for amendment quiz."
            text = (
                f"[bold {NAVY}]{icon} {escape(p['label'])}[/bold {NAVY}]\n"
                f"[{STRIPES}]{escape(p.get('subtitle', ''))}[/{STRIPES}]\n\n"
                f"[{ACCENT}]Activities[/{ACCENT}]\n{act_lines}{extra}"
            )
            self.query_one("#preview", Static).update(text)

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            if event.list_view.id == "lane-list":
                self._select_lane(event.list_view.index)
                self.query_one("#pavilion-list", ListView).focus()
            elif event.list_view.id == "pavilion-list":
                self.action_visit()

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            if event.list_view.id == "pavilion-list":
                self._update_preview(event.list_view.index)
                self._render_hero()

        def action_visit(self) -> None:
            pavs = self._pavilions_by_lane.get(self._current_lane_id or "", [])
            idx = self.query_one("#pavilion-list", ListView).index
            if not pavs or idx is None or idx >= len(pavs):
                return
            pavilion = pavs[idx]
            if pavilion["id"] == "_sources":
                self.app.push_screen(SourcesScreen())
                return
            activity_id = primary_activity_id(pavilion["id"])
            if not activity_id:
                self.notify("No activity wired for this pavilion yet.", timeout=3)
                return
            self.app.push_screen(ActivityScreen(activity_id, pavilion["label"]))

        def action_sources(self) -> None:
            self.app.push_screen(SourcesScreen())

        def action_focus_lanes(self) -> None:
            self.query_one("#lane-list", ListView).focus()

        def action_focus_pavilions(self) -> None:
            self.query_one("#pavilion-list", ListView).focus()

        def action_debate(self) -> None:
            enter_underground(self.app)

        def action_ring_bell(self) -> None:
            self.notify(
                random.choice([
                    "THE BELL: I heard that. I have opinions.",
                    "THE BELL: still cracked. still here.",
                    "THE BELL: 250 years and you're pressing buttons at me.",
                    "THE BELL: the floor beneath Liberty Plaza is NOT load-bearing.",
                ]),
                title="Liberty Bell",
                timeout=5,
            )
            # the ring shivers the sky: ripple outward from center, flash the plaza hint
            self._sparkle(ticks=14, mode="ripple")
            plaza = self.query_one("#flare-plaza", Static)
            plaza.update(tui_art.FLARE_PLAZA_HOT)
            self.set_timer(1.6, lambda: plaza.update(tui_art.FLARE_PLAZA))

        def action_quit_app(self) -> None:
            self.app.exit()

        def on_key(self, event) -> None:
            if event.key == "a":
                pavs = self._pavilions_by_lane.get(self._current_lane_id or "", [])
                idx = self.query_one("#pavilion-list", ListView).index
                if pavs and idx is not None and pavs[idx]["id"] == "amendments":
                    self.app.push_screen(ActivityScreen("amendment-quiz", "Amendment Quiz"))

    class ActivityScreen(StageScreen):
        """Run one catalog activity via ActivitySession — center stage, chrome up."""

        BINDINGS = [
            Binding("escape", "back", "Fair map", show=True),
        ]

        CSS = STAGE_CSS + f"""
        ActivityScreen {{
            background: {PARCHMENT};
        }}
        #activity-herald {{
            height: 1;
            padding: 0 2;
            background: {NAVY};
            color: {CREAM};
            border-bottom: heavy {GOLD};
        }}
        ActivityScreen.debate-mode {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
        }}
        ActivityScreen.debate-mode Static,
        ActivityScreen.debate-mode Horizontal,
        ActivityScreen.debate-mode Vertical {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
        }}
        #status {{
            height: 1;
            padding: 0 2;
            color: {ACCENT};
            background: {PARCHMENT_DEEP};
            border-bottom: heavy {RULE};
        }}
        ActivityScreen.debate-mode #status {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
            border-bottom: heavy {DEBATE_FG};
        }}
        #card {{
            height: 1fr;
            padding: 1 2;
        }}
        #feedback {{
            height: auto;
            max-height: 8;
            padding: 0 2;
            color: {INK_MUTED};
            display: none;
        }}
        #answer-input {{
            height: 3;
            margin: 0 2 1 2;
        }}
        #firework {{
            height: 3;
            content-align: center middle;
            color: {BRASS};
            display: none;
        }}
        """

        def __init__(self, activity_id: str, title: str) -> None:
            super().__init__()
            self.activity_id = activity_id
            self.title = title
            self.session: ActivitySession | None = None
            self.duel_setup = 0
            self.duel_names = ["Player 1", "Player 2"]
            self._done = False

        def compose_stage(self) -> ComposeResult:
            yield Static("", id="activity-herald")
            yield Static("", id="status")
            yield Static("", id="firework")
            yield Static("", id="card")
            yield Static("", id="feedback")
            yield Input(placeholder="", id="answer-input")

        def on_mount(self) -> None:
            self.call_after_refresh(self._render_hero)
            self._render_herald()
            try:
                self.session = ActivitySession(self.activity_id)
            except (ValueError, FileNotFoundError) as exc:
                self.query_one("#card", Static).update(f"[bold]{escape(str(exc))}[/bold]")
                return
            if self.session.kind == "duel":
                self.duel_setup = 1
                self._set_status("enter Player 1 name")
                self.query_one("#answer-input", Input).placeholder = "Player 1"
            elif self.activity_id == "missed":
                import db as _db

                if not _db.missed_card_ids(1) and not _db.missed_question_ids(1):
                    self._render_message("Missed Review", "Nothing missed yet — clean slate.")
                    self._done = True
                    return
            self._render_step()
            self.query_one("#answer-input", Input).focus()

        def _render_herald(self) -> None:
            self.query_one("#activity-herald", Static).update(
                f"[bold {GOLD}]★[/bold {GOLD}] {escape(self.title)}"
            )

        def _hero_context(self) -> tui_art.HeroContext:
            ctx = super()._hero_context()
            lane_id, pavilion_id = _activity_lane_pavilion(self.activity_id)
            lane_label = tui_art.LANE_ICONS.get(lane_id, "")
            if lane_label:
                ctx.caption = f"{lane_label} · {self.title}"[:58]
            else:
                ctx.caption = self.title[:58]
            ctx.canton = tui_art.canton_for_lane(lane_id, pavilion_id or None)
            ctx.nat_pass_hint = (
                self.activity_id in tui_art.NAT_ACTIVITY_IDS
                or lane_id == "citizenship_court"
            )
            card = _session_catalog_card(self.session)
            if card:
                ctx.solemn = tui_art.card_is_solemn(card)
                ctx.official_line = tui_art.official_line_for_card(card)
            return ctx

        def _set_status(self, text: str) -> None:
            self.query_one("#status", Static).update(
                f" [bold {INK}]{escape(self.title)}[/bold {INK}] — {escape(text)}"
            )

        def _hide_feedback(self) -> None:
            fb = self.query_one("#feedback", Static)
            fb.update("")
            fb.styles.display = "none"

        def _show_feedback(self, verdict: str, detail: str = "") -> None:
            fb = self.query_one("#feedback", Static)
            lines = [verdict]
            if detail:
                lines.append(f"[{INK_MUTED}]{escape(detail)}[/{INK_MUTED}]")
            fb.update("\n".join(lines))
            fb.styles.display = "block"

        def _render_message(self, heading: str, body: str) -> None:
            self.query_one("#card", Static).update(
                f"[bold {INK}]{escape(heading)}[/bold {INK}]\n\n{escape(body)}"
            )
            self.query_one("#answer-input", Input).placeholder = "Esc — back to fair"

        def _render_step(self) -> None:
            if not self.session or self._done:
                return
            step = self.session.current()
            if step is None:
                self._finish()
                return
            kind = self.session.kind
            card = self.query_one("#card", Static)

            if kind == "browse":
                text = (
                    f"[bold {INK}]{escape(step.get('title', ''))}[/bold {INK}]\n"
                    f"[{INK_MUTED}]{escape(step.get('subtitle', ''))}[/{INK_MUTED}]\n\n"
                    f"{escape(step.get('body', ''))}"
                )
                if step.get("context"):
                    text += f"\n\n[{INK_MUTED}]{escape(step['context'])}[/{INK_MUTED}]"
                if step.get("source"):
                    text += f"\n\n{source_markup(step['source'])}"
                card.update(text)
                n = self.session.index + 1
                self._set_status(f"{n}/{self.session.total} — Enter for next")
                self.query_one("#answer-input", Input).placeholder = "Enter — next card"

            elif kind in ("quiz", "duel", "states"):
                if kind == "duel" and self.session._duel_players:
                    player = self.session.duel_player() or ""
                    sub = f"{player}'s turn"
                else:
                    sub = step.get("category", "") or self.session.activity.get("kind", "")
                card.update(
                    f"[bold {INK}]{escape(step.get('question') or step.get('prompt', ''))}[/bold {INK}]\n"
                    f"[{INK_MUTED}]{escape(sub)}[/{INK_MUTED}]"
                )
                self._set_status(
                    f"Q {self.session.index + 1}/{self.session.total} · score {self.session.score}"
                )
                self.query_one("#answer-input", Input).placeholder = "type your answer"

            elif kind in ("pick", "match"):
                prompt = step.get("prompt") or step.get("quote", "")
                opts = step.get("options", [])
                body = "\n".join(f"  {i + 1}. {opt}" for i, opt in enumerate(opts))
                card.update(f"[bold {INK}]{escape(prompt)}[/bold {INK}]\n\n{body}")
                self._set_status(f"Q {self.session.index + 1}/{self.session.total}")
                self.query_one("#answer-input", Input).placeholder = "enter number"

            elif kind == "sort":
                items = step.get("items", [])
                body = "\n".join(f"  {num}. {label}" for num, label in items)
                card.update(
                    f"[bold {INK}]Timeline Sort[/bold {INK}]\n\n"
                    f"Put these in chronological order (earliest first).\n\n{body}"
                )
                self._set_status("type numbers space-separated, e.g. 3 1 2 4")
                self.query_one("#answer-input", Input).placeholder = "3 1 2 ..."

            self._render_hero()

        def _finish(self) -> None:
            if not self.session:
                return
            self._done = True
            summary = self.session.summary()
            elapsed = summary.get("elapsed_s")
            passed = summary.get("passed")
            medal = bell.medal(summary["score"], summary["total"])
            lines = [
                bell.telegram_plain(self.activity_id, summary["score"], summary["total"], elapsed),
                f"{'PASS' if passed else 'KEEP STUDYING'} — {medal}",
            ]
            if summary.get("duel_scores"):
                ds = summary["duel_scores"]
                lines.append(" · ".join(f"{k}: {v}" for k, v in ds.items()))
            self._render_message("Round complete", "\n".join(lines))
            db.record_score(
                self.activity_id,
                summary["score"],
                summary["total"],
                elapsed,
            )
            if summary["total"] and summary["score"] == summary["total"]:
                self._fireworks()
                self._sparkle(ticks=12)
                self.notify(bell.perfect_plain(), title="Liberty Bell", timeout=6)
            self._set_status("Esc — back to fair")

        def _fireworks(self) -> None:
            overlay = self.query_one("#firework", Static)
            overlay.styles.display = "block"
            state = {"i": 0, "timer": None}

            def tick() -> None:
                if state["i"] >= len(FIREWORK_FRAMES):
                    overlay.styles.display = "none"
                    if state["timer"]:
                        state["timer"].stop()
                    return
                overlay.update(f"[bold {BRASS}]{FIREWORK_FRAMES[state['i']]}[/bold {BRASS}]")
                state["i"] += 1

            state["timer"] = self.set_interval(0.12, tick)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            raw = event.value.strip()
            event.input.value = ""
            if self._done:
                return

            if raw == "109":
                enter_underground(self.app)
                return
            if raw == "1776":
                self._show_feedback(f"[bold {BRASS}]THE BELL:[/bold {BRASS}] Still not the answer.")
                return

            if self.session and self.session.kind == "duel" and self.duel_setup:
                if self.duel_setup == 1:
                    self.duel_names[0] = raw or "Player 1"
                    self.duel_setup = 2
                    self._set_status("enter Player 2 name")
                    self.query_one("#answer-input", Input).placeholder = "Player 2"
                    return
                self.duel_names[1] = raw or "Player 2"
                self.duel_setup = 0
                self.session.setup_duel(self.duel_names[0], self.duel_names[1])
                self._render_step()
                return

            if not self.session:
                return

            self._hide_feedback()
            result = self.session.submit(raw if self.session.kind != "browse" else raw or " ")

            if result.get("timed_out"):
                self._finish()
                return

            if self.session.kind == "browse":
                if result.get("done"):
                    self._finish()
                else:
                    self._render_step()
                return

            if self.session.kind == "sort" and result.get("done"):
                ordered = result.get("ordered", [])
                body = "\n".join(
                    f"  {e['year']} — {e['event']}" for e in ordered
                )
                self._render_message(
                    "Timeline",
                    f"Score {result.get('score', 0)}/{result.get('total', 0)}\n\n{body}",
                )
                db.record_score(
                    "timeline",
                    result.get("score", 0),
                    result.get("total", 0),
                    self.session.elapsed(),
                )
                self._done = True
                self._set_status("Esc — back to fair")
                return

            card_id = result.get("card_id")
            if card_id and self.session.kind in ("quiz", "duel", "states"):
                if result.get("correct"):
                    db.clear_miss(card_id)
                else:
                    db.record_miss(card_id)

            if result.get("correct"):
                verdict = f"[bold {BRASS}]{bell.right_plain()}[/bold {BRASS}]"
                card = None
                cid = result.get("card_id")
                if cid:
                    card = engine.get_catalog().card(str(cid))
                accent = tui_art.card_landmark_accent(card)
                if accent:
                    self._sparkle(ticks=8, accent=accent)
                elif not (self._hero_context().solemn):
                    self._sparkle(ticks=5)
            else:
                expected = result.get("expected", "")
                if isinstance(expected, list):
                    expected = ", ".join(str(x) for x in expected)
                verdict = f"[bold #8b2500]{bell.wrong_plain()}[/bold #8b2500]"
                if expected:
                    self._show_feedback(verdict, f"Accepted: {expected}")
                else:
                    self._show_feedback(verdict)
                if result.get("done"):
                    self._finish()
                else:
                    self._render_step()
                return

            fact = result.get("fact") or result.get("person", "")
            if fact:
                self._show_feedback(verdict, str(fact))
            else:
                self._show_feedback(verdict)

            if result.get("done"):
                self._finish()
            else:
                self._render_step()

        def action_back(self) -> None:
            self.app.pop_screen()

    class SourcesScreen(StageScreen):
        """The Record Room — every source, framed both ways:
        learn more here, and this is where we got the info."""

        BINDINGS = [
            Binding("escape", "back", "Fair map", show=True),
        ]

        CSS = STAGE_CSS + f"""
        SourcesScreen {{
            background: {PARCHMENT};
        }}
        #sources-herald {{
            height: 1;
            padding: 0 2;
            background: {NAVY};
            color: {CREAM};
            border-bottom: heavy {GOLD};
        }}
        #sources-scroll {{
            height: 1fr;
        }}
        #sources-body {{
            padding: 1 2;
            color: {INK};
        }}
        """

        def compose_stage(self) -> ComposeResult:
            yield Static(
                f"[bold {GOLD}]★[/bold {GOLD}] THE RECORD ROOM — sources & further reading",
                id="sources-herald",
            )
            yield VerticalScroll(Static("", id="sources-body"), id="sources-scroll")

        def on_mount(self) -> None:
            self.call_after_refresh(self._render_hero)
            links = engine.load_source_links()
            parts = [
                f"[{INK_MUTED}]Every fact in this fair came from somewhere. These are the "
                f"somewheres — and every one is a fine place to keep going.[/{INK_MUTED}]",
                "",
                f"[bold {NAVY}]WHERE WE GOT THE INFO[/bold {NAVY}]",
            ]
            for r in links.get("resolvers", []):
                parts.append(
                    f"\n[link='{r['url']}'][bold {ACCENT}]⧉ {escape(r['label'])}[/bold {ACCENT}][/link]"
                    f"\n  {escape(r.get('blurb', ''))}"
                    f"\n  [{INK_MUTED}]{escape(r['url'])}[/{INK_MUTED}]"
                )
            parts.append(f"\n[bold {NAVY}]LEARN MORE HERE[/bold {NAVY}]")
            for m in links.get("more", []):
                parts.append(
                    f"\n[link='{m['url']}'][bold {ACCENT}]⧉ {escape(m['label'])}[/bold {ACCENT}][/link]"
                    f"\n  {escape(m.get('blurb', ''))}"
                    f"\n  [{INK_MUTED}]{escape(m['url'])}[/{INK_MUTED}]"
                )
            parts.append(
                f"\n[{INK_MUTED}]Links open in your browser (Ctrl+click in most terminals)."
                f" Esc returns to the fair.[/{INK_MUTED}]"
            )
            self.query_one("#sources-body", Static).update("\n".join(parts))

        def _hero_context(self) -> tui_art.HeroContext:
            ctx = super()._hero_context()
            ctx.record_room = True
            ctx.caption = ""
            return ctx

        def action_back(self) -> None:
            self.app.pop_screen()

    class DebateScreen(Screen):
        """Underground — DIENAMIC palette, real quotes."""

        BINDINGS = [
            Binding("escape", "back", "Surface", show=True),
        ]

        CSS = APP_BASE_CSS + f"""
        DebateScreen {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
        }}
        DebateScreen Static,
        DebateScreen Horizontal,
        DebateScreen VerticalScroll {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
        }}
        DebateScreen ListItem, DebateScreen ListItem Static {{
            background: {DEBATE_BG};
            color: {DEBATE_FG};
        }}
        DebateScreen ListItem.--highlight,
        DebateScreen ListItem.--highlight Static {{
            background: {DEBATE_FG};
            color: {DEBATE_BG};
        }}
        #debate-status {{
            height: 1;
            padding: 0 2;
            border-bottom: heavy {DEBATE_FG};
        }}
        #topic-list {{
            width: 32;
            height: 1fr;
        }}
        #transcript-scroll {{
            width: 1fr;
            height: 1fr;
        }}
        #transcript {{
            height: 1fr;
            padding: 1 2;
        }}
        """

        def __init__(self, topic_index: int | None = None) -> None:
            super().__init__()
            self._topics = engine.load_debate()
            self._topic_index = topic_index
            self._exchange_index = 0
            self._shown_index: int | None = None

        def compose(self) -> ComposeResult:
            yield Static(tui_art.DIENAMIC_LOGO, id="debate-logo")
            yield Static("CONSTITUTIONAL DEBATE — real quotes, cited", id="debate-status")
            with Horizontal():
                yield ListView(id="topic-list")
                yield VerticalScroll(Static("", id="transcript"), id="transcript-scroll")

        def on_mount(self) -> None:
            topic_list = self.query_one("#topic-list", ListView)
            for t in self._topics:
                topic_list.append(ListItem(Static(t["topic"])))
            if self._topic_index is not None:
                topic_list.index = self._topic_index
                self._show_topic(self._topic_index)
            elif self._topics:
                topic_list.index = 0
                self._show_topic(0)
            topic_list.focus()

        def _show_topic(self, index: int) -> None:
            if index < 0 or index >= len(self._topics):
                return
            topic = self._topics[index]
            self._shown_index = index
            self._exchange_index = 0
            self._render_exchange(topic, 0)
            self.query_one("#debate-status", Static).update(
                f" {topic['topic']} — Enter next quote · Esc surface"
            )

        def _render_exchange(self, topic: dict, index: int) -> None:
            exchanges = topic.get("exchanges", [])
            if not exchanges:
                self.query_one("#transcript", Static).update("[dim]No exchanges.[/dim]")
                return
            ex = exchanges[index % len(exchanges)]
            speaker = ex.get("speaker", "")
            color = OBAMA_COLOR if speaker == "Obama" else TRUMP_COLOR if speaker == "Trump" else DEBATE_FG
            citation = ex.get("citation", "")
            cite = span(f"source: {citation}", DEBATE_FG, DEBATE_BG)
            resolved = engine.resolve_source(citation)
            if resolved:
                cite += (
                    f"\n[link='{resolved['url']}'][bold {DEBATE_FG} on {DEBATE_BG}]"
                    f"⧉ learn more — {escape(resolved['label'])}"
                    f"[/bold {DEBATE_FG} on {DEBATE_BG}][/link]"
                )
            text = (
                span(speaker, color, DEBATE_BG, bold=True)
                + "\n"
                + span(f"{ex.get('occasion', '')} — {ex.get('date', '')}", DEBATE_FG, DEBATE_BG)
                + "\n\n"
                + span(f'"{ex.get("quote", "")}"', DEBATE_FG, DEBATE_BG)
                + "\n\n"
                + cite
            )
            self.query_one("#transcript", Static).update(text)

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            # arrow keys change topic; guard so mount/select don't re-reset
            if event.list_view.id == "topic-list" and event.list_view.index is not None:
                if event.list_view.index != self._shown_index:
                    self._show_topic(event.list_view.index)

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            # Enter on the highlighted topic advances through its exchanges
            if event.list_view.id == "topic-list" and self._topics:
                idx = event.list_view.index or 0
                self._exchange_index += 1
                self._render_exchange(self._topics[idx], self._exchange_index)

        def action_back(self) -> None:
            self.app.pop_screen()

    class CivicsFairApp(App):
        TITLE = "Civics Fair"
        SUB_TITLE = "Freedom 250"
        CSS = APP_BASE_CSS

        BINDINGS = [
            Binding("ctrl+c", "quit", "Quit", show=False),
        ]

        def on_mount(self) -> None:
            self.push_screen(FairMapScreen())

        def action_quit(self) -> None:
            self.exit()


def main() -> None:
    if not TEXTUAL_OK:
        print("textual is not installed. Run: pip install -r requirements.txt")
        print("Or: ./dev.sh   ·   CLI fallback: python3 app.py --cli")
        return
    CivicsFairApp().run()


if __name__ == "__main__":
    main()
