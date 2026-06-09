"""Textual TUI — Search + Review tabs."""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import traceback

_log_path = pathlib.Path("data/tui.log")
_log_path.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_log_path),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)
_log = logging.getLogger("semantic_translator.tui")

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)


# ── Search tab ──────────────────────────────────────────────────────────────

SEARCH_CSS = """
#sidebar {
    width: 32;
    border-right: solid $primary-darken-2;
    padding: 0 1;
}
#sidebar-title {
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}
#lesson-list { height: 1fr; }
#main { width: 1fr; padding: 0 1; }
#query-input { margin: 1 0; }
#results {
    height: 1fr;
    border: solid $primary-darken-2;
    padding: 0 1;
}
"""

REVIEW_CSS = """
#review-container { padding: 1 2; }
#review-header {
    height: 3;
    color: $text-muted;
    padding: 0 0 1 0;
}
#segments-panel {
    height: 1fr;
    border: solid $primary-darken-2;
    padding: 1 2;
}
#source-box {
    width: 1fr;
    border: solid $success-darken-2;
    padding: 1;
    margin-right: 1;
}
#candidate-box {
    width: 1fr;
    border: solid $warning-darken-2;
    padding: 1;
}
#source-label  { color: $success; text-style: bold; }
#candidate-label { color: $warning; text-style: bold; }
#source-text   { margin-top: 1; }
#candidate-text { margin-top: 1; }
#score-bar { height: 1; color: $text-muted; margin-top: 1; }
#action-row {
    height: 5;
    padding: 1 0;
    align: center middle;
}
#btn-approve { margin: 0 1; }
#btn-correct { margin: 0 1; }
#btn-reject  { margin: 0 1; }
#correction-input { margin: 1 0; display: none; }
#correction-input.visible { display: block; }
#review-status { height: 1; color: $text-muted; padding: 0 1; }
#learner-row { height: 3; padding: 0 0 1 0; }
#learner-select { width: 40; }
"""

LEARN_CSS = """
#learn-container { padding: 1 2; height: 1fr; }
#learn-stats { height: 3; color: $text-muted; padding: 0 0 1 0; }
#flashcard {
    height: 1fr;
    border: solid $primary-darken-2;
    padding: 2 3;
}
#card-front-label { color: $accent; text-style: bold; margin-bottom: 1; }
#card-front-text  { margin-bottom: 2; }
#card-back-label  { color: $success; text-style: bold; margin-bottom: 1; }
#card-hint        { color: $text-muted; margin-top: 2; }
#rating-row       { height: 5; padding: 1 0; align: center middle; display: none; }
#rating-row.visible { display: block; }
#btn-again { margin: 0 1; }
#btn-hard  { margin: 0 1; }
#btn-good  { margin: 0 1; }
#btn-easy  { margin: 0 1; }
#learn-status { height: 1; color: $text-muted; padding: 0 1; }
"""


