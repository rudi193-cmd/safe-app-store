"""Textual TUI for semantic-translator."""
from __future__ import annotations

import json
import pathlib

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog


class TranslatorApp(App):
    TITLE = "Semantic Translator — Emerging Rule"
    CSS = """
    Screen {
        background: $surface;
    }
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
    #lesson-list {
        height: 1fr;
    }
    #main {
        width: 1fr;
        padding: 0 1;
    }
    #query-input {
        margin: 1 0;
    }
    #results {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    #status {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_results", "Clear"),
        Binding("escape", "blur_input", "Blur"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Lessons", id="sidebar-title")
                yield ListView(id="lesson-list")
            with Vertical(id="main"):
                yield Input(
                    placeholder="Enter text to find semantic matches... (Enter to search)",
                    id="query-input",
                )
                yield RichLog(id="results", highlight=True, markup=True)
        yield Label("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._load_corpus_list()

    def _corpus_path(self) -> pathlib.Path:
        return pathlib.Path("data/corpus.jsonl")

    def _load_corpus_list(self) -> None:
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
            lv.append(ListItem(Label(lesson)))

        status.update(f"{count} segments · {len(lessons)} lessons · ready")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
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

            results = await self.run_worker(
                lambda: search(query, limit=6), thread=True
            )

            if not results:
                results_log.write("[yellow]No matches found.[/yellow]")
                status.update("No results")
                return

            for i, r in enumerate(results, 1):
                score = r.get("score", r.get("certainty", r.get("similarity", "?")))
                title = r.get("title", "")
                content = r.get("content", r.get("text", str(r)))

                # Detect language from title for colour coding
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
        lesson = str(event.item.query_one(Label).renderable)
        results_log = self.query_one("#results", RichLog)
        results_log.clear()
        results_log.write(f"[bold]Lesson:[/bold] {lesson}\n")

        corpus = self._corpus_path()
        if not corpus.exists():
            return

        with open(corpus, encoding="utf-8") as f:
            for line in f:
                seg = json.loads(line)
                if seg["lesson"] != lesson:
                    continue
                lang_color = "green" if seg["lang"] == "en" else "yellow"
                results_log.write(
                    f"[bold {lang_color}][{seg['lang'].upper()}][/bold {lang_color}]  "
                    f"{seg['text'][:300]}\n"
                )

    def action_clear_results(self) -> None:
        self.query_one("#results", RichLog).clear()

    def action_blur_input(self) -> None:
        self.query_one("#query-input", Input).blur()
