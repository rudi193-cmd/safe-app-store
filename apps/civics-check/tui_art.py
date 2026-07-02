"""ASCII ceremony assets for the civics fair TUI.

Hero band is HERO_ROWS tall (matches #ceremony-band in tui.py): a night-sky
star field with the FREEDOM 250 word mark floating centered in it.
Rendering: Rich Text objects (no bracket markup) so glyphs stay literal.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from rich.style import Style
from rich.text import Text

import bell

HERO_ROWS = 11
CURTAIN_W = 8

_DATA = Path(__file__).resolve().parent / "data" / "sources"

# Rich styles (Textual Static.update accepts Text — avoids markup parse errors)
_STYLE_MARK = Style(color="#d4a017", bold=True)
_STYLE_MARK_SHADOW = Style(color="#0d1526")
_STYLE_CAPTION = Style(color="#c9a85c", bold=True)
_STYLE_FAIR_DAY = Style(color="#3d5680")
_STYLE_MOTTO = Style(color="#2e4a72", italic=True)
_STYLE_HINT = Style(color="#6b4e0a")
_STYLE_OFFICIAL = Style(color="#e2c992")

# Maroon stage curtains — vertical fold stripes via glyph density, not animation.
_CURTAIN_BG = "#3f0c0c"
_STYLE_CURTAIN = Style(color="#8a1f1f", bgcolor=_CURTAIN_BG)
_STYLE_CURTAIN_HI = Style(color="#a63030", bgcolor=_CURTAIN_BG)
_STYLE_CURTAIN_ROD = Style(color="#d4a017", bgcolor=_CURTAIN_BG, bold=True)

_CURTAIN_ROD_ROW = "▄▄▄▄▄▄▄▄"
_CURTAIN_FOLD_ROW = "█▓▒▓█▓▒▓"

MOTTOS = ("E PLURIBUS UNUM", "ANNUIT COEPTIS", "NOVUS ORDO SECLORUM")

# fair_schedule theme → (number, gloss) for the hero numerology line
FAIR_DAY_NUMBERS: dict[str, tuple[str, str]] = {
    "We the People": ("7", "articles in the Constitution"),
    "13 Originals": ("13", "original colonies"),
    "Bill of Rights": ("10", "amendments in the Bill of Rights"),
    "Three Branches": ("3", "branches of government"),
    "50 Stars": ("50", "states · stars on the flag"),
    "Naturalization": ("100", "civics questions on the test"),
    "270 to Win": ("270", "electoral votes to win"),
    "1776": ("1776", "Declaration adopted"),
    "27 Changes": ("27", "amendments to the Constitution"),
    "Participation": ("18", "to vote"),
}

NAT_ACTIVITY_IDS = frozenset({"naturalization", "missed", "speed"})


@dataclass
class HeroContext:
    """Playbill lines and accents for the hero band — no ambient animation."""

    caption: str = ""
    fair_day: str = ""
    motto: str = ""
    canton: str = ""  # "13" | "50"
    landmark_accent: str = ""  # "capitol" | "liberty"
    solemn: bool = False
    nat_pass_hint: bool = False
    official_line: str = ""
    number_line: str = ""
    record_room: bool = False


def curtain_rich(rows: int = 60) -> Text:
    """One curtain panel, `rows` tall: gold rod, then repeating fold stripes."""
    out = Text()
    out.append(_CURTAIN_ROD_ROW, _STYLE_CURTAIN_ROD)
    for i in range(1, rows):
        out.append("\n")
        style = _STYLE_CURTAIN_HI if i % 4 == 0 else _STYLE_CURTAIN
        out.append(_CURTAIN_FOLD_ROW, style)
    return out


# ── FREEDOM 250 word mark (hero center) ───────────────────────────────────────

_FREEDOM_ROWS = [
    "█▀▀▀ █▀▀▄ █▀▀▀ █▀▀▀ █▀▀▄ ▄▀▀▄ █▄ ▄█",
    "█▀▀  █▀▀▄ █▀▀  █▀▀  █  █ █  █ █ ▀ █",
    "█    █  █ █▄▄▄ █▄▄▄ █▄▄▀ ▀▄▄▀ █   █",
]
_250_ROWS = [
    "▀▀▀▄ █▀▀▀ ▄▀▀▄",
    " ▄▄▀ ▀▀▀▄ █  █",
    "█▄▄▄ ▄▄▄▀ ▀▄▄▀",
]
_MARK_W = len(_FREEDOM_ROWS[0]) + 2
FREEDOM_MARK_ROWS = 8


def _silhouette(rows: list[str]) -> str:
    width = max(len(r) for r in rows)
    padded = [r.ljust(width) for r in rows]
    return "".join("░" if any(r[c] != " " for r in padded) else " " for c in range(width))


def _mark_lines() -> list[tuple[str, Style]]:
    lines: list[tuple[str, Style]] = []
    for row in _FREEDOM_ROWS:
        lines.append((row.ljust(_MARK_W), _STYLE_MARK))
    lines.append((("  " + _silhouette(_FREEDOM_ROWS)).ljust(_MARK_W), _STYLE_MARK_SHADOW))
    lead = (len(_FREEDOM_ROWS[0]) - len(_250_ROWS[0])) // 2
    for row in _250_ROWS:
        lines.append(((" " * lead + row).ljust(_MARK_W), _STYLE_MARK))
    shadow = " " * (lead + 2) + _silhouette(_250_ROWS)
    lines.append((shadow.ljust(_MARK_W), _STYLE_MARK_SHADOW))
    return lines


FREEDOM_MARK_PLAIN = "\n".join(line for line, _s in _mark_lines())

# ── Star field ────────────────────────────────────────────────────────────────

_STAR_GLYPHS = "✦✧⋆·˙*"
_STAR_STYLES = [
    Style(color="#f0e4c8", bold=True),
    Style(color="#d4a017"),
    Style(color="#3d5680"),
]
_STAR_SEED = 1776
_STAR_DENSITY = 14

_STYLE_LANDMARK = Style(color="#2e4a72")
_STYLE_LANDMARK_ACCENT = Style(color="#d4a017")
_STYLE_LANDMARK_GLOW = Style(color="#f0e4c8", bold=True)

_WASHINGTON_MONUMENT = [
    "   ▲",
    "   █",
    "   █",
    "   █",
    "  ▐█▌",
    "▄▄▄███▄▄▄",
]
_GATEWAY_ARCH = [
    "  ▄▄▀▀▀▀▀▄▄",
    " █▀       ▀█",
    "▐▌         ▐▌",
    "█▌         ▐█",
]
_CAPITOL_DOME = [
    "     ★",
    "   ▄▀▀▀▄",
    "  ▄█████▄",
    " ▐ ║ ║ ║ ▌",
    "▄▄▄▄▄▄▄▄▄▄▄",
]
_LIBERTY = [
    "   ✦",
    "   ▌",
    " ▗▟█▖",
    "  ▐█▌",
    "  ▐█▌",
    " ▄███▄",
    "▀█████▀",
]

_LEFT_LANDMARKS = [_WASHINGTON_MONUMENT, _GATEWAY_ARCH]
_RIGHT_LANDMARKS = [_LIBERTY, _CAPITOL_DOME]

BUNTING = "★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★"


def _load_current_officials() -> dict:
    try:
        return json.loads((_DATA / "current_officials.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def card_is_solemn(card: dict | None) -> bool:
    if not card:
        return False
    text = " ".join(
        str(card.get(k, "")) for k in ("title", "body", "prompt", "context", "subtitle")
    ).lower()
    needles = (
        "deadliest", "trail of tears", "gettysburg", "mankato", "9066",
        "concentration", "mass execution", "abbey gate", "family-separation",
        "waterboarding", "torture", "atrocity",
    )
    return any(n in text for n in needles)


def card_landmark_accent(card: dict | None) -> str:
    if not card:
        return ""
    pavilion = card.get("pavilion", "")
    tags = set(card.get("tags") or [])
    sub = (card.get("subcategory") or "").lower()
    cat = (card.get("category") or "").lower()
    if pavilion in ("rights_bingo",) or "bill of rights" in tags or "first amendment" in sub:
        return "liberty"
    if pavilion in ("branches", "bill_law", "electoral") or "legislative" in sub:
        return "capitol"
    if "system of government" in sub or "american government" in cat:
        if any(w in (card.get("prompt") or "").lower() for w in ("congress", "senate", "house", "law")):
            return "capitol"
    return ""


def official_line_for_card(card: dict | None) -> str:
    if not card:
        return ""
    officials = _load_current_officials()
    legacy = card.get("legacy_id")
    prompt = (card.get("prompt") or card.get("title") or "").lower()
    if legacy == 28 or "president of the united states now" in prompt:
        p = officials.get("president", {})
        return f"President: {p.get('name', '')}".strip(": ")
    if legacy == 29 or "vice president" in prompt and "now" in prompt:
        v = officials.get("vice_president", {})
        return f"Vice President: {v.get('name', '')}".strip(": ")
    if legacy == 46 or "political party of the president" in prompt:
        party = (officials.get("president_party", {}).get("answers") or ["Republican"])[0]
        return f"Party in office: {party}"
    if legacy == 47 or "speaker of the house" in prompt:
        s = officials.get("speaker", {})
        return f"Speaker: {s.get('name', '')}".strip(": ")
    return ""


def canton_for_lane(lane_id: str | None, pavilion_id: str | None) -> str:
    if lane_id in ("statehouse",) or pavilion_id in ("state_stars", "states"):
        return "50"
    if lane_id in ("schoolhouse", "constitution_hall", "citizenship_court"):
        return "13"
    return ""


def _center_text(text: str, width: int) -> str:
    text = text[: max(0, width)]
    if len(text) >= width:
        return text[:width]
    pad = width - len(text)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def _stamp_canton(grid: list[list[tuple[str, Style | None]]], era: str) -> None:
    if era not in ("13", "50"):
        return
    glyphs = "★" if era == "13" else "★·"
    label = f" {era}★ " if era == "13" else " 50★ "
    style = Style(color="#d4a017", bold=True)
    for i, ch in enumerate(label[: len(grid[0]) - 1]):
        if ch != " ":
            grid[0][1 + i] = (ch, style)


def _stamp_text_row(
    grid: list[list[tuple[str, Style | None]]],
    y: int,
    text: str,
    style: Style,
) -> None:
    if y < 0 or y >= len(grid):
        return
    width = len(grid[y])
    row = _center_text(text, width)
    for x, ch in enumerate(row):
        if ch != " ":
            grid[y][x] = (ch, style)


def hero_field(
    width: int,
    height: int = HERO_ROWS,
    phase: int = 0,
    ctx: HeroContext | None = None,
    *,
    sparkle_mode: str = "normal",
    ripple_tick: int = 0,
) -> Text:
    """Night sky with FREEDOM 250, skyline, playbill captions, and event sparkle."""
    ctx = ctx or HeroContext()
    width = max(width, _MARK_W)
    height = max(height, HERO_ROWS)
    mark = _mark_lines()
    top = max(0, (height - len(mark)) // 2)
    left = max(0, (width - _MARK_W) // 2)
    mark_right = left + _MARK_W
    cx, cy = width // 2, height // 2

    grid: list[list[tuple[str, Style | None]]] = [
        [(" ", None) for _ in range(width)] for _ in range(height)
    ]

    ink_landmarks: list[tuple[int, int, str]] = []

    def stamp(art: list[str], x0: int, side: str) -> None:
        y0 = height - len(art)
        for dy, row in enumerate(art):
            for dx, ch in enumerate(row):
                if ch == " ":
                    continue
                x, y = x0 + dx, y0 + dy
                ink_landmarks.append((x, y, ch))
                if ch == "★" and side == "capitol" and ctx.landmark_accent == "capitol":
                    style = _STYLE_LANDMARK_GLOW
                elif ch == "✦" and side == "liberty" and ctx.landmark_accent == "liberty":
                    style = _STYLE_LANDMARK_GLOW
                elif ch in ("★", "✦"):
                    style = _STYLE_LANDMARK_ACCENT
                else:
                    style = _STYLE_LANDMARK
                grid[y][x] = (ch, style)

    x = 1
    for art in _LEFT_LANDMARKS:
        w = max(len(r) for r in art)
        if x + w <= left - 2:
            stamp(art, x, "left")
            x += w + 3
    xr = width - 1
    for art in _RIGHT_LANDMARKS:
        w = max(len(r) for r in art)
        side = "liberty" if art is _LIBERTY else "capitol"
        if xr - w >= mark_right + 2:
            stamp(art, xr - w, side)
            xr -= w + 3

    ink_set = {(a, b) for a, b, _ in ink_landmarks}
    rng = random.Random(_STAR_SEED)
    stars: dict[tuple[int, int], tuple[str, int]] = {}
    for i in range(max(6, (width * height) // _STAR_DENSITY)):
        sx, sy = rng.randrange(width), rng.randrange(height)
        if top <= sy < top + len(mark) and left - 1 <= sx < mark_right + 1:
            continue
        if (sx, sy) in ink_set:
            continue
        stars[(sx, sy)] = (rng.choice(_STAR_GLYPHS), i)

    for (sx, sy), (glyph, i) in stars.items():
        if ctx.solemn:
            style = _STAR_STYLES[2]
        elif sparkle_mode == "ripple" and ripple_tick > 0:
            dist = abs(sx - cx) + abs(sy - cy)
            wave = abs(dist - ripple_tick * 2)
            if wave <= 2:
                style = _STAR_STYLES[0]
            elif wave <= 4:
                style = _STAR_STYLES[1]
            else:
                style = _STAR_STYLES[(i + phase) % len(_STAR_STYLES)]
        else:
            style = _STAR_STYLES[(i + phase) % len(_STAR_STYLES)]
        grid[sy][sx] = (glyph, style)

    for y in range(top, min(top + len(mark), height)):
        line, style = mark[y - top]
        for dx, ch in enumerate(line):
            x = left + dx
            if x < width and ch != " ":
                grid[y][x] = (ch, style)

    caption_row = height - 1
    motto_row = height - 2 if height >= 2 else height - 1

    if ctx.fair_day:
        _stamp_text_row(grid, 0, ctx.fair_day, _STYLE_FAIR_DAY)
    if ctx.canton:
        _stamp_canton(grid, ctx.canton)
    if ctx.number_line:
        _stamp_text_row(grid, motto_row, ctx.number_line, _STYLE_HINT)
    elif ctx.motto:
        _stamp_text_row(grid, motto_row, ctx.motto, _STYLE_MOTTO)
    if ctx.official_line:
        _stamp_text_row(grid, max(0, motto_row - 1), ctx.official_line, _STYLE_OFFICIAL)
    if ctx.nat_pass_hint:
        _stamp_text_row(grid, caption_row, "6 of 10 to pass · Citizenship Court", _STYLE_HINT)
    elif ctx.record_room:
        _stamp_text_row(grid, caption_row, "❧ Record Room · sources & further reading", _STYLE_CAPTION)
    elif ctx.caption:
        _stamp_text_row(grid, caption_row, ctx.caption, _STYLE_CAPTION)

    out = Text()
    for y in range(height):
        if y:
            out.append("\n")
        for x in range(width):
            ch, style = grid[y][x]
            if style:
                out.append(ch, style)
            else:
                out.append(ch)
    return out


def fair_rail(lane_index: int = 0, fair_day: str = "open all week") -> str:
    markers = [" ", " ", " "]
    if 0 <= lane_index < 3:
        markers[lane_index] = "▶"
    return (
        f"⌂ Schoolhouse{markers[0]}   "
        f"§ Constitution Hall{markers[1]}   "
        f"⚖ Citizenship Court{markers[2]}   "
        f"· {fair_day[:22]}"
    )


def fair_map(lane_index: int = 0, fair_day: str = "open all week") -> str:
    return fair_rail(lane_index, fair_day)


FLARE_PLAZA = "╔ LIBERTY PLAZA · hollow? ╗"
FLARE_PLAZA_HOT = "╔ LIBERTY PLAZA · 109 ╗"

FALL_THROUGH_FRAMES = [
    "THE FLOOR GIVES WAY",
    "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓",
    "DIENAMIC SYSTEMS",
    "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒",
    "under the civics fair",
]

FIREWORK_FRAMES = [
    "        *        ",
    "      \\ | /      ",
    "    -- * * * --  ",
    "      / | \\      ",
    "        *        ",
]

PAVILION_ICONS = {
    "tap": "◆",
    "show": "▸",
    "know": "★",
}

DIENAMIC_LOGO = "╔ DIENAMIC SYSTEMS · factory floor beneath ╗"

LANE_ICONS = {
    "schoolhouse": "⌂ Schoolhouse",
    "constitution_hall": "§ Constitution Hall",
    "citizenship_court": "⚖ Citizenship Court",
    "statehouse": "⚑ States' Rights & Duties",
    "_record_room": "❧ Record Room",
}

LIBERTY_BELL_BLOCK = bell.LIBERTY_BELL_PLAIN.strip()
