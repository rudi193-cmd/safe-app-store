"""Environmental hero — catalog desk at the Stacks (Grove-style persistent band)."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from askjeles.classify import QueryClass, classify

log = logging.getLogger("jeles.hero")

_DRAWERS = ("kb", "web", "maps", "stacks")
_DRAWER_LABELS = {
    "kb": "YOUR KB",
    "web": "OPEN WEB",
    "maps": "MAPS",
    "stacks": "STACKS",
}

_CARDS = ["▢", "▣", "□", "▤"]

# Block wordmark — center nameplate focal point
_NAMEPLATE_ART = [
    r"    __ _____ __    _____ _____",
    r" __|  |   __|  |  |   __|   __|",
    r"|  |  |   __|  |__|   __|__   |",
    r"|_____|_____|_____|_____|_____|",
]

_QUOTE = "The things we think we've lost are simply misfiled."
_HERO_EGGS_PATH = Path(__file__).resolve().parent.parent / "data" / "hero_eggs.json"
_DEFAULT_SPINNER = ("Checking the wrong drawer first...", "Polishing the hyperlinks...")
_DEFAULT_HOOKS = (("42", "MOSTLY HARMLESS"),)


def _hero_eggs() -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Load amendable hero spinner text from data/hero_eggs.json."""
    try:
        raw = json.loads(_HERO_EGGS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("hero_eggs.json unavailable: %s", exc)
        return _DEFAULT_SPINNER, _DEFAULT_HOOKS

    spinner = tuple(
        str(line).strip()
        for line in raw.get("spinner", [])
        if isinstance(line, str) and line.strip()
    )
    hooks: list[tuple[str, str]] = []
    for item in raw.get("query_hooks", []):
        if not isinstance(item, dict):
            continue
        match = str(item.get("match") or "").strip().lower()
        message = str(item.get("message") or "").strip()
        if match and message:
            hooks.append((match, message))

    return spinner or _DEFAULT_SPINNER, tuple(hooks) or _DEFAULT_HOOKS


def _drawer_for_query(query: str) -> str:
    qclass = classify(query)
    if qclass == QueryClass.NAVIGATIONAL:
        return "maps"
    if qclass == QueryClass.RESEARCH:
        return "stacks"
    return "kb"


def _spinner_hook(query: str) -> str | None:
    q = (query or "").lower()
    _spinner, hooks = _hero_eggs()
    for needle, line in hooks:
        if needle in q:
            return line
    return None


def _primary_drawer_from_sources(sources: list[str]) -> str:
    for key in ("local_kb", "open_web", "maps", "stacks"):
        if key in sources:
            if key == "local_kb":
                return "kb"
            if key == "open_web":
                return "web"
            if key == "maps":
                return "maps"
            return "stacks"
    return "web"


class DeskArt(Static):
    """Left wing: catalog drawers (easter-egg space above/beside desk)."""

    DEFAULT_CSS = """
    DeskArt {
        width: 1fr;
        height: 7;
        color: #8b7355;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._frame = 0
        self._active = "kb"
        self._stamp = "DESK"
        self._egg = ""

    def set_active(self, drawer: str) -> None:
        if drawer in _DRAWER_LABELS:
            self._active = drawer

    def set_stamp(self, text: str) -> None:
        self._stamp = (text or "DESK")[:18]

    def set_egg(self, text: str) -> None:
        self._egg = (text or "").strip()[:40]
        self._redraw()

    def on_mount(self) -> None:
        self.set_interval(1.1, self._tick)
        self._redraw()

    def _tick(self) -> None:
        self._frame += 1
        self._redraw()

    def _box(self, drawer: str, top: bool) -> str:
        label = _DRAWER_LABELS[drawer]
        active = drawer == self._active
        if top:
            line = f"╭─{label.center(11)[:11]}─╮"
        else:
            rng = random.Random(self._frame * 17 + hash(drawer))
            cards = " ".join(rng.choice(_CARDS) for _ in range(3))
            line = f"│ {cards:^9} │"
        return f"[bold #c4a456]{line}[/]" if active else f"[dim]{line}[/]"

    def _redraw(self) -> None:
        egg = f"[dim italic]{self._egg}[/]\n" if self._egg else ""
        self.update(
            egg
            + f"{self._box('kb', True)}   {self._box('web', True)}\n"
            + f"{self._box('kb', False)}   {self._box('web', False)}\n"
            + f"[#6b5e4f]{'═' * 28}[/]\n"
            + f"{self._box('maps', True)}   {self._box('stacks', True)}\n"
            + f"{self._box('maps', False)}   {self._box('stacks', False)}\n"
            + f"[#8b3a2a]╢[/] [bold]{self._stamp}[/] [dim]· desk[/]"
        )


class NamePlate(Static):
    """Center: JELES nameplate + quote (true visual anchor)."""

    DEFAULT_CSS = """
    NamePlate {
        width: auto;
        max-width: 52;
        height: 7;
        color: #c4a456;
        padding: 0 2;
        content-align: center middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._mode = "DESK"

    def set_mode(self, mode: str) -> None:
        self._mode = (mode or "DESK")[:12]
        self._redraw()

    def on_mount(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        art = "\n".join(f"[bold #c4a456]{line}[/]" for line in _NAMEPLATE_ART)
        self.update(
            "[#8b3a2a]╭────────── THE STACKS ──────────╮[/]\n"
            f"{art}\n"
            "[dim]HEAD LIBRARIAN · UTETY[/]\n"
            f"[italic #9a7b3c]{_QUOTE}[/]\n"
            f"[#8b3a2a]╰────[/][dim] {self._mode} [/][#8b3a2a]────────────────╯[/]"
        )


class HeroInfo(Static):
    """Right wing: live status (easter-egg space)."""

    DEFAULT_CSS = """
    HeroInfo {
        width: 1fr;
        height: 7;
        color: #6b5e4f;
        padding: 0 1;
        content-align: right middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._status = "ready"
        self._detail = ""
        self._active = "kb"
        self._egg = ""

    def set_status(self, status: str, detail: str = "", active: str = "kb") -> None:
        self._status = status[:40]
        self._detail = detail[:60]
        if active in _DRAWER_LABELS:
            self._active = active
        self._redraw()

    def set_egg(self, text: str) -> None:
        self._egg = (text or "").strip()[:40]
        self._redraw()

    def on_mount(self) -> None:
        self.set_interval(30.0, self._redraw)
        self._redraw()

    def _redraw(self) -> None:
        now = datetime.now().strftime("%H:%M")
        order = " · ".join(
            f"[bold #c4a456]{d.upper()}[/]" if d == self._active else d.upper()
            for d in _DRAWERS
        )
        detail = f"\n[dim]{self._detail}[/]" if self._detail else ""
        egg = f"[dim italic]{self._egg}[/]\n\n" if self._egg else "\n"
        self.update(
            egg
            + f"{order}\n"
            + f"[dim]{now}[/]  [bold]{self._status}[/]{detail}\n"
            + "[dim]KB → WEB → MAPS → STACKS[/]"
        )


class DeskStrip(Static):
    """Full-width ribbon under the nameplate."""

    DEFAULT_CSS = """
    DeskStrip {
        height: 2;
        width: 100%;
        color: #9a7b3c;
        padding: 0 2;
        content-align: left middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._frame = 0
        self._message = ""

    def set_message(self, text: str) -> None:
        self._message = text.strip()
        self._redraw()

    def on_mount(self) -> None:
        self.set_interval(1.4, self._tick)
        self._redraw()

    def _tick(self) -> None:
        self._frame += 1
        self._redraw()

    def _redraw(self) -> None:
        if self._message:
            width = max(40, self.size.width or 100)
            pad = " " * max(0, int(width * 0.28))
            self.update(
                f"{pad}[#8b3a2a]╢[/] [bold #f0c36a]{self._message}[/]\n"
                f"{pad}[dim]search desk output[/]"
            )
            return
        motes = ["·", " ", ".", " ", "·", " ", "·", " "]
        shift = self._frame % len(motes)
        line = "".join(motes[shift:] + motes[:shift])
        width = max(40, self.size.width or 100)
        pad = " " * max(0, int(width * 0.24))
        self.update(f"{pad}[dim]{line}  YOUR KB → OPEN WEB → MAPS → SPECIAL COLLECTIONS  {line}[/]")


class HeroScene(Vertical):
    """Persistent catalog-desk hero."""

    DEFAULT_CSS = """
    HeroScene {
        height: 10;
        background: #1a1510;
        border-bottom: solid #9a7b3c;
    }
    #hero-top {
        height: 8;
        width: 100%;
        align: center middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._searching = False
        self._spin_idx = 0
        self._spin_rng = random.Random()

    def compose(self) -> ComposeResult:
        with Horizontal(id="hero-top"):
            yield DeskArt(id="desk-art")
            yield NamePlate(id="nameplate")
            yield HeroInfo(id="hero-info")
        yield DeskStrip(id="desk-strip")

    def on_mount(self) -> None:
        self.set_interval(1.5, self._search_spin_tick)

    def _stop_search_spin(self) -> None:
        self._searching = False
        self.query_one("#desk-strip", DeskStrip).set_message("")
        self.query_one("#desk-art", DeskArt).set_egg("")
        self.query_one("#hero-info", HeroInfo).set_egg("")

    def stop_search_spin(self) -> None:
        """Clear transient search spinner text without changing result/idle state."""
        self._stop_search_spin()

    def _search_spin_tick(self) -> None:
        if not self._searching:
            return
        spinner, _hooks = _hero_eggs()
        n = len(spinner)
        self._spin_idx = (self._spin_idx + 1) % n
        line = spinner[self._spin_idx]
        self.query_one("#desk-strip", DeskStrip).set_message(line)
        self.query_one("#desk-art", DeskArt).set_egg("")
        self.query_one("#hero-info", HeroInfo).set_egg("")

    def set_idle(self, *, online: bool = True) -> None:
        self._stop_search_spin()
        art = self.query_one("#desk-art", DeskArt)
        plate = self.query_one("#nameplate", NamePlate)
        info = self.query_one("#hero-info", HeroInfo)
        strip = self.query_one("#desk-strip", DeskStrip)
        art.set_active("kb")
        art.set_stamp("DESK")
        art.set_egg("")
        plate.set_mode("DESK")
        info.set_status("ready" if online else "offline", active="kb")
        info.set_egg("")
        strip.set_message("")

    def set_query_preview(self, query: str) -> None:
        """Highlight the likely drawer while typing, without starting spinner text."""
        self._stop_search_spin()
        active = _drawer_for_query(query)
        art = self.query_one("#desk-art", DeskArt)
        plate = self.query_one("#nameplate", NamePlate)
        info = self.query_one("#hero-info", HeroInfo)
        art.set_active(active)
        art.set_stamp("READY")
        plate.set_mode("READY")
        q = (query or "").strip()
        preview = f"«{q[:36]}»" if q else ""
        info.set_status("ready", preview, active=active)

    def set_searching(self, query: str) -> None:
        active = _drawer_for_query(query)
        art = self.query_one("#desk-art", DeskArt)
        plate = self.query_one("#nameplate", NamePlate)
        info = self.query_one("#hero-info", HeroInfo)
        strip = self.query_one("#desk-strip", DeskStrip)
        art.set_active(active)
        art.set_stamp("SEARCH")
        plate.set_mode("SEARCH")
        q = (query or "").strip()
        preview = f"«{q[:36]}»" if q else ""
        info.set_status("searching…", preview, active=active)

        spinner, _hooks = _hero_eggs()
        hook = _spinner_hook(q)
        self._searching = True
        self._spin_idx = self._spin_rng.randint(0, max(0, len(spinner) - 1))
        first = hook or spinner[self._spin_idx]
        strip.set_message(first)
        art.set_egg("")
        info.set_egg("")

    def set_results(self, payload: dict) -> None:
        self._stop_search_spin()
        art = self.query_one("#desk-art", DeskArt)
        plate = self.query_one("#nameplate", NamePlate)
        info = self.query_one("#hero-info", HeroInfo)
        sources = payload.get("sources_used") or []
        active = _primary_drawer_from_sources(sources)
        if payload.get("query_class") == "navigational":
            active = "maps"
        elif payload.get("query_class") == "research":
            active = "stacks"
        total = payload.get("total", 0)
        backend = payload.get("backend") or "—"
        err = payload.get("error") or ""
        art.set_active(active)
        art.set_stamp("FOUND" if total else "EMPTY")
        plate.set_mode("FOUND" if total else "EMPTY")
        if err:
            info.set_status("error", err[:50], active=active)
        else:
            info.set_status(f"{total} found", backend, active=active)

    def set_trivia_pending(self) -> None:
        self._stop_search_spin()
        art = self.query_one("#desk-art", DeskArt)
        plate = self.query_one("#nameplate", NamePlate)
        info = self.query_one("#hero-info", HeroInfo)
        strip = self.query_one("#desk-strip", DeskStrip)
        art.set_stamp("TRIVIA")
        plate.set_mode("TRIVIA")
        info.set_status("quiz mode", "from current results", active="kb")
        strip.set_message("Ctrl+T — quiz from your search")

    def set_easter_egg(self, left: str = "", right: str = "") -> None:
        """Hook for future hero easter eggs in the wing panels."""
        self.query_one("#desk-art", DeskArt).set_egg(left)
        self.query_one("#hero-info", HeroInfo).set_egg(right)
