# askjeles/crown.py
"""
AskJeles TUI — Jeles, your AI librarian (search-first).

Layout inspired by googler/fzf: verified hits with URLs, Enter opens browser,
optional Jeles synthesis on demand.

Launch:
  python -m askjeles.crown              # Textual TUI (default)
  python -m askjeles.crown --serve      # FastAPI verification API
  python -m askjeles.crown --trivia     # literary trivia TUI
"""
from __future__ import annotations

import dataclasses
import logging
import time
from pathlib import Path
from typing import Any, Optional

from askjeles import trivia as _trivia
from askjeles.browser import open_url
from askjeles.willow_path import bootstrap as _bootstrap_willow

_willow_root = _bootstrap_willow()

from askjeles.search import available as search_available
from askjeles.search import search_stacks, snippet_block, synthesize_answer

_LOG_PATH = Path.home() / ".willow" / "jeles.log"
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_LOG_PATH),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jeles")

try:
    from core.llm_edge import respond as llm_respond

    _LLM_AVAILABLE = True
except ImportError as exc:
    log.warning("llm_edge unavailable: %s", exc)
    _LLM_AVAILABLE = False

_JELES_AVAILABLE = search_available() and _LLM_AVAILABLE

try:
    from askjeles.prism import verify_batch, verify_entity

    _PRISM_AVAILABLE = True
except ImportError as exc:
    log.warning("prism unavailable: %s", exc)
    _PRISM_AVAILABLE = False

_SYSTEM_PROMPT = (
    "You are Jeles, a trusted librarian. Answer using ONLY the numbered source "
    "excerpts below. Cite each fact with [N]. For lists, enumerate ALL items found. "
    "2-6 sentences or a bulleted list. "
    "NEVER use outside knowledge — if excerpts lack the answer, say exactly: "
    "'The trusted sources do not contain this answer.'"
)


def _verify_candidate(hit: Optional[dict[str, Any]], query: str = "") -> dict[str, Any]:
    """Build the entity payload used by CLI/TUI verification."""
    title = ""
    if hit:
        title = str(hit.get("title") or "").strip()
    name = title or (query or "").strip()
    return {"id": 0, "name": name, "type": "", "description": "", "mentions": 1}


def _verify_result_message(result: Any) -> tuple[str, str]:
    """Return (message, severity) for Textual notifications."""
    if getattr(result, "skipped", False):
        reason = getattr(result, "skip_reason", "") or "not verifiable"
        return f"Verify skipped: {getattr(result, 'name', '')} ({reason})", "warning"
    if getattr(result, "verified", False):
        sources = getattr(result, "sources", []) or []
        source = (sources[0].get("title") or sources[0].get("url")) if sources else "public source"
        return (
            f"Verified {getattr(result, 'name', '')}: {getattr(result, 'confidence', 'low')} via {source}",
            "information",
        )
    return f"Could not verify {getattr(result, 'name', '')} from trusted public sources.", "warning"

