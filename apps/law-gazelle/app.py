"""
Law Gazelle — case command center. b17: E472A

Syncs Nest case databases and surfaces urgent flags, deadlines, and open atoms.

Usage:
  python3 app.py
  python3 app.py --sync-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Bump when workflow UI changes — printed at startup so you know which copy is running.
WORKFLOW_UI_VERSION = "today-v1"

import document_store
import gazelle_state
import intelligence
import tui_routes
import workflow
from case_store import (
    bankruptcy_overview,
    check_stale,
    coparent_atoms,
    cross_case_overview,
    legal_documents,
    list_artifacts,
    list_cases,
    milestone_banner,
    session_overview,
    sync_cases,
    urgent_queue,
    workers_comp_atoms,
    workers_comp_overview,
)
from tui_routes import (
    ACTIONABLE_ROUTES,
    MATTER_NAV,
    OPEN_FILE_ROUTES,
    WORKFLOW_CARD_ROUTES,
    RouteFrame,
    breadcrumb_text,
    footer_hints,
)

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import DataTable, Header, Label, ListItem, ListView, Static
    from screens.detail import DetailScreen, NoteModal, SnoozeModal
    from screens.intelligence import IntelligenceScreen
    from screens.workflow import PacketScreen
except ImportError:
    App = None
    DetailScreen = NoteModal = SnoozeModal = None  # type: ignore


def _sync_and_report(source: Path | None = None) -> dict:
    return sync_cases(source or Path.home() / "Desktop" / "Nest")


LawGazelleApp = None

if App is not None:

    class LawGazelleApp(App):
        """Law Gazelle case dashboard — urgent-first drill-down."""

        TITLE = "Law Gazelle"
        SUB_TITLE = f"Today workflow ({WORKFLOW_UI_VERSION})"

        CSS = """
        #workflow-banner {
            height: 1;
            padding: 0 1;
            text-style: bold;
            color: $text;
            background: $primary-darken-2;
            content-align: left middle;
        }
        #breadcrumb {
            height: 1;
            padding: 0 1;
            text-style: bold;
            color: $accent;
            background: $panel;
            content-align: left middle;
        }
        #nav-hint {
            height: auto;
            padding: 0 1;
            color: $text-muted;
            background: $surface;
        }
        #milestones {
            height: auto;
            padding: 0 1;
            color: $warning;
            background: $surface;
        }
        #sync-status {
            height: auto;
            padding: 0 1;
            color: $text-muted;
        }
        #stale-banner {
            height: 1;
            padding: 0 1;
            text-style: bold;
            color: $text;
            background: $warning;
            content-align: left middle;
        }
        #ai-status {
            height: auto;
            padding: 0 1;
            color: $warning;
            background: $surface;
        }
        #route-hints {
            height: 1;
            padding: 0 1;
            color: $text;
            background: $primary-darken-3;
        }
        #main-table {
            height: 1fr;
        }
        #action-deck-list {
            height: 1fr;
            padding: 0 1;
        }
        #action-deck-list ListItem {
            height: 1;
            padding: 0 1;
        }
        """

        BINDINGS = [
            Binding("u", "go_home", "Today", show=True),
            Binding("m", "go_matters", "Matters", show=True),
            Binding("d", "go_drafts", "Drafts", show=True),
            Binding("s", "go_session", "Session", show=True),
            Binding("a", "go_activity", "Activity", show=True),
            Binding("r", "refresh", "Refresh", show=True),
            Binding("escape", "go_back", "Back", show=True),
            Binding("v", "open_detail", "Detail", show=False),
            Binding("x", "mark_done", "Done", show=False),
            Binding("n", "add_note", "Note", show=False),
            Binding("z", "snooze", "Snooze", show=False),
            Binding("t", "toggle_resolved", "Resolved", show=False),
            Binding("i", "ai_rank_today", "Rank", show=False),
            Binding("o", "open_file", "Open", show=False),
            Binding("f", "ai_inspect_fact", "Inspect Fact", show=False),
            Binding("shift+f", "ai_inspect_fact_force", "Re-inspect", show=False),
            Binding("1", "fact_verified", "Verified", show=False),
            Binding("2", "fact_needs_source", "Needs Source", show=False),
            Binding("3", "fact_do_not_use", "Do Not Use", show=False),
            Binding("q", "quit", "Quit", show=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.show_resolved = False
            self._item_by_key: dict[str, dict] = {}
            self._route_stack: list[RouteFrame] = [
                RouteFrame("home", label="Today"),
            ]
            self._last_sync: dict | None = None
            self._stale_files: list[str] = []
            self._active_card: dict | None = None
            self._deck_entries: list[dict] = []
            self._pending_ai_title: str = ""
            self._pending_ai_allow_save: bool = False
            self._ai_busy = False
            self._ai_started_at = 0.0
            self._ai_status_message = ""

        @property
        def _current_route(self) -> str:
            return self._route_stack[-1].route if self._route_stack else "home"

        @property
        def _current_params(self) -> dict:
            return self._route_stack[-1].params if self._route_stack else {}

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static(
                f"Law Gazelle · Today workflow {WORKFLOW_UI_VERSION}",
                id="workflow-banner",
            )
            yield Static("› Today", id="breadcrumb")
            yield Static(
                "Columns: Status · Matter · Next Action · Why · Title — pick a row, press Enter",
                id="nav-hint",
            )
            yield Static("", id="milestones")
            yield Static("", id="stale-banner")
            yield Static("", id="sync-status")
            yield Static("", id="ai-status")
            yield DataTable(id="main-table", zebra_stripes=True)
            yield ListView(id="action-deck-list")
            yield Static("", id="route-hints")

        def on_mount(self) -> None:
            self.action_refresh()
            self.set_interval(1.0, self._update_ai_status)
            self.call_after_refresh(self._post_mount_notify)

        def _post_mount_notify(self) -> None:
            self.notify(
                "Today workflow: Enter opens action deck (5 steps). "
                "If you still see 8 tabs (Urgent, Coparent, …), quit and run ./dev.sh from apps/law-gazelle.",
                severity="information",
                timeout=12,
            )

        def _main_table(self) -> DataTable:
            return self.query_one("#main-table", DataTable)

        def _deck_list(self) -> ListView:
            return self.query_one("#action-deck-list", ListView)

        @staticmethod
        def _item_key(item: dict) -> str:
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
            return f"{source_db}|{item_type}|{item_id}"

        def _register_item(self, item: dict) -> str:
            key = self._item_key(item)
            self._item_by_key[key] = item
            return key

        def _configure_table(self, table: DataTable) -> None:
            table.cursor_type = "row"
            table.show_header = self._current_route != "action_deck"
            table.zebra_stripes = self._current_route != "action_deck"

        def _item_from_row_key(self, row_key) -> dict | None:
            key = getattr(row_key, "value", None) or str(row_key)
            return self._item_by_key.get(str(key))

        def _selected_item(self) -> dict | None:
            table = self._main_table()
            try:
                cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
                return self._item_from_row_key(cell_key[0])
            except Exception:
                return None

        def _selected_deck_step(self) -> dict | None:
            deck = self._deck_list()
            index = deck.index
            if index is None:
                return None
            if 0 <= index < len(self._deck_entries):
                return self._deck_entries[index]
            return None

        def _add_item_row(self, table: DataTable, item: dict, *cells: str) -> None:
            row_key = self._register_item(item)
            table.add_row(*cells, key=row_key)

        def _update_chrome(self) -> None:
            trail = breadcrumb_text(self._route_stack)
            self.query_one("#breadcrumb", Static).update(f"› {trail}")
            route = self._current_route
            self.sub_title = trail
            nav_hint = self.query_one("#nav-hint", Static)
            if route == "home":
                nav_hint.display = "block"
                nav_hint.update(
                    "Enter = action deck for selected work · m matters · d drafts · s session · a activity"
                )
            elif route == "action_deck" and self._active_card:
                nav_hint.display = "block"
                nav_hint.update(
                    f"Work item: {self._active_card.get('title', 'Untitled')} · choose one action below"
                )
            else:
                nav_hint.display = "none"
            self.query_one("#route-hints", Static).update(
                footer_hints(route, show_resolved=self.show_resolved)
            )
            stale_widget = self.query_one("#stale-banner", Static)
            if self._stale_files:
                stale_widget.display = "block"
                stale_widget.update(
                    f"⚠ {len(self._stale_files)} case file(s) stale in Nest — press R to sync: "
                    + ", ".join(self._stale_files)
                )
            else:
                stale_widget.display = "none"
            if self._last_sync:
                result = self._last_sync
                copied = ", ".join(result["copied"]) or "none"
                missing = ", ".join(result["missing"]) or "none"
                self.query_one("#sync-status", Static).update(
                    f"Synced → {result['dest']} | copied: {copied} | missing: {missing}"
                )
            self._update_ai_status()

        def _set_ai_status(self, message: str, *, busy: bool) -> None:
            self._ai_busy = busy
            self._ai_status_message = message
            self._ai_started_at = time.monotonic() if busy else 0.0
            self._update_ai_status()

        def _clear_ai_status(self) -> None:
            self._ai_busy = False
            self._ai_status_message = ""
            self._ai_started_at = 0.0
            self._update_ai_status()

        def _update_ai_status(self) -> None:
            try:
                status = self.query_one("#ai-status", Static)
            except Exception:
                return
            if not self._ai_status_message:
                status.display = "none"
                status.update("")
                return
            status.display = "block"
            if self._ai_busy and self._ai_started_at:
                elapsed = int(time.monotonic() - self._ai_started_at)
                status.update(f"AI working ({elapsed}s): {self._ai_status_message}")
            else:
                status.update(self._ai_status_message)

        def _push_route(self, route: str, *, params: dict | None = None, label: str = "") -> None:
            params = params or {}
            if not label:
                if route == "matter_items":
                    matter = params.get("matter", "")
                    label = tui_routes.ROUTE_LABELS.get(matter, matter.replace("_", " ").title())
                else:
                    label = tui_routes.ROUTE_LABELS.get(route, route)
            self._route_stack.append(RouteFrame(route, params=params, label=label))
            self._render_current_route()

        def _pop_route(self) -> None:
            if len(self._route_stack) > 1:
                self._route_stack.pop()
                self._render_current_route()

        def _reset_to_home(self) -> None:
            self._route_stack = [RouteFrame("home", label="Today")]
            self._active_card = None
            self._render_current_route()

        def _render_current_route(self) -> None:
            self._item_by_key.clear()
            table = self._main_table()
            deck = self._deck_list()
            table.clear(columns=True)
            deck.clear()
            self._deck_entries = []
            route = self._current_route
            params = self._current_params

            is_action_deck = route == "action_deck"
            table.display = not is_action_deck
            deck.display = is_action_deck

            if is_action_deck:
                self._load_route_action_deck_list(deck, params)
                self._update_chrome()
                deck.focus()
                return

            loaders = {
                "home": self._load_route_home,
                "fact_review": self._load_route_fact_review,
                "activity": self._load_route_activity,
                "matters": self._load_route_matters,
                "matter_items": self._load_route_matter_items,
                "drafts": self._load_route_drafts,
                "session": self._load_route_session,
            }
            loader = loaders.get(route)
            if loader:
                loader(table, params)
            self._configure_table(table)
            self._update_chrome()
            table.focus()

        def action_refresh(self) -> None:
            self._stale_files = check_stale()
            self._last_sync = _sync_and_report()
            self._stale_files = check_stale()  # re-check after sync
            self.query_one("#milestones", Static).update(milestone_banner())
            self._render_current_route()

        def action_go_home(self) -> None:
            self._reset_to_home()

        def action_go_matters(self) -> None:
            if self._current_route == "matters":
                return
            self._push_route("matters")

        def action_go_drafts(self) -> None:
            if self._current_route == "drafts":
                return
            self._route_stack = [RouteFrame("home", label="Today"), RouteFrame("drafts", label="Drafts")]
            self._render_current_route()

        def action_go_session(self) -> None:
            if self._current_route == "session":
                return
            self._route_stack = [
                RouteFrame("home", label="Today"),
                RouteFrame("session", label="Session"),
            ]
            self._render_current_route()

        def action_go_activity(self) -> None:
            if self._current_route == "activity":
                return
            self._route_stack = [
                RouteFrame("home", label="Today"),
                RouteFrame("activity", label="Activity"),
            ]
            self._render_current_route()

        def action_go_back(self) -> None:
            if len(self._route_stack) > 1:
                leaving = self._route_stack[-1].route
                self._pop_route()
                if leaving in ("action_deck", "fact_review", "packet"):
                    if self._route_stack[-1].route == "home":
                        self._active_card = None
            else:
                self.notify("Already on Today.", severity="information")

        def action_toggle_resolved(self) -> None:
            if self._current_route != "home":
                self.notify("Toggle resolved only on Today home.", severity="warning")
                return
            self.show_resolved = not self.show_resolved
            self._render_current_route()

        def _open_action_deck(self, card: dict) -> None:
            self._active_card = card
            title = (card.get("title") or "Work item")[:40]
            self._push_route("action_deck", params={"card": card}, label=title)

        def _run_ai_job(
            self,
            title: str,
            fn,
            *,
            allow_save: bool = False,
            cache_peek: tuple[str, str] | None = None,
        ) -> None:
            """Run intelligence function in a background worker (local Ollama)."""
            self._pending_ai_title = title
            self._pending_ai_allow_save = allow_save
            cached = None
            if cache_peek:
                cached = gazelle_state.get_ai_cache(cache_peek[0], fingerprint=cache_peek[1])
            if cached:
                self._set_ai_status(f"{title} (sidecar cache)", busy=True)
                self.notify(
                    "Recovered prior result from sidecar — no Ollama call",
                    severity="information",
                )
            else:
                self._set_ai_status(f"{title} via local Ollama", busy=True)
                self.notify(
                    "Calling local Ollama — this may take a minute...",
                    severity="information",
                )

            def work():
                return fn()

            self.run_worker(work, thread=True, name="law_gazelle_ai", exclusive=True)

        def on_worker_state_changed(self, event) -> None:
            if getattr(event.worker, "name", None) != "law_gazelle_ai":
                return
            if not event.worker.is_finished:
                return
            title = self._pending_ai_title or "AI Result"
            allow_save = getattr(self, "_pending_ai_allow_save", False)
            try:
                result = event.worker.result
            except Exception as exc:
                self._set_ai_status(f"AI error: {exc}", busy=False)
                self.notify(f"AI error: {exc}", severity="error")
                return
            if not isinstance(result, dict):
                self._set_ai_status("AI returned unexpected result", busy=False)
                self.notify("AI returned unexpected result", severity="error")
                return
            if not result.get("ok"):
                self._set_ai_status(result.get("error") or "AI failed", busy=False)
                self.notify(result.get("error") or "AI failed", severity="error")
                return
            meta_parts = []
            if result.get("cached"):
                when = (result.get("cached_at") or "")[:19]
                meta_parts.append(f"cached sidecar{(' @ ' + when) if when else ''}")
            elif result.get("model"):
                meta_parts.append(f"model: {result['model']}")
            if result.get("context_sources"):
                meta_parts.append(f"sources: {', '.join(result['context_sources'][:8])}")
            meta = " · ".join(meta_parts)
            suggested = result.get("suggested_filename") if allow_save else None
            draft_body = result.get("text") if allow_save else None
            self._clear_ai_status()
            self.push_screen(
                IntelligenceScreen(
                    title,
                    result.get("text", ""),
                    meta=meta,
                    suggested_filename=suggested,
                    draft_body=draft_body,
                )
            )

        def action_ai_rank_today(self) -> None:
            if self._current_route != "home":
                self.notify("Rank Today only on Today home.", severity="warning")
                return
            cards = workflow.today_cards(show_resolved=self.show_resolved)
            self._run_ai_job(
                "Today — priority ranking",
                lambda: intelligence.rank_today(cards),
                cache_peek=intelligence.rank_cache_key(cards),
            )

        def action_ai_inspect_fact(self, *, force: bool = False) -> None:
            if self._current_route != "fact_review":
                self.notify("Inspect Fact only on Review Facts.", severity="warning")
                return
            row = self._selected_item()
            if not row or not row.get("atom_id") or row.get("atom_id") == "none":
                self.notify("Select a fact row first.", severity="warning")
                return
            cache_peek = None if force else intelligence.fact_inspection_cache_key(row)
            self._run_ai_job(
                f"Inspect fact: {row.get('atom_id')}",
                lambda: intelligence.inspect_fact_row(row, force=force),
                cache_peek=cache_peek,
            )

        def action_ai_inspect_fact_force(self) -> None:
            self.action_ai_inspect_fact(force=True)

        def _execute_deck_step(self, step: dict) -> None:
            step_id = step.get("step_id", "")
            card = step.get("card") or self._active_card
            if not card:
                return
            self._active_card = card
            if step_id == workflow.DECK_TRIAGE:
                self.notify("Triage: n = note · z = snooze · x = mark done", severity="information")
                return
            if step_id == workflow.DECK_BUILD_PACKET:
                body = workflow.build_packet_markdown(card)
                title = f"Packet: {card.get('title', '')}"
                self.push_screen(PacketScreen(title, body))
                gazelle_state.log_activity(
                    "draft_packet",
                    f"Opened drafting packet for {card.get('card_id', '')}",
                    source_db=(card.get("source_item") or {}).get("source_db"),
                    item_type=(card.get("source_item") or {}).get("item_type"),
                    item_id=(card.get("source_item") or {}).get("item_id"),
                )
                return
            if step_id == workflow.DECK_DRAFT:
                body = workflow.build_packet_markdown(card)
                self.push_screen(PacketScreen(f"Packet: {card.get('title', '')}", body))
                return
            if step_id == workflow.DECK_AI_BRIEF:
                self._run_ai_job(
                    f"Brief: {card.get('title', '')}",
                    lambda: intelligence.brief_card(card),
                    cache_peek=intelligence.brief_cache_key(card),
                )
                return
            if step_id == workflow.DECK_AI_DRAFT:
                self._run_ai_job(
                    f"Draft: {card.get('title', '')}",
                    lambda: intelligence.draft_from_card(card),
                    allow_save=True,
                    cache_peek=intelligence.draft_cache_key(card),
                )
                return
            if step_id == workflow.DECK_REVIEW_FACTS:
                self._push_route("fact_review", params={"card": card}, label="Facts")
                return
            if step_id == workflow.DECK_SOURCE_DETAIL:
                src = card.get("source_item") or {}
                source_db = src.get("source_db") or src.get("case", "")
                item_type = src.get("item_type") or src.get("kind", "")
                item_id = src.get("item_id") or src.get("flag_id") or src.get("atom_id", "")
                if item_id and item_type not in ("deadline",):
                    self.push_screen(DetailScreen(source_db, item_type, item_id))
                else:
                    self.notify("Use Build Packet for deadline-level work.", severity="warning")

        def _show_detail(self, item: dict) -> None:
            route = self._current_route
            if route == "home" and item.get("item_type") == "action_card":
                self._open_action_deck(item)
                return
            if route == "action_deck" and item.get("item_type") == "deck_step":
                self._execute_deck_step(item)
                return
            if item.get("item_type") == "matter_nav":
                matter = item.get("matter_key") or item.get("item_id")
                self._push_route("matter_items", params={"matter": matter}, label="")
                return
            if item.get("item_type") == "draft":
                path = item.get("path")
                if path:
                    subprocess.Popen(
                        ["xdg-open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return
            if item.get("item_type") == "fact_review":
                detail = item.get("detail") or {}
                atom = detail.get("atom") or {}
                atom_id = item.get("atom_id") or atom.get("atom_id") or item.get("item_id")
                source_db = ((item.get("card") or {}).get("source_item") or {}).get("source_db", "coparent")
                if atom_id and atom_id != "none":
                    self.push_screen(DetailScreen(source_db, "atom", atom_id))
                else:
                    self.notify("No atom detail for this fact row.", severity="warning")
                return
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
            if not item_id or item_type in ("session_meta", "commit_manifest"):
                self.notify("No detail for this row.", severity="warning")
                return
            self.push_screen(DetailScreen(source_db, item_type, item_id))

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            item = self._item_from_row_key(event.row_key)
            if item:
                self._show_detail(item)

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            if getattr(event.list_view, "id", None) != "action-deck-list":
                return
            step = self._selected_deck_step()
            if step:
                self._execute_deck_step(step)

        def action_open_detail(self) -> None:
            if self._current_route == "action_deck":
                step = self._selected_deck_step()
                if step:
                    self._execute_deck_step(step)
                else:
                    self.notify("Select an action, then press Enter.", severity="information")
                return
            item = self._selected_item()
            if item:
                self._show_detail(item)
            else:
                self.notify("Select a row, then Enter or v.", severity="information")

        def _triage_target(self) -> dict | None:
            """Underlying case item for triage actions on workflow screens."""
            if self._current_route in WORKFLOW_CARD_ROUTES and self._active_card:
                return self._active_card.get("source_item")
            item = self._selected_item()
            if not item:
                return None
            if item.get("item_type") == "action_card":
                return item.get("source_item")
            if self._current_route not in ACTIONABLE_ROUTES:
                self.notify("Not available on this screen.", severity="warning")
                return None
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
            if not item_id or item.get("item_type") in ("matter_nav", "case", "commit_manifest", "deck_step"):
                return None
            return item

        def action_mark_done(self) -> None:
            item = self._triage_target()
            if not item:
                return
            gazelle_state.mark_resolved(
                item.get("source_db") or item.get("case", ""),
                item.get("item_type") or item.get("kind", ""),
                item.get("item_id") or item.get("flag_id") or item.get("atom_id", ""),
            )
            self.action_refresh()

        def action_add_note(self) -> None:
            item = self._triage_target()
            if not item:
                return
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")

            def save_note(body: str | None) -> None:
                if body:
                    gazelle_state.add_note(source_db, item_type, item_id, body)
                    self.action_refresh()

            self.push_screen(NoteModal(source_db, item_type, item_id), save_note)

        def action_snooze(self) -> None:
            item = self._triage_target()
            if not item:
                return
            source_db = item.get("source_db") or item.get("case", "")
            item_type = item.get("item_type") or item.get("kind", "")
            item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")

            def apply_snooze(until: str | None) -> None:
                if until:
                    gazelle_state.snooze_until(source_db, item_type, item_id, until)
                    self.action_refresh()

            self.push_screen(SnoozeModal(), apply_snooze)

        def _set_fact_verification(self, status: str) -> None:
            if self._current_route != "fact_review":
                return
            row = self._selected_item()
            if not row or not row.get("atom_id"):
                self.notify("Select a fact row first.", severity="warning")
                return
            gazelle_state.set_fact_verification("coparent", "atom", row["atom_id"], status)
            self._render_current_route()

        def action_fact_verified(self) -> None:
            self._set_fact_verification("verified")

        def action_fact_needs_source(self) -> None:
            self._set_fact_verification("needs_source")

        def action_fact_do_not_use(self) -> None:
            self._set_fact_verification("do_not_use")

        def action_open_file(self) -> None:
            if self._current_route not in OPEN_FILE_ROUTES:
                self.notify("Open only on Drafts or Session.", severity="warning")
                return
            item = self._selected_item()
            if self._current_route == "drafts":
                path = item.get("path") if item else None
                if not path:
                    self.notify("No draft selected.", severity="warning")
                    return
                subprocess.Popen(
                    ["xdg-open", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            if item and item.get("item_type") == "artifact":
                path = item.get("path")
                if path:
                    subprocess.Popen(
                        ["xdg-open", path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return
            arts = list_artifacts()
            if arts:
                subprocess.Popen(
                    ["xdg-open", arts[0]["path"]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

        # ── Route loaders ─────────────────────────────────────────────────────

        def _load_route_home(self, table: DataTable, _params: dict) -> None:
            table.add_columns("Status", "Matter", "Next Action", "Why", "Title")
            for card in workflow.today_cards(show_resolved=self.show_resolved):
                self._add_item_row(
                    table,
                    card,
                    card.get("status_label", ""),
                    card.get("matter", ""),
                    (card.get("recommended_action_label") or "")[:28],
                    (card.get("why") or "")[:45],
                    (card.get("title") or "")[:40],
                )

        def _load_route_action_deck(self, table: DataTable, params: dict) -> None:
            card = params.get("card") or self._active_card
            if not card:
                table.add_columns("Error")
                table.add_row("No work item selected")
                return
            self._active_card = card
            table.add_columns("Key", "Action", "Purpose")
            for entry in workflow.action_deck_entries(card):
                label = entry.get("label", "")
                key, _, action = label.partition(". ")
                description = entry.get("description") or ""
                self._add_item_row(
                    table,
                    entry,
                    key,
                    action,
                    description,
                )

        def _load_route_action_deck_list(self, deck: ListView, params: dict) -> None:
            card = params.get("card") or self._active_card
            if not card:
                self._deck_entries = []
                deck.append(ListItem(Label("No work item selected")))
                return
            self._active_card = card
            self._deck_entries = workflow.action_deck_entries(card)
            for entry in self._deck_entries:
                label = entry.get("label", "")
                key, _, action = label.partition(". ")
                description = entry.get("description") or ""
                row = f"{key:>2}  {action:<18} {description}"
                deck.append(ListItem(Label(row)))
            deck.index = 0

        def _load_route_fact_review(self, table: DataTable, params: dict) -> None:
            card = params.get("card") or self._active_card
            if card:
                self._active_card = card
            table.add_columns("Status", "Fact", "What to check", "Source", "Action")
            for row in workflow.fact_review_rows(card or {}):
                self._add_item_row(
                    table,
                    row,
                    row.get("review_status", workflow.verification_label(row.get("verification"))),
                    (row.get("fact") or "")[:42],
                    (row.get("case_summary") or "")[:58],
                    (row.get("source_summary") or row.get("evidence") or "")[:35],
                    (row.get("review_action") or "")[:42],
                )

        def _load_route_activity(self, table: DataTable, _params: dict) -> None:
            table.add_columns("When", "Event", "Summary")
            events = gazelle_state.list_activity(limit=40)
            if not events:
                table.add_row("—", "—", "No activity yet — triage, notes, and drafts appear here")
                return
            for i, ev in enumerate(events):
                created = ev.get("created_at") or ""
                item = {
                    **ev,
                    "source_db": "workflow",
                    "item_type": "activity",
                    "item_id": f"{created}:{i}",
                }
                self._add_item_row(
                    table,
                    item,
                    (ev.get("created_at") or "")[:19],
                    ev.get("event_type", ""),
                    (ev.get("summary") or "")[:60],
                )

        def _load_route_matters(self, table: DataTable, _params: dict) -> None:
            table.add_columns("Matter", "Scope")
            for matter_key, title, desc in MATTER_NAV:
                item = {
                    "source_db": "nav",
                    "item_type": "matter_nav",
                    "item_id": matter_key,
                    "matter_key": matter_key,
                }
                self._add_item_row(table, item, title, desc)

        def _load_route_matter_items(self, table: DataTable, params: dict) -> None:
            matter = params.get("matter", "coparent")
            if matter == "coparent":
                self._load_matter_coparent(table)
            elif matter == "bankruptcy":
                self._load_matter_bankruptcy(table)
            elif matter == "workers_comp":
                self._load_matter_workers_comp(table)
            elif matter == "cross_case":
                self._load_matter_cross_case(table)
            elif matter == "cases":
                self._load_matter_cases(table)
            else:
                table.add_columns("Error")
                table.add_row(f"Unknown matter: {matter}")

        def _load_matter_coparent(self, table: DataTable) -> None:
            table.add_columns("Type", "ID", "Status", "Title", "Date/Action")
            for doc in legal_documents():
                item = {
                    "source_db": "coparent",
                    "item_type": "legal_document",
                    "item_id": doc["doc_id"],
                    "kind": "legal_document",
                    **doc,
                }
                date_label = doc.get("effective_date") or doc.get("signed_date") or doc.get("filed_date") or ""
                self._add_item_row(
                    table,
                    item,
                    doc.get("doc_type") or "document",
                    doc.get("doc_id", ""),
                    doc.get("verified_label", ""),
                    (doc.get("title") or "")[:60],
                    date_label,
                )
            for atom in coparent_atoms(status="open"):
                item = {
                    "source_db": "coparent",
                    "item_type": "atom",
                    "item_id": atom["atom_id"],
                    "kind": "atom",
                    **atom,
                }
                self._add_item_row(
                    table,
                    item,
                    "atom",
                    atom.get("atom_id", ""),
                    atom.get("priority", ""),
                    (atom.get("title") or "")[:60],
                    (atom.get("action_required") or "")[:80],
                )

        def _load_matter_bankruptcy(self, table: DataTable) -> None:
            table.add_columns("Type", "Severity/Status", "Item", "Deadline/Notes")
            overview = bankruptcy_overview()
            for case in overview.get("cases") or []:
                table.add_row(
                    "case",
                    case.get("status", ""),
                    f"Ch.{case.get('chapter')} {case.get('case_id')}",
                    (case.get("notes") or "")[:80],
                )
            for flag in overview.get("flags") or []:
                item = {
                    "source_db": "bankruptcy",
                    "item_type": "flag",
                    "item_id": flag["flag_id"],
                    "kind": "flag",
                    **flag,
                }
                self._add_item_row(
                    table,
                    item,
                    "flag",
                    flag.get("severity", ""),
                    flag.get("title", ""),
                    flag.get("deadline") or (flag.get("action_required") or "")[:80],
                )
            for doc in overview.get("checklist") or []:
                table.add_row(
                    "checklist",
                    doc.get("status", ""),
                    doc.get("doc_type", ""),
                    doc.get("priority", ""),
                )

        def _load_matter_workers_comp(self, table: DataTable) -> None:
            table.add_columns("ID", "Priority", "Domain", "Title", "Action")
            if not workers_comp_overview():
                table.add_row(
                    "—",
                    "—",
                    "—",
                    "workers_comp.db not in Nest",
                    "Run: python3 scripts/scaffold_workers_comp.py",
                )
                return
            for atom in workers_comp_atoms(status="open"):
                item = {
                    "source_db": "workers_comp",
                    "item_type": "atom",
                    "item_id": atom["atom_id"],
                    "kind": "atom",
                    **atom,
                }
                self._add_item_row(
                    table,
                    item,
                    atom.get("atom_id", ""),
                    atom.get("priority", ""),
                    atom.get("domain", ""),
                    (atom.get("title") or "")[:60],
                    (atom.get("action_required") or "")[:80],
                )

        def _load_matter_cross_case(self, table: DataTable) -> None:
            table.add_columns("Type", "Issue/Party", "Bankruptcy", "Coparent/Context")
            overview = cross_case_overview()
            for x in overview.get("intersections") or []:
                item = {
                    "source_db": "bankruptcy",
                    "item_type": "intersection",
                    "item_id": x.get("issue", ""),
                    **x,
                }
                self._add_item_row(
                    table,
                    item,
                    "intersection",
                    (x.get("issue") or "")[:40],
                    (x.get("bankruptcy_impact") or "")[:50],
                    (x.get("coparent_impact") or "")[:50],
                )
            for c in overview.get("creditors") or []:
                item = {
                    "source_db": "bankruptcy",
                    "item_type": "creditor",
                    "item_id": c.get("creditor_id") or str(c.get("id", "")),
                    **c,
                }
                self._add_item_row(
                    table,
                    item,
                    "creditor",
                    c.get("name", ""),
                    c.get("debt_type", ""),
                    f"${c.get('amount_owed') or '—'}",
                )
            for ev in overview.get("context_events") or []:
                item = {
                    "source_db": "coparent",
                    "item_type": "context_event",
                    "item_id": str(ev.get("id", "")),
                    **ev,
                }
                self._add_item_row(
                    table,
                    item,
                    "context",
                    ev.get("event_type", ""),
                    (ev.get("description") or "")[:50],
                    ev.get("effective_date", ""),
                )

        def _load_matter_cases(self, table: DataTable) -> None:
            table.add_columns("Case", "Number", "Status", "Open Items", "Jurisdiction")
            for case in list_cases():
                item = {
                    "source_db": case["key"],
                    "item_type": "case",
                    "item_id": case["key"],
                    **case,
                }
                self._add_item_row(
                    table,
                    item,
                    case["title"],
                    case.get("case_number", ""),
                    case.get("status", ""),
                    str(case.get("open_items", 0)),
                    case.get("jurisdiction", "")[:50],
                )

        def _load_route_drafts(self, table: DataTable, _params: dict) -> None:
            table.add_columns("Name", "Size", "Modified", "Path")
            drafts = document_store.list_drafts()
            if not drafts:
                table.add_row("—", "—", "—", "No drafts yet — use gazelle_draft to generate one")
                return
            for d in drafts:
                item = {
                    "source_db": "drafts",
                    "item_type": "draft",
                    "item_id": d["name"],
                    **d,
                }
                self._add_item_row(
                    table,
                    item,
                    d["name"],
                    f"{d['size_kb']} KB",
                    d["modified"],
                    d["path"],
                )

        def _load_route_session(self, table: DataTable, _params: dict) -> None:
            table.add_columns("Type", "Key", "Value")
            overview = session_overview()
            last_commit = overview.get("last_commit")
            if last_commit and not last_commit.get("error"):
                commit_id = last_commit.get("session_date") or last_commit.get("name", "commit")
                item = {
                    "source_db": "session",
                    "item_type": "commit_manifest",
                    "item_id": commit_id,
                    **last_commit,
                }
                summary = (last_commit.get("summary") or "")[:80]
                files_n = last_commit.get("file_count", len(last_commit.get("files") or []))
                self._add_item_row(
                    table,
                    item,
                    "commit",
                    last_commit.get("name", "legal_commit"),
                    f"{summary} · {files_n} files · {last_commit.get('modified', '—')}",
                )
            elif last_commit and last_commit.get("error"):
                item = {
                    "source_db": "session",
                    "item_type": "commit_manifest",
                    "item_id": "error",
                    **last_commit,
                }
                self._add_item_row(
                    table,
                    item,
                    "commit",
                    last_commit.get("name", "manifest"),
                    last_commit["error"],
                )

            if not overview.get("present"):
                item = {
                    "source_db": "session",
                    "item_type": "session_meta",
                    "item_id": "status",
                    "key": "session_meta.db",
                    "value": "not synced",
                }
                self._add_item_row(table, item, "status", "session_meta.db", "not synced")
                return
            for key, value in overview.get("meta", {}).items():
                item = {
                    "source_db": "session",
                    "item_type": "session_meta",
                    "item_id": key,
                    "key": key,
                    "value": value,
                }
                self._add_item_row(table, item, "meta", key, str(value)[:100])
            for art in overview.get("artifacts") or []:
                item = {
                    "source_db": "session",
                    "item_type": "artifact",
                    "item_id": art.get("name", ""),
                    **art,
                }
                self._add_item_row(
                    table,
                    item,
                    "artifact",
                    art.get("name", ""),
                    f"{art.get('size_kb', '?')} KB · o to open",
                )
            for dec in overview.get("decisions") or []:
                decision_id = dec.get("id")
                if decision_id is None:
                    decision_id = (dec.get("decision") or "")[:40]
                item = {
                    "source_db": "session",
                    "item_type": "session_decision",
                    "item_id": str(decision_id),
                    **dec,
                }
                self._add_item_row(
                    table,
                    item,
                    "decision",
                    (dec.get("decision") or "")[:60],
                    (dec.get("rationale") or "")[:100],
                )


def _cli_fallback() -> int:
    """Plain-text dashboard when Textual is not installed."""
    result = _sync_and_report()
    print(milestone_banner())
    print(f"Synced → {result['dest']}")
    print(f"  copied:  {', '.join(result['copied']) or 'none'}")
    print(f"  missing: {', '.join(result['missing']) or 'none'}")
    print()

    print("=== URGENT QUEUE ===")
    for item in urgent_queue():
        sev = item.get("severity") or item.get("priority") or "?"
        title = item.get("title") or item.get("flag_id") or item.get("atom_id")
        dl = item.get("deadline") or "—"
        days = item.get("days_until", "—")
        print(f"  [{item.get('case')}] {sev:8} {str(days):>4}d {dl:12} {title}")

    print("\n=== CASES ===")
    for case in list_cases():
        print(f"  {case['title']:28} {case.get('case_number',''):16} {case.get('status','')}")

    print("\n=== CROSS-CASE ===")
    cc = cross_case_overview()
    for x in cc.get("intersections") or []:
        print(f"  {x.get('issue')}")

    wc = workers_comp_overview()
    print("\n=== WORKERS COMP ===")
    if wc is None:
        print("  workers_comp.db not found — run scripts/scaffold_workers_comp.py")
    else:
        for a in wc.get("atoms") or []:
            print(f"  {a.get('atom_id')}: {a.get('title')}")

    session = session_overview()
    print("\n=== SESSION ===")
    last_commit = session.get("last_commit")
    if last_commit and not last_commit.get("error"):
        print(
            f"  last commit: {last_commit.get('name')} — "
            f"{last_commit.get('summary', '')} ({last_commit.get('file_count', 0)} files)"
        )
    if not session.get("present"):
        print("  session_meta.db not synced")
    else:
        for key in (
            "session_date",
            "session_outcome",
            "letter_sent",
            "response_deadline_1",
            "response_deadline_2",
        ):
            if key in session.get("meta", {}):
                print(f"  {key}: {session['meta'][key]}")

    return 0


def print_ui_identity() -> None:
    """stderr banner so terminal shows which app.py launched."""
    here = Path(__file__).resolve()
    print(
        f"Law Gazelle UI: WORKFLOW {WORKFLOW_UI_VERSION} | {here}",
        file=sys.stderr,
    )
    if App is None:
        print("  (Textual not installed — plain CLI fallback)", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Law Gazelle case command center")
    parser.add_argument("--sync-only", action="store_true", help="Sync databases and exit")
    parser.add_argument(
        "--check-ui",
        action="store_true",
        help="Print workflow UI version and app path, then exit",
    )
    parser.add_argument("--source", type=Path, default=Path.home() / "Desktop" / "Nest")
    args = parser.parse_args()

    if args.check_ui:
        print_ui_identity()
        print(f"textual_installed={App is not None}")
        print(f"workflow_module={Path(__file__).parent / 'workflow.py'}")
        return 0

    result = sync_cases(args.source)
    if args.sync_only:
        print(json_dump(result))
        return 0

    print_ui_identity()

    if App is None:
        return _cli_fallback()

    app = LawGazelleApp()
    app.run()
    return 0


def json_dump(obj: dict) -> str:
    import json

    return json.dumps(obj, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
