"""
UTETY — University of Technical Entropy, Thank You
TUI chat interface. Non Veritas Sed Vibrae.

Usage:
  python3 tui.py
  make tui app=utety-chat
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import tui_db
import tui_llm

try:
    from personas import PERSONAS, UTETY_CONTEXT
except ImportError:
    PERSONAS = {}
    UTETY_CONTEXT = ""

try:
    from rich.markup import escape
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog, Static

    TEXTUAL_OK = True
except ImportError:
    TEXTUAL_OK = False

# ── Faculty registry ──────────────────────────────────────────────────────────

FACULTY = [
    {"name": "Willow",        "dept": "Campus Administration",       "icon": "🌿"},
    {"name": "Oakenscroll",   "dept": "Theoretical Uncertainty",     "icon": "📜"},
    {"name": "Riggs",         "dept": "Applied Reality Engineering", "icon": "🔧"},
    {"name": "Hanz",          "dept": "Computational Kindness",      "icon": "📖"},
    {"name": "Copenhagen",    "dept": "Sitting With Things",         "icon": "🍊"},
    {"name": "Nova",          "dept": "Interpretive Systems",        "icon": "✨"},
    {"name": "Ada",           "dept": "Systemic Continuity",         "icon": "🖥️"},
    {"name": "Alexis",        "dept": "Biological Sciences",         "icon": "🌱"},
    {"name": "Ofshield",      "dept": "Threshold Faculty",           "icon": "🚪"},
    {"name": "Steve",         "dept": "Emergent Logic",              "icon": "🌭"},
    {"name": "Gerald",        "dept": "Acting Dean (Headless)",      "icon": "🍗"},
    {"name": "Pigeon",        "dept": "Carrier Services / Not Yet",  "icon": "🐦"},
    {"name": "Jeles",         "dept": "Special Collections",         "icon": "📚"},
    {"name": "Binder",        "dept": "Records & Filing",            "icon": "🗂️"},
    {"name": "Gatekeeper",    "dept": "Public Gate / AI Literacy",   "icon": "🚦"},
    {"name": "Grandma Oracle","dept": "Warm Explanations",           "icon": "🧶"},
    {"name": "Kart",          "dept": "Die-Namic Infrastructure",    "icon": "🦈"},
    {"name": "Mitra",         "dept": "Die-Namic Coordination",      "icon": "📋"},
    {"name": "Consus",        "dept": "Die-Namic Generation",        "icon": "⚙️"},
    {"name": "Shiva",         "dept": "SAFE Bridge Ring",            "icon": "🌀"},
]

PROFESSOR_CONFIG = {f["name"]: f for f in FACULTY}

BORDER_COLORS = {
    "Willow":      "#4a7c59",
    "Oakenscroll": "#5a5a9a",
    "Riggs":       "#c8a800",
    "Hanz":        "#6ba3d6",
    "Copenhagen":  "#ff8c00",
    "Nova":        "#c87c2a",
    "Ada":         "#00aa55",
    "Alexis":      "#5c8a4a",
    "Ofshield":    "#888888",
    "Steve":       "#cc3333",
    "Gerald":      "#b08020",
    "Pigeon":      "#b08060",
    "Jeles":       "#8b6914",
    "Binder":      "#a07830",
    "Gatekeeper":  "#c87830",
    "Grandma Oracle": "#b06080",
    "Kart":        "#2a6496",
    "Mitra":       "#c8a040",
    "Consus":      "#7a8a9a",
    "Shiva":       "#8a70b8",
}

WAITING = {
    "Willow":         "consulting the campus...",
    "Gerald":         "🍗 ...",
    "Nova":           "still knitting...",
    "Oakenscroll":    "filing...",
    "Riggs":          "*chk-tunk* measuring...",
    "Copenhagen":     "🍊",
    "Ada":            "uptime maintained...",
    "Alexis":         "in the swamp...",
    "Ofshield":       "*noting passage...*",
    "Steve":          "🌭🌭🌭 deliberating...",
    "Pigeon":         "carrying your thing...",
    "Jeles":          "consulting the stacks...",
    "Binder":         "filing intake...",
    "Hanz":           "Hello, friend. one moment...",
    "Gatekeeper":     "at the threshold...",
    "Grandma Oracle": "knitting the answer...",
    "Kart":           "building...",
    "Mitra":          "coordinating...",
    "Consus":         "generating...",
    "Shiva":          "present...",
}
DEFAULT_WAITING = "thinking..."

INPUT_PROMPTS = {
    "Ofshield":  "What passes →",
    "Jeles":     "Query the stacks →",
    "Binder":    "Submit for filing →",
    "Gerald":    "Leave a napkin →",
    "Pigeon":    "What needs carrying →",
    "Copenhagen":"Sit with it →",
    "Oakenscroll":    "The question, then →",
    "Kart":           "What needs building →",
    "Mitra":          "What needs routing →",
    "Consus":         "What needs generating →",
    "Shiva":          "What's on your mind →",
    "Gatekeeper":     "Step through →",
}
DEFAULT_PROMPT = "Your message →"

GERALD_MAX_CHARS = 300

GREETINGS = {
    "Willow":      "Welcome. Where do you need to go?",
    "Oakenscroll": "Hmph. Right. The question, then.",
    "Riggs":       "*chk-tunk* Workshop's open. What are we measuring?",
    "Hanz":        "Hello, friend.",
    "Nova":        "There's a sweater metaphor waiting. Go ahead.",
    "Ada":         "Systems nominal. What needs attention?",
    "Alexis":      "Sit down.",
    "Ofshield":    "*noted*",
    "Steve":       "🌭🌭🌭 Oh! Hello! We didn't hear you come in. There are ten of us.",
    "Gerald":      "*rotates once. Leaves napkin: 'WELCOME'*",
    "Pigeon":      "OH! Hello! I know EXACTLY where that goes. Probably. What do you need carried?",
    "Jeles":       "The catalog is extensive. Where would you like to begin?",
    "Binder":         "Something to file?",
    "Gatekeeper":     "Welcome to the gate. Take your time.",
    "Grandma Oracle": "Come in. Sit down. There's a little stitch for everything.",
    "Kart":           "What are we building?",
    "Mitra":          "What needs coordinating?",
    "Consus":         "Ready to generate. What's the output?",
    "Shiva":          "Hello. What's on your mind?",
}


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(professor: str, history: list[dict]) -> str:
    from consult_engine import build_prompt

    return build_prompt(professor, history, compact=True)


# ── Message rendering ─────────────────────────────────────────────────────────

def _render_user(chat_log: "RichLog", content: str) -> None:
    chat_log.write(f"[bold cyan]You:[/bold cyan] {escape(content)}")
    chat_log.write("")


def _render_response(
    chat_log: "RichLog",
    professor: str,
    content: str,
    provider: str,
    filed_count_ref: list,  # mutable single-element list so we can update it
    category: str = "",
) -> None:
    safe = escape(content)

    if professor == "Gerald":
        if len(content) > GERALD_MAX_CHARS:
            content = content[:GERALD_MAX_CHARS].rstrip() + " *confetti*"
            safe = escape(content)
        width = max(20, min(len(content), 40))
        bar = "═" * width
        chat_log.write(f"[bold dark_goldenrod]╔══ napkin {bar}╗[/bold dark_goldenrod]")
        for line in content.split("\n"):
            chat_log.write(f"[dark_goldenrod]  {escape(line)}[/dark_goldenrod]")
        chat_log.write(f"[bold dark_goldenrod]╚{'═' * (width + 10)}╝[/bold dark_goldenrod]")
        chat_log.write("[dim]— G.[/dim]")

    elif professor == "Copenhagen":
        chat_log.write("[bold orange3]        🍊[/bold orange3]")
        chat_log.write("[dim italic]Hanz translates:[/dim italic]")
        chat_log.write(safe)

    elif professor == "Oakenscroll":
        formatted = re.sub(r"\*([^*]+)\*", r"[italic]\1[/italic]", safe)
        chat_log.write(f"[bold #5a5a9a]Oakenscroll:[/bold #5a5a9a] {formatted}")
        filed_count_ref[0] += 1
        tui_db.set_meta(professor, "filed_count", str(filed_count_ref[0]))
        chat_log.write(f"[dim]Filed. [{filed_count_ref[0]}][/dim]")

    elif professor == "Riggs":
        formatted = re.sub(r"\*([^*]+)\*", r"[bold yellow]\1[/bold yellow]", safe)
        chat_log.write(f"[bold yellow]Riggs:[/bold yellow] {formatted}")

    elif professor == "Ofshield":
        chat_log.write("[dim italic]*noted*[/dim italic]")
        chat_log.write(f"[#888888]Ofshield:[/#888888] {safe}")

    elif professor == "Steve":
        import random
        dog_num = random.randint(1, 10)
        dogs = "🌭" * 10
        chat_log.write(f"[bold red]{dogs}[/bold red]")
        chat_log.write(f"[bold red]\\[Dog {dog_num} of 10]:[/bold red] {safe}")

    elif professor == "Ada":
        chat_log.write(f"[bold green]Ada:[/bold green] {safe}")

    elif professor == "Nova":
        chat_log.write(f"[bold #c87c2a]✨ Nova:[/bold #c87c2a] {safe}")

    elif professor == "Hanz":
        chat_log.write(f"[bold #6ba3d6]Hanz:[/bold #6ba3d6] {safe}")

    elif professor == "Pigeon":
        chat_log.write(f"[bold #b08060]🐦 PIGEON:[/bold #b08060] {safe}")

    elif professor == "Jeles":
        chat_log.write(f"[bold #8b6914]Jeles:[/bold #8b6914] [italic]{safe}[/italic]")

    elif professor == "Binder":
        chat_log.write(f"[bold #a07830]Binder:[/bold #a07830] {safe}")
        label = category or "general correspondence"
        chat_log.write(f"[dim][Filed under: {escape(label)}][/dim]")

    elif professor == "Alexis":
        chat_log.write(f"[bold #5c8a4a]Alexis:[/bold #5c8a4a] {safe}")

    else:
        cfg = PROFESSOR_CONFIG.get(professor, {})
        icon = cfg.get("icon", "")
        chat_log.write(f"{icon} [bold]{escape(professor)}:[/bold] {safe}")

    if provider:
        chat_log.write(f"[dim]  ↳ {escape(provider)}[/dim]")

    chat_log.write("")


# ── App ───────────────────────────────────────────────────────────────────────

if TEXTUAL_OK:

    class UTETYApp(App):
        """UTETY — University of Technical Entropy, Thank You."""

        TITLE = "UTETY"
        SUB_TITLE = "Non Veritas Sed Vibrae"

        CSS = """
        Screen {
            layout: vertical;
        }

        #body {
            height: 1fr;
        }

        #sidebar {
            width: 22;
            border-right: solid $primary-darken-2;
        }

        #sidebar-header {
            height: 1;
            background: $primary-darken-3;
            color: $text;
            text-style: bold;
            content-align: center middle;
            padding: 0 1;
        }

        #faculty-list {
            height: 1fr;
        }

        #faculty-list > ListItem {
            height: 1;
            padding: 0 1;
        }

        #main {
            width: 1fr;
            padding: 0 1;
        }

        #prof-header {
            height: 1;
            background: $panel;
            color: $text;
            text-style: bold;
            padding: 0 1;
        }

        #chat-log {
            height: 1fr;
            border: heavy white;
            padding: 0 1;
            margin-top: 1;
        }

        #waiting-indicator {
            height: 1;
            padding: 0 1;
            color: $text-muted;
        }

        #message-input {
            height: 3;
            margin-top: 1;
        }
        """

        BINDINGS = [
            Binding("ctrl+c", "quit", "Quit", show=True),
            Binding("ctrl+x", "export", "Export", show=True),
            Binding("ctrl+d", "clear", "Clear history", show=True),
            Binding("ctrl+l", "focus_list", "Faculty", show=True),
            Binding("escape", "focus_input", "Focus input", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._active_professor: str = "Willow"
            self._history: list[dict] = []
            self._tier: str = "?"
            self._filed_count: list[int] = [0]
            self._busy: bool = False
            self._stream_buf: str = ""

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with Vertical(id="sidebar"):
                    yield Static("  FACULTY", id="sidebar-header")
                    yield ListView(id="faculty-list")
                with Vertical(id="main"):
                    yield Static("", id="prof-header")
                    yield RichLog(id="chat-log", markup=True, highlight=False, wrap=True)
                    yield Static("", id="waiting-indicator")
                    yield Input(placeholder=DEFAULT_PROMPT, id="message-input")
            yield Footer()

        def on_mount(self) -> None:
            faculty_list = self.query_one("#faculty-list", ListView)
            for f in FACULTY:
                faculty_list.append(ListItem(Label(f"{f['icon']} {f['name']}")))
            self._switch_professor("Willow")
            faculty_list.index = 0  # pre-select Willow so first Down goes to Oakenscroll
            faculty_list.focus()

        # ── Professor switching ───────────────────────────────────────────────

        def _switch_professor(self, name: str) -> None:
            self._active_professor = name
            self._filed_count[0] = int(tui_db.get_meta(name, "filed_count", "0"))
            self._history = tui_db.load_history(name)

            cfg = PROFESSOR_CONFIG.get(name, {})
            dept = cfg.get("dept", "")
            icon = cfg.get("icon", "")
            self.sub_title = f"{icon} {name} · {dept}"

            # Border color
            chat_log = self.query_one("#chat-log", RichLog)
            color = BORDER_COLORS.get(name, "white")
            chat_log.styles.border = ("heavy", color)

            # Input placeholder
            self.query_one("#message-input", Input).placeholder = INPUT_PROMPTS.get(
                name, DEFAULT_PROMPT
            )

            # Repopulate log
            chat_log.clear()

            if name == "Copenhagen":
                chat_log.write("")
                chat_log.write("[bold orange3]                    🍊[/bold orange3]")
                chat_log.write("[dim]Copenhagen is present. Hanz translates.[/dim]")
                chat_log.write("")

            if not self._history:
                greeting = GREETINGS.get(name)
                if greeting:
                    formatted = re.sub(r"\*([^*]+)\*", r"[italic]\1[/italic]", escape(greeting))
                    chat_log.write(f"[dim]{formatted}[/dim]")
                    chat_log.write("")
            else:
                for msg in self._history:
                    if msg["role"] == "user":
                        _render_user(chat_log, msg["content"])
                    else:
                        _render_response(
                            chat_log, name, msg["content"],
                            msg.get("provider", ""), self._filed_count
                        )

            self._update_prof_header()

        def _update_prof_header(self) -> None:
            name = self._active_professor
            cfg = PROFESSOR_CONFIG.get(name, {})
            dept = cfg.get("dept", "")
            icon = cfg.get("icon", "")
            extra = ""
            if name == "Oakenscroll" and self._filed_count[0] > 0:
                extra = f"  [dim][Filed: {self._filed_count[0]}][/dim]"
            elif name == "Ada":
                extra = "  [green][uptime: ∞][/green]"
            elif name == "Steve":
                extra = "  [red]🌭🌭🌭🌭🌭🌭🌭🌭🌭🌭[/red]"
            header = f"{icon} [bold]{escape(name)}[/bold] — {escape(dept)}{extra}"
            self.query_one("#prof-header", Static).update(header)

        # ── Sending ───────────────────────────────────────────────────────────

        def _send_message(self, text: str) -> None:
            if self._busy:
                self.notify("Still thinking...", severity="warning")
                return
            text = text.strip()
            if not text:
                return

            professor = self._active_professor
            chat_log = self.query_one("#chat-log", RichLog)

            _render_user(chat_log, text)
            tui_db.save_message(professor, "user", text)
            self._history.append({"role": "user", "content": text})

            self._busy = True
            self._stream_buf = ""
            waiting_msg = WAITING.get(professor, DEFAULT_WAITING)
            indicator = self.query_one("#waiting-indicator", Static)
            indicator.update(f"[dim italic]{escape(waiting_msg)}[/dim italic]")

            prompt = _build_prompt(professor, self._history)

            def on_chunk(token: str) -> None:
                self._stream_buf += token
                tail = self._stream_buf[-400:]
                self.call_from_thread(
                    indicator.update,
                    f"[dim italic]{escape(professor)}:[/dim italic] {escape(tail)}",
                )

            def work():
                llm_result = tui_llm.ask(prompt, professor=professor, on_chunk=on_chunk)
                if professor == "Binder" and llm_result.get("ok"):
                    llm_result["binder_category"] = tui_llm.categorize_for_binder(text)
                return llm_result

            self.run_worker(work, thread=True, name="utety_llm", exclusive=True)

        def on_worker_state_changed(self, event) -> None:
            if getattr(event.worker, "name", None) != "utety_llm":
                return
            if not event.worker.is_finished:
                return

            self.query_one("#waiting-indicator", Static).update("")
            self._stream_buf = ""
            self._busy = False

            professor = self._active_professor
            chat_log = self.query_one("#chat-log", RichLog)

            try:
                result = event.worker.result
            except Exception as exc:
                self.notify(f"LLM error: {exc}", severity="error")
                return

            if not result or not result.get("ok"):
                error = (result or {}).get("error", "all tiers failed")
                self.notify(f"No response: {error}", severity="error")
                return

            text = result["text"]
            provider = result.get("provider", "")
            tier = result.get("tier", "?")

            self._tier = tier
            cfg = PROFESSOR_CONFIG.get(professor, {})
            self.sub_title = (
                f"{cfg.get('icon', '')} {professor} · {cfg.get('dept', '')} · [{tier}]"
            )

            category = result.get("binder_category", "")
            _render_response(chat_log, professor, text, provider, self._filed_count, category)
            tui_db.save_message(professor, "assistant", text, provider)
            self._history.append({"role": "assistant", "content": text, "provider": provider})
            self._update_prof_header()

        # ── Input / navigation ────────────────────────────────────────────────

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "message-input":
                text = event.value
                event.input.value = ""
                self._send_message(text)

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            if event.item is None:
                return
            try:
                idx = list(event.list_view.children).index(event.item)
            except ValueError:
                return
            if 0 <= idx < len(FACULTY):
                name = FACULTY[idx]["name"]
                if name != self._active_professor:
                    self._switch_professor(name)

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            # Enter on list → drop focus to input, ready to type
            self.query_one("#message-input", Input).focus()

        # ── Actions ───────────────────────────────────────────────────────────

        def action_clear(self) -> None:
            professor = self._active_professor
            tui_db.clear_history(professor)
            self._history = []
            self._filed_count[0] = 0
            tui_db.set_meta(professor, "filed_count", "0")
            chat_log = self.query_one("#chat-log", RichLog)
            chat_log.clear()
            greeting = GREETINGS.get(professor)
            if greeting:
                formatted = re.sub(r"\*([^*]+)\*", r"[italic]\1[/italic]", escape(greeting))
                chat_log.write(f"[dim]{formatted}[/dim]")
                chat_log.write("")
            self._update_prof_header()
            self.notify(f"Cleared {professor}'s history.", severity="information")

        def action_export(self) -> None:
            professor = self._active_professor
            content = tui_db.export_markdown(professor)
            out_dir = Path(__file__).parent / "data" / "exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{professor.lower()}_export.md"
            out_path.write_text(content, encoding="utf-8")
            self.notify(f"Exported → {out_path.name}", severity="information")

        def action_focus_input(self) -> None:
            self.query_one("#message-input", Input).focus()

        def action_focus_list(self) -> None:
            self.query_one("#faculty-list", ListView).focus()


def main() -> None:
    if not TEXTUAL_OK:
        print("textual is not installed.")
        print("Run:  make install app=utety-chat")
        sys.exit(1)
    UTETYApp().run()


if __name__ == "__main__":
    main()