_DEMO_QUERY = "Vespa scooters"
_DEMO_PAYLOAD: dict[str, Any] = {
    "query": _DEMO_QUERY,
    "intent": "classic Italian scooter design urban mobility",
    "total": 5,
    "query_class": "general",
    "backend": "demo",
    "sources_used": ["local_kb", "open_web", "stacks"],
    "error": "",
    "hits": [
        {
            "n": 1,
            "title": "Vespa scooters: Italian design and city mobility",
            "url": "https://example.invalid/jeles-demo/vespa-design",
            "hostname": "demo.local",
            "source": "demo_topic_brief",
            "snippet": (
                "Vespa is a scooter line created by Piaggio in postwar Italy. Its step-through "
                "frame, enclosed engine, and pressed-steel body helped make it practical for city "
                "transport while giving it a recognizable visual identity."
            ),
        },
        {
            "n": 2,
            "title": "Why the Vespa became an urban icon",
            "url": "https://example.invalid/jeles-demo/vespa-urban-icon",
            "hostname": "demo.local",
            "source": "demo_topic_brief",
            "snippet": (
                "The Vespa's small footprint, easy mounting position, and weather-shielding bodywork "
                "made it useful in dense streets. Its styling also turned practical transport into a "
                "symbol of modern Italian life."
            ),
        },
        {
            "n": 3,
            "title": "Scooter versus motorcycle design",
            "url": "https://example.invalid/jeles-demo/scooter-vs-motorcycle",
            "hostname": "demo.local",
            "source": "demo_topic_brief",
            "snippet": (
                "Classic scooters usually emphasize a step-through frame, smaller wheels, upright "
                "posture, and body panels that cover mechanical parts. Motorcycles more often expose "
                "the engine and use a straddled frame layout."
            ),
        },
        {
            "n": 4,
            "title": "Piaggio and postwar mobility",
            "url": "https://example.invalid/jeles-demo/piaggio-postwar",
            "hostname": "demo.local",
            "source": "demo_topic_brief",
            "snippet": (
                "Piaggio adapted industrial production toward affordable personal mobility after "
                "World War II. The Vespa answered a need for economical transport that was easier "
                "to use than many motorcycles."
            ),
        },
        {
            "n": 5,
            "title": "Vespa as culture, not just transport",
            "url": "https://example.invalid/jeles-demo/vespa-culture",
            "hostname": "demo.local",
            "source": "demo_topic_brief",
            "snippet": (
                "Vespa's cultural meaning comes from the blend of utility, style, cinema, tourism, "
                "and youth mobility. It is often remembered as much for its silhouette and lifestyle "
                "associations as for its mechanics."
            ),
        },
    ],
}
_DEMO_ANSWER = (
    "Vespa scooters are best understood as compact step-through motor scooters shaped by postwar "
    "Italian urban needs. Their enclosed engine, pressed-steel body, upright riding posture, and "
    "small footprint made them practical city transport, while Piaggio's design language turned "
    "that practicality into an icon of Italian modernity."
)


def _synthesize(question: str, hits: list[dict[str, Any]]) -> str:
    if not hits and not question.strip():
        return "Nothing in the stacks matched that query."
    try:
        payload = synthesize_answer(question)
        return payload.get("answer") or "(no answer returned)"
    except Exception as exc:
        log.exception("synthesis failed")
        if not hits:
            return f"(synthesis unavailable: {exc})"
    if not _LLM_AVAILABLE:
        return "(LLM unavailable — pick a result and press Enter to open it.)"
    try:
        return llm_respond(
            _SYSTEM_PROMPT,
            [],
            f"Question: {question}\n\nSources:\n{snippet_block(hits)}",
        )
    except Exception as exc:
        log.exception("synthesis fallback failed")
        return f"(synthesis unavailable: {exc})"