class TranslatorApp(App):
    TITLE = "Semantic Translator — Emerging Rule"
    CSS = SEARCH_CSS + REVIEW_CSS + LEARN_CSS
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_results", "Clear"),
        Binding("escape", "blur_input", "Blur"),
        Binding("1", "show_search", "Search"),
        Binding("2", "show_review", "Review"),
        Binding("3", "show_learn",  "Learn"),
        Binding("space", "flip_card", "Flip"),
    ]

    # Review state
    _queue: list[dict] = []
    _queue_pos: int = 0
    _current_learner_id: str = ""

    # Learn state
    _study_queue: list[dict] = []
    _study_pos: int = 0
    _card_flipped: bool = False

    # ── compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Search [1]", id="tab-search"):
                with Horizontal():
                    with Vertical(id="sidebar"):
                        yield Label("Lessons", id="sidebar-title")
                        yield ListView(id="lesson-list")
                    with Vertical(id="main"):
                        yield Input(
                            placeholder="Enter text to find semantic matches… (Enter)",
                            id="query-input",
                        )
                        yield RichLog(id="results", highlight=True, markup=True)
                yield Label("", id="status")
            with TabPane("Review [2]", id="tab-review"):
                with Vertical(id="review-container"):
                    with Horizontal(id="learner-row"):
                        yield Label("Reviewer: ", classes="")
                        yield Select([], id="learner-select", prompt="Select learner…")
                    yield Label("", id="review-header")
                    with Horizontal(id="segments-panel"):
                        with Vertical(id="source-box"):
                            yield Label("SOURCE", id="source-label")
                            yield Static("", id="source-text")
                        with Vertical(id="candidate-box"):
                            yield Label("CANDIDATE", id="candidate-label")
                            yield Static("", id="candidate-text")
                            yield Static("", id="score-bar")
                    with Horizontal(id="action-row"):
                        yield Button("Approve  A", id="btn-approve", variant="success")
                        yield Button("Correct  C", id="btn-correct", variant="warning")
                        yield Button("Reject   R", id="btn-reject",  variant="error")
                    yield Input(placeholder="Type correction and press Enter…",
                                id="correction-input")
                    yield Label("", id="review-status")
            with TabPane("Learn [3]", id="tab-learn"):
                with Vertical(id="learn-container"):
                    yield Label("", id="learn-stats")
                    with Vertical(id="flashcard"):
                        yield Label("FRONT", id="card-front-label")
                        yield Static("", id="card-front-text")
                        yield Label("", id="card-back-label")
                        yield Static("", id="card-back-text")
                        yield Static("", id="card-hint")
                    with Horizontal(id="rating-row"):
                        yield Button("Again  1", id="btn-again", variant="error")
                        yield Button("Hard   2", id="btn-hard",  variant="warning")
                        yield Button("Good   3", id="btn-good",  variant="success")
                        yield Button("Easy   4", id="btn-easy",  variant="primary")
                    yield Label("", id="learn-status")
        yield Footer()

    # ── mount ───────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._load_corpus_list()
        self._load_learners()
        self._load_queue()
        self._load_study_queue()

    def _corpus_path(self) -> pathlib.Path:
        return pathlib.Path("data/corpus.jsonl")

    def _load_corpus_list(self) -> None:
        try:
            corpus = self._corpus_path()
            lv = self.query_one("#lesson-list", ListView)
            status = self.query_one("#status", Label)
            if not corpus.exists():
                status.update("No corpus — run: semantic-translator scrape")
                return
            lessons: set[str] = set()
            count = 0
            with open(corpus, encoding="utf-8") as f:
                for line in f:
                    seg = json.loads(line)
                    lessons.add(seg["lesson"])
                    count += 1
            for lesson in sorted(lessons):
                lv.append(ListItem(Label(lesson), name=lesson))
            # show ingest progress if log exists
            ingest_log = pathlib.Path("data/ingest_log.jsonl")
            if ingest_log.exists():
                ingested = sum(1 for _ in ingest_log.open())
                passed = 0
                for line in ingest_log.open():
                    try:
                        e = json.loads(line)
                        if not e.get("blocked") and not e.get("error"):
                            passed += 1
                    except Exception:
                        pass
                pct = ingested / count * 100 if count else 0
                status.update(
                    f"{count} segments · {len(lessons)} lessons  ·  "
                    f"ingest {ingested}/{count} ({pct:.0f}%)  {passed} atoms in Jeles"
                )
            else:
                status.update(f"{count} segments · {len(lessons)} lessons · ready")
        except Exception as exc:
            _log.error("_load_corpus_list: %s\n%s", exc, traceback.format_exc())

    def _load_learners(self) -> None:
        try:
            from . import db
            db.init_db()
            learners = db.list_learners()
            sel = self.query_one("#learner-select", Select)
            options = [(l["name"], l["id"]) for l in learners]
            sel.set_options(options)
            if learners:
                self._current_learner_id = learners[0]["id"]
                sel.value = learners[0]["id"]
        except Exception as exc:
            _log.error("_load_learners: %s\n%s", exc, traceback.format_exc())

    def _load_queue(self) -> None:
        try:
            from .review import get_queue
            self._queue = get_queue(limit=50)
            self._queue_pos = 0
            self._show_current_segment()
        except Exception as exc:
            _log.error("_load_queue: %s\n%s", exc, traceback.format_exc())

    def _show_current_segment(self) -> None:
        header = self.query_one("#review-header", Label)
        source = self.query_one("#source-text", Static)
        candidate = self.query_one("#candidate-text", Static)
        score_bar = self.query_one("#score-bar", Static)
        rev_status = self.query_one("#review-status", Label)

        if not self._queue:
            header.update("[bold]Review queue is empty[/bold]")
            source.update(
                "No documents queued for review.\n\n"
                "To add content:\n"
                "  1. Write a .txt file with the text to translate\n"
                "  2. Run:  semantic-translator translate <file.txt>\n"
                "  3. Come back here — segments will appear for approval\n\n"
                "The ingest is still building the Jeles corpus in the background.\n"
                "Once it has more atoms, translation candidates will improve."
            )
            candidate.update("")
            score_bar.update("")
            rev_status.update("[dim]Ingest running — check: tail -f data/ingest_log.jsonl[/dim]")
            return

        pos = self._queue_pos
        seg = self._queue[pos]
        total = len(self._queue)
        score = seg.get("jeles_score") or 0.0
        filled = int(score * 10)
        bar = "█" * filled + "░" * (10 - filled)

        header.update(
            f"[bold]{seg.get('doc_title', '')}[/bold]  "
            f"segment {pos + 1}/{total}  "
            f"[dim]id: {seg['id'][:8]}[/dim]"
        )
        source.update(seg.get("source_text", ""))
        candidate.update(seg.get("candidate", "[dim]no candidate[/dim]"))
        score_bar.update(f"confidence [{bar}] {score:.2f}")
        rev_status.update(
            f"{total - pos - 1} remaining  ·  "
            f"{'[yellow]needs native[/yellow]' if score < 0.5 else '[green]learner ok[/green]'}"
        )

    # ── search tab events ────────────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "correction-input":
            await self._submit_correction(event.value.strip())
            return

        if event.input.id != "query-input":
            return

        query = event.value.strip()
        if not query:
            return

        results_log = self.query_one("#results", RichLog)
        status = self.query_one("#status", Label)
        results_log.clear()
        results_log.write(f"[bold]Query:[/bold] {query}\n")
        status.update("Searching…")

        try:
            from .search import search
            results = await asyncio.to_thread(search, query, 6)
            if not results:
                results_log.write("[yellow]No matches found.[/yellow]")
                status.update("No results")
                return
            for i, r in enumerate(results, 1):
                score = r.get("score", r.get("certainty", r.get("similarity", "?")))
                title = r.get("title", "")
                content = r.get("content", r.get("text", str(r)))
                lang_hint = "es" if "| es" in title.lower() else "en"
                lang_color = "green" if lang_hint == "en" else "yellow"
                results_log.write(
                    f"\n[bold cyan][{i}][/bold cyan] "
                    f"[bold {lang_color}]{title}[/bold {lang_color}]  "
                    f"[dim]score={score}[/dim]"
                )
                results_log.write(content[:500])
            status.update(f"{len(results)} matches for: {query}")
        except Exception as exc:
            results_log.write(f"[red bold]Error:[/red bold] {exc}")
            status.update(f"Error: {exc}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        try:
            lesson = event.item.name or ""
            if not lesson:
                return
            results_log = self.query_one("#results", RichLog)
            results_log.clear()
            corpus = self._corpus_path()
            if not corpus.exists():
                return
            segs = []
            with open(corpus, encoding="utf-8") as f:
                for line in f:
                    seg = json.loads(line)
                    if seg["lesson"] == lesson:
                        segs.append(seg)
            results_log.write(
                f"[bold]{lesson}[/bold]  [dim]{len(segs)} segments[/dim]\n"
            )
            for i, seg in enumerate(segs, 1):
                lang_color = "green" if seg["lang"] == "en" else "yellow"
                grade = seg.get("grade", "")
                grade_str = f"  grade {grade}" if grade else ""
                results_log.write(
                    f"\n[dim]──── {i}/{len(segs)}{grade_str} ────[/dim]\n"
                    f"[bold {lang_color}]{seg['lang'].upper()}[/bold {lang_color}]  "
                    f"{seg['text'][:400]}"
                )
        except Exception as exc:
            _log.error("on_list_view_selected: %s\n%s", exc, traceback.format_exc())
            self.query_one("#status", Label).update(f"[red]Error: {exc}[/red]")

    # ── review tab events ────────────────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "learner-select" and event.value:
            self._current_learner_id = str(event.value)
            self._load_study_queue()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        # Learn tab ratings
        if btn_id == "btn-again":
            await self._submit_rating(1)
            return
        if btn_id == "btn-hard":
            await self._submit_rating(2)
            return
        if btn_id == "btn-good":
            await self._submit_rating(3)
            return
        if btn_id == "btn-easy":
            await self._submit_rating(4)
            return
        # Review tab
        if not self._queue or self._queue_pos >= len(self._queue):
            return
        if btn_id == "btn-approve":
            await self._submit_verdict("approved")
        elif btn_id == "btn-correct":
            inp = self.query_one("#correction-input", Input)
            inp.add_class("visible")
            inp.focus()
        elif btn_id == "btn-reject":
            await self._submit_verdict("rejected")

    async def on_key(self, event) -> None:
        tab = self.query_one(TabbedContent)
        if tab.active == "tab-learn":
            if event.key == "1":
                await self._submit_rating(1)
            elif event.key == "2":
                await self._submit_rating(2)
            elif event.key == "3":
                await self._submit_rating(3)
            elif event.key == "4":
                await self._submit_rating(4)
            return
        if event.key == "a":
            await self._try_quick_verdict("approved")
        elif event.key == "r":
            await self._try_quick_verdict("rejected")

    async def _try_quick_verdict(self, verdict: str) -> None:
        tab = self.query_one(TabbedContent)
        if tab.active != "tab-review":
            return
        await self._submit_verdict(verdict)

    async def _submit_correction(self, text: str) -> None:
        if not text:
            return
        inp = self.query_one("#correction-input", Input)
        inp.remove_class("visible")
        inp.value = ""
        await self._submit_verdict("corrected", correction=text)

    async def _submit_verdict(self, verdict: str, correction: str = "") -> None:
        if not self._current_learner_id:
            self.query_one("#review-status", Label).update(
                "[red]Select a learner first[/red]"
            )
            return
        if not self._queue or self._queue_pos >= len(self._queue):
            return

        seg = self._queue[self._queue_pos]
        status = self.query_one("#review-status", Label)
        status.update(f"Submitting {verdict}…")

        try:
            from .review import submit_verification
            await asyncio.to_thread(
                submit_verification, seg["id"], self._current_learner_id, verdict, correction
            )
            self._queue_pos += 1
            if self._queue_pos >= len(self._queue):
                self._load_queue()
            else:
                self._show_current_segment()
        except Exception as exc:
            status.update(f"[red]Error: {exc}[/red]")

    # ── learn tab ────────────────────────────────────────────────────────────

    def _load_study_queue(self) -> None:
        try:
            if not self._current_learner_id:
                return
            from .learn import get_study_queue, seed_cards, study_stats
            seeded = seed_cards(self._current_learner_id)
            self._study_queue = get_study_queue(self._current_learner_id, limit=30)
            self._study_pos = 0
            self._card_flipped = False
            self._show_current_card()
            self._refresh_learn_stats()
        except Exception as exc:
            _log.error("_load_study_queue: %s\n%s", exc, traceback.format_exc())

    def _refresh_learn_stats(self) -> None:
        try:
            if not self._current_learner_id:
                return
            from .learn import study_stats
            stats = study_stats(self._current_learner_id)
            self.query_one("#learn-stats", Label).update(
                f"Due: [bold]{stats['due']}[/bold]  "
                f"New: [bold]{stats['new']}[/bold]  "
                f"Total cards: [bold]{stats['total']}[/bold]  "
                f"Studied today: [bold]{stats['studied_today']}[/bold]"
            )
        except Exception as exc:
            _log.error("_refresh_learn_stats: %s\n%s", exc, traceback.format_exc())

    def _show_current_card(self) -> None:
        front_label  = self.query_one("#card-front-label", Label)
        front_text   = self.query_one("#card-front-text", Static)
        back_label   = self.query_one("#card-back-label", Label)
        back_text    = self.query_one("#card-back-text", Static)
        hint         = self.query_one("#card-hint", Static)
        rating_row   = self.query_one("#rating-row")
        learn_status = self.query_one("#learn-status", Label)

        if not self._study_queue:
            front_label.update("All caught up!")
            front_text.update(
                "No cards due right now.\n\n"
                "Add a learner first:  semantic-translator learner add <name>\n"
                "Then cards seed automatically from the corpus and Jeles atoms."
            )
            back_label.update("")
            back_text.update("")
            hint.update("")
            rating_row.remove_class("visible")
            learn_status.update("")
            return

        if self._study_pos >= len(self._study_queue):
            front_label.update("[bold green]Session complete![/bold green]")
            front_text.update(f"Reviewed {len(self._study_queue)} cards this session.")
            back_label.update("")
            back_text.update("")
            hint.update("")
            rating_row.remove_class("visible")
            learn_status.update("")
            return

        card = self._study_queue[self._study_pos]
        remaining = len(self._study_queue) - self._study_pos
        lang_front = card.get("lang_front", "en").upper()
        lang_back  = card.get("lang_back", "es").upper()
        lesson = card.get("lesson", "")

        front_label.update(f"{lang_front}  [dim]— {lesson}[/dim]")
        front_text.update(card.get("front", "[dim]no content[/dim]"))

        if self._card_flipped:
            back = card.get("back", "")
            back_label.update(f"{lang_back}")
            back_text.update(back if back else "[dim]No translation in corpus yet — this atom needs a verified translation[/dim]")
            hint.update("")
            rating_row.add_class("visible")
        else:
            back_label.update("")
            back_text.update("")
            hint.update("[dim]Think of the translation… then press Space to flip[/dim]")
            rating_row.remove_class("visible")

        source = card.get("source", "")
        source_tag = f"  [{source}]" if source else ""
        learn_status.update(f"Card {self._study_pos + 1}/{len(self._study_queue)}{source_tag}  ·  {remaining - 1} remaining")

    async def _submit_rating(self, rating_int: int) -> None:
        if not self._study_queue or self._study_pos >= len(self._study_queue):
            return
        card = self._study_queue[self._study_pos]
        try:
            from .learn import submit_rating
            await asyncio.to_thread(submit_rating, self._current_learner_id, card["atom_id"], rating_int)
        except Exception as exc:
            _log.error("_submit_rating: %s\n%s", exc, traceback.format_exc())
        self._study_pos += 1
        self._card_flipped = False
        self._show_current_card()
        self._refresh_learn_stats()

    # ── actions ──────────────────────────────────────────────────────────────

    def action_clear_results(self) -> None:
        self.query_one("#results", RichLog).clear()

    def action_blur_input(self) -> None:
        self.query_one("#query-input", Input).blur()

    def action_show_search(self) -> None:
        self.query_one(TabbedContent).active = "tab-search"

    def action_show_review(self) -> None:
        self.query_one(TabbedContent).active = "tab-review"
        self._load_queue()

    def action_show_learn(self) -> None:
        self.query_one(TabbedContent).active = "tab-learn"
        self._load_study_queue()

    def action_flip_card(self) -> None:
        tab = self.query_one(TabbedContent)
        if tab.active != "tab-learn":
            return
        if not self._study_queue or self._study_pos >= len(self._study_queue):
            return
        self._card_flipped = not self._card_flipped
        self._show_current_card()