def _build_tui(*, demo: bool = False):
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.reactive import reactive
    from textual.widgets import (
        Footer,
        Header,
        Input,
        Label,
        ListItem,
        ListView,
        LoadingIndicator,
        Static,
    )
    from textual import work

    def _hit_label(hit: dict[str, Any]):
        from rich.style import Style
        from rich.text import Text

        t = Text()
        t.append(f"{hit.get('n', '?')}. ", style="bold cyan")
        t.append((hit.get("title") or "Untitled")[:140])
        t.append("\n")
        t.append(hit.get("hostname") or hit.get("source") or "source", style="dim")
        url = hit.get("url") or ""
        if url:
            t.append("\n")
            # Rich link style — safe for https:// URLs (no markup parsing)
            t.append(url[:160], style=Style(dim=True, underline=True, link=url))
        return t

    class HitItem(ListItem):
        DEFAULT_CSS = """
        HitItem { padding: 0 1; min-height: 3; }
        HitItem.-highlight { background: $accent 20%; }
        """

        def __init__(self, hit: dict[str, Any]):
            self.hit = hit
            super().__init__(Label(_hit_label(hit)))

    class JelesTUI(App):
        TITLE = "Jeles"
        SUB_TITLE = "Enter/o open · a synthesize · Ctrl+T quiz · m MCP"
        CSS = """
        Screen { background: $surface; }
        #search-bar { height: 3; padding: 0 1; }
        #meta-row { height: 1; padding: 0 1; }
        #hits-list { height: 1fr; margin: 0 1; border: solid $primary-darken-2; }
        #preview { height: auto; max-height: 8; margin: 0 1; padding: 0 1;
                    border: solid $primary-darken-3; color: $text-muted; }
        #answer { height: auto; max-height: 10; margin: 0 1 1 1; padding: 0 1;
                  border: solid $success-darken-2; }
        #loading { display: none; height: 1; }
        #loading.visible { display: block; }
        Input { border: tall $primary; }
        """

        BINDINGS = [
            Binding("ctrl+q", "quit", "Quit"),
            Binding("ctrl+n", "clear", "New search"),
            Binding("enter", "open_hit", "Open", show=False),
            Binding("o", "open_hit", "Open"),
            Binding("a", "synthesize", "Synthesize"),
            Binding("v", "verify", "Verify"),
            Binding("ctrl+s", "save", "Save"),
            Binding("ctrl+v", "verify", "Verify", show=False),
            Binding("ctrl+t", "trivia", "Trivia"),
            Binding("ctrl+l", "learning_toggle", "Learning"),
            Binding("m", "mcp_drawer", "MCP"),
            Binding("escape", "clear", "Clear", show=False),
        ]

        _hits: list[dict[str, Any]] = []
        _last_query: str = ""
        _last_answer: str = ""
        _last_hero_payload: dict[str, Any] = {}
        _loading = reactive(False)
        _learning_enabled: bool = False
        _learning_granted_at: Optional[float] = None

        def compose(self) -> ComposeResult:
            from askjeles.hero_scene import HeroScene

            yield Header()
            yield HeroScene(id="hero-scene")
            with Horizontal(id="meta-row"):
                yield Label("stacks: ", id="meta-label")
                yield Static("—", id="meta-badge")
            with Horizontal(id="search-bar"):
                yield Input(placeholder="Search your KB, the open web, maps, and Special Collections…", id="query-input")
            yield LoadingIndicator(id="loading")
            yield ListView(id="hits-list")
            yield Static(
                "[bold]Enter/o[/bold] open  [bold]a[/bold] synthesize  [bold]v[/bold] verify  [bold]Ctrl+T[/bold] topic quiz  "
                "[bold]m[/bold] MCP drawer  [bold]Ctrl+L[/bold] learning  [dim]Ctrl+S save · Ctrl+N new[/dim]",
                id="preview",
                markup=True,
            )
            yield Static("", id="answer", markup=True)
            yield Footer()

        def _hero(self):
            from askjeles.hero_scene import HeroScene

            return self.query_one("#hero-scene", HeroScene)

        def on_mount(self) -> None:
            badge = self.query_one("#meta-badge", Static)
            online = search_available()
            badge.update("ready" if online else "offline")
            self._hero().set_idle(online=online)
            self.query_one("#query-input", Input).focus()
            if demo:
                self._load_demo()

        def _load_demo(self) -> None:
            inp = self.query_one("#query-input", Input)
            inp.value = _DEMO_QUERY
            self._show_hits(dict(_DEMO_PAYLOAD))
            self.query_one("#meta-badge", Static).update("demo · offline topic deck")
            self.notify(
                "Demo loaded: try a synthesize, Ctrl+T topic quiz, Ctrl+L learning, or m MCP.",
                timeout=6,
            )

        def on_input_changed(self, event: Input.Changed) -> None:
            q = event.value.strip()
            if q:
                self._hero().set_query_preview(q)
            elif not self._hits:
                self._hero().set_idle(online=search_available())

        def on_input_submitted(self, event: Input.Submitted) -> None:
            q = event.value.strip()
            if q:
                self._run_search(q)

        @work(exclusive=True, thread=True)
        def _run_search(self, question: str) -> None:
            self.call_from_thread(self._set_loading, True)
            payload = search_stacks(question, limit_per_source=5)
            self.call_from_thread(self._show_hits, payload)
            self.call_from_thread(self._set_loading, False)

        @work(exclusive=True, thread=True)
        def _run_synthesize(self) -> None:
            if not self._hits:
                self.notify("Search first.", severity="warning")
                return
            self.call_from_thread(self._set_loading, True)
            question = self.query_one("#query-input", Input).value.strip() or self._last_query
            answer = _synthesize(question, self._hits)
            self.call_from_thread(self._show_answer, answer)
            self.call_from_thread(self._set_loading, False)

        def _set_loading(self, state: bool) -> None:
            loader = self.query_one("#loading", LoadingIndicator)
            loader.set_class(state, "visible")
            if state:
                q = self.query_one("#query-input", Input).value.strip()
                if q:
                    self._hero().set_searching(q)
            else:
                self._hero().stop_search_spin()

        def _show_hits(self, payload: dict[str, Any]) -> None:
            self._last_hero_payload = dict(payload)
            self._hero().set_results(payload)
            self._hits = payload.get("hits") or []
            self._last_query = payload.get("query") or ""
            self._last_answer = ""
            self.query_one("#answer", Static).update("")

            if self._learning_enabled and self._learning_granted_at and self._last_query:
                try:
                    from datetime import datetime, timezone

                    from askjeles.learning_events import build_event, record_event

                    sources_used = payload.get("sources_used") or []
                    backend = payload.get("backend") or ""
                    qclass = payload.get("query_class") or ""
                    total = payload.get("total", len(self._hits))
                    top_sources: list[str] = []
                    for h in self._hits[:8]:
                        s = (h.get("source") or h.get("hostname") or "").strip()
                        if s and s not in top_sources:
                            top_sources.append(s)

                    event = build_event(
                        event_type="search",
                        query=self._last_query,
                        consent_granted_at=datetime.fromtimestamp(
                            self._learning_granted_at, tz=timezone.utc
                        ),
                        query_class=qclass,
                        sources_used=list(sources_used),
                        backend=backend,
                        result_summary={
                            "hit_count": int(total),
                            "top_sources": top_sources[:5],
                        },
                        pedagogy={
                            "signals": ["curiosity", "source_selection"],
                            "followup_affordances": ["quiz", "synthesis", "citation_review"],
                        },
                    )
                    record_event(event)
                except Exception as exc:
                    log.debug("learning event (search) failed: %s", exc)

            err = payload.get("error") or ""
            sources = payload.get("sources_used") or []
            total = payload.get("total", len(self._hits))
            badge = self.query_one("#meta-badge", Static)
            if err:
                badge.update(f"error — {err[:60]}")
            elif payload.get("corrected_question"):
                badge.update(
                    f"{total} hits · {payload.get('query_class', '—')} · corrected: {payload['corrected_question']}"
                )
            else:
                qclass = payload.get("query_class") or "—"
                backend = payload.get("backend") or "—"
                badge.update(f"{total} hits · {qclass} · {backend}")

            lv = self.query_one("#hits-list", ListView)
            lv.clear()
            for hit in self._hits:
                try:
                    lv.append(HitItem(hit))
                except Exception as exc:
                    log.warning("skip hit render: %s", exc)

            preview = self.query_one("#preview", Static)
            if not self._hits:
                preview.update(err or "No results. Try different terms — Jeles keeps misfiled things, not lost ones.")
                return

            if not lv.children:
                preview.update("Results found but could not render the list. Check jeles.log.")
                return

            lv.focus()
            lv.index = 0
            self._show_preview(self._hits[0])

        def _show_preview(self, hit: dict[str, Any]) -> None:
            from rich.markup import escape

            snippet = escape((hit.get("snippet") or "(no preview)")[:500])
            host = escape(hit.get("hostname") or "")
            preview = self.query_one("#preview", Static)
            preview.update(f"[dim]{host}[/dim]\n{snippet}\n[dim]Enter · o[/dim] open  [dim]a[/dim] synthesize  [dim]v[/dim] verify")

        def _show_answer(self, answer: str) -> None:
            from rich.text import Text

            self._last_answer = answer
            pane = self.query_one("#answer", Static)
            body = Text()
            body.append("Jeles: ", style="bold")
            body.append(answer)
            pane.update(body)

            if (
                self._learning_enabled
                and self._learning_granted_at
                and (self._last_query or "").strip()
                and (answer or "").strip()
            ):
                try:
                    from datetime import datetime, timezone

                    from askjeles.learning_events import build_event, record_event

                    event = build_event(
                        event_type="synthesis",
                        query=self._last_query,
                        consent_granted_at=datetime.fromtimestamp(
                            self._learning_granted_at, tz=timezone.utc
                        ),
                        result_summary={
                            "citation_count": int(len(self._hits)),
                            "answer_chars": int(len(answer)),
                        },
                        pedagogy={
                            "signals": ["explanation_request"],
                            "followup_affordances": ["citation_review", "quiz"],
                        },
                    )
                    record_event(event)
                except Exception as exc:
                    log.debug("learning event (synthesis) failed: %s", exc)

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            item = event.item
            if isinstance(item, HitItem):
                self._show_preview(item.hit)

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            item = event.item
            if isinstance(item, HitItem):
                self.action_open_hit()

        def _selected_hit(self) -> Optional[dict[str, Any]]:
            lv = self.query_one("#hits-list", ListView)
            item = lv.highlighted_child
            if isinstance(item, HitItem):
                return item.hit
            if self._hits:
                return self._hits[0]
            return None

        def action_open_hit(self) -> None:
            hit = self._selected_hit()
            if not hit:
                self.notify("No result selected.", severity="warning")
                return
            url = hit.get("url") or ""
            if not url:
                self.notify("This hit has no URL.", severity="warning")
                return
            if open_url(url):
                self.notify(f"Opened {hit.get('hostname') or 'link'}", timeout=2)
            else:
                self.notify(f"Could not open browser. Copy URL:\n{url}", severity="error", timeout=6)

        def action_synthesize(self) -> None:
            if not self._hits:
                self.notify("Search first.", severity="warning")
                return
            if demo and (self._last_query or "").strip().lower() == _DEMO_QUERY.lower():
                self._show_answer(_DEMO_ANSWER)
                return
            self._run_synthesize()

        def action_clear(self) -> None:
            self._hero().set_idle(online=search_available())
            self.query_one("#query-input", Input).value = ""
            self.query_one("#hits-list", ListView).clear()
            self.query_one("#preview", Static).update(
                "[bold]Enter/o[/bold] open  [bold]a[/bold] synthesize  [bold]v[/bold] verify  [bold]Ctrl+T[/bold] topic quiz  "
                "[bold]m[/bold] MCP drawer  [bold]Ctrl+L[/bold] learning  [dim]Ctrl+S save · Ctrl+N new[/dim]"
            )
            self.query_one("#answer", Static).update("")
            self.query_one("#meta-badge", Static).update("ready" if search_available() else "offline")
            self._hits = []
            self._last_query = ""
            self._last_answer = ""
            self.query_one("#query-input", Input).focus()

        def action_learning_toggle(self) -> None:
            """Toggle session-only learning event capture."""
            self._learning_enabled = not self._learning_enabled
            if self._learning_enabled:
                self._learning_granted_at = time.time()
                self.notify(
                    "Learning capture ON for this session. Jeles stores small JSON summaries only; no snippets/full answers. Resets on app close.",
                    severity="information",
                    timeout=6,
                )
            else:
                self.notify(
                    "Learning capture OFF for this session.",
                    severity="information",
                    timeout=4,
                )

        def action_save(self) -> None:
            if not self._hits and not self._last_answer:
                self.notify("Nothing to save.", severity="warning")
                return
            query = self.query_one("#query-input", Input).value.strip() or self._last_query
            lines = [f"# Jeles: {query}\n\n"]
            if self._last_answer:
                lines.append(f"{self._last_answer}\n\n")
            lines.append("## Sources\n")
            for hit in self._hits:
                lines.append(f"- [{hit['title']}]({hit['url']}) — {hit['source']}\n")
            body = "".join(lines)
            save_path = Path.home() / ".willow" / "jeles_saves" / f"jeles_{time.strftime('%Y%m%d_%H%M%S')}.md"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(body)
            binder_note = save_path.name
            try:
                from safe_integration import contribute

                staged = contribute(
                    body,
                    category="jeles_save",
                    metadata={"query": query, "dest_path": str(save_path), "citation_count": len(self._hits)},
                )
                if staged.get("ok"):
                    binder_note = f"{save_path.name} → intake staged"
            except Exception as exc:
                log.debug("binder intake staging failed: %s", exc)
            self.notify(f"Saved → {binder_note}", severity="information")

        def action_verify(self) -> None:
            if not _PRISM_AVAILABLE:
                self.notify("prism not available", severity="warning")
                return
            hit = self._selected_hit()
            query = self.query_one("#query-input", Input).value.strip() or self._last_query
            candidate = _verify_candidate(hit, query)
            if not candidate["name"]:
                self.notify("Search or type an entity to verify.", severity="warning")
                return
            self._run_verify(candidate)

        @work(exclusive=True, thread=True)
        def _run_verify(self, candidate: dict[str, Any]) -> None:
            self.call_from_thread(self._set_loading, True)
            try:
                result = verify_entity(candidate)
                message, severity = _verify_result_message(result)
            except Exception as exc:
                message = f"Verify failed: {exc}"
                severity = "error"
            self.call_from_thread(self._set_loading, False)
            self.call_from_thread(self.notify, message, severity=severity, timeout=8)

        def action_mcp_drawer(self) -> None:
            from askjeles.overlays import McpDrawerModal

            query = self.query_one("#query-input", Input).value.strip() or self._last_query
            self.push_screen(McpDrawerModal(query))

        def action_trivia(self) -> None:
            if not self._hits:
                self.notify(
                    "Search first — Ctrl+T builds a subject-matter quiz behind the search results.",
                    severity="warning",
                )
                return
            from askjeles.overlays import TriviaModal

            self._hero().set_trivia_pending()
            query = self.query_one("#query-input", Input).value.strip() or self._last_query
            self.push_screen(
                TriviaModal(query, list(self._hits), synthesis=self._last_answer),
                callback=self._on_trivia_dismiss,
            )

        def _on_trivia_dismiss(self, result: Optional[dict[str, Any]]) -> None:
            if not result:
                return
            if not (self._learning_enabled and self._learning_granted_at):
                return
            try:
                from datetime import datetime, timezone

                from askjeles.learning_events import build_event, record_event

                total = int(result.get("total") or 0)
                score = int(result.get("score") or 0)
                answered = int(result.get("answered") or 0)
                max_score = total * 10 if total else 0
                pct = (score / max_score * 100) if max_score else 0.0

                event = build_event(
                    event_type="trivia",
                    query=str(result.get("query") or self._last_query),
                    consent_granted_at=datetime.fromtimestamp(
                        self._learning_granted_at, tz=timezone.utc
                    ),
                    result_summary={
                        "score": score,
                        "total": total,
                        "answered": answered,
                        "completed": bool(result.get("completed")),
                        "duration_s": result.get("duration_s"),
                        "accuracy_pct": round(pct, 1),
                    },
                    pedagogy={
                        "signals": ["recall_practice"],
                        "followup_affordances": ["synthesis", "citation_review"],
                    },
                )
                record_event(event)
            except Exception as exc:
                log.debug("learning event (trivia) failed: %s", exc)

        def on_screen_resume(self, event) -> None:
            """Restore hero/search desk after any overlay closes."""
            if self._last_hero_payload:
                self._hero().set_results(self._last_hero_payload)
            elif self._hits:
                self._hero().set_query_preview(self._last_query)

        def action_quit(self) -> None:
            try:
                from askjeles import mcp_generic

                mcp_generic.shutdown_all()
            except Exception:
                pass
            self.exit()

    return JelesTUI


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="AskJeles — Jeles, your AI librarian")
    parser.add_argument("--batch", action="store_true", help="Batch entity verification (headless)")
    parser.add_argument("--verify", metavar="NAME", help="Verify a single entity")
    parser.add_argument("--type", metavar="TYPE", default="", help="Entity type for --verify")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--willow-url", metavar="URL", default=None)
    parser.add_argument("--serve", action="store_true", help="Start FastAPI verification API")
    parser.add_argument("--trivia", action="store_true", help="Run the Sovereign Trivia Engine")
    parser.add_argument("--demo", action="store_true", help="Launch an offline seeded demo deck")
    args = parser.parse_args()

    if args.willow_url:
        os.environ["WILLOW_URL"] = args.willow_url

    if args.trivia:
        _trivia.main()
        return

    if args.serve:
        from askjeles.serve import main as serve_main

        serve_main()
        return

    if args.batch and not _PRISM_AVAILABLE:
        print("prism verifier is not available in this install", flush=True)
        raise SystemExit(1)

    if args.verify and not _PRISM_AVAILABLE:
        print("prism verifier is not available in this install", flush=True)
        raise SystemExit(1)

    if args.batch and _PRISM_AVAILABLE:
        summary = verify_batch(willow_url=args.willow_url, limit=args.limit, dry_run=args.dry_run)
        print(summary)
        return

    if args.verify and _PRISM_AVAILABLE:
        result = verify_entity(
            {"id": 0, "name": args.verify, "type": args.type, "description": "", "mentions": 0}
        )
        print(dataclasses.asdict(result))
        return

    log.info("launching TUI (log: %s, willow: %s)", _LOG_PATH, _willow_root)
    try:
        JelesTUI = _build_tui(demo=args.demo)
    except ImportError as exc:
        print(
            "Textual not found in this Python. Use ./dev.sh or "
            "github/willow-2.0/.venv-dev/bin/python3 -m askjeles.crown",
            flush=True,
        )
        raise SystemExit(1) from exc

    JelesTUI().run()


if __name__ == "__main__":
    main()
