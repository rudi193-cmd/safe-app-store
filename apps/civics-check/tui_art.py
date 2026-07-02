"""ASCII ceremony assets for the civics fair TUI.

Hero band is HERO_ROWS tall (matches #ceremony-band in tui.py): a night-sky
star field with the FREEDOM 250 word mark floating centered in it.
Rendering: Rich Text objects (no bracket markup) so glyphs stay literal.
"""

from __future__ import annotations

import random

from rich.style import Style
from rich.text import Text

import bell

HERO_ROWS = 10
CURTAIN_W = 8

# Rich styles (Textual Static.update accepts Text — avoids markup parse errors)
_STYLE_MARK = Style(color="#d4a017", bold=True)
_STYLE_MARK_SHADOW = Style(color="#0d1526")  # darker than the navy band — cast shadow

# Maroon stage curtains — vertical fold stripes via glyph density, not animation.
_CURTAIN_BG = "#3f0c0c"
_STYLE_CURTAIN = Style(color="#8a1f1f", bgcolor=_CURTAIN_BG)
_STYLE_CURTAIN_HI = Style(color="#a63030", bgcolor=_CURTAIN_BG)
_STYLE_CURTAIN_ROD = Style(color="#d4a017", bgcolor=_CURTAIN_BG, bold=True)

_CURTAIN_ROD_ROW = "▄▄▄▄▄▄▄▄"
_CURTAIN_FOLD_ROW = "█▓▒▓█▓▒▓"


def curtain_rich(rows: int = 60) -> Text:
    """One curtain panel, `rows` tall: gold rod, then repeating fold stripes."""
    out = Text()
    out.append(_CURTAIN_ROD_ROW, _STYLE_CURTAIN_ROD)
    for i in range(1, rows):
        out.append("\n")
        # every 4th row catches light — a highlight band across the folds
        style = _STYLE_CURTAIN_HI if i % 4 == 0 else _STYLE_CURTAIN
        out.append(_CURTAIN_FOLD_ROW, style)
    return out


# ── FREEDOM 250 word mark (hero center) ───────────────────────────────────────
# 8 rows: FREEDOM (3) + shadow (1) + 250 (3) + shadow (1).
# Every line padded to _MARK_W so Textual's text-align: center keeps the
# shadow's 2-column offset instead of re-centering each line independently.

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
_MARK_W = len(_FREEDOM_ROWS[0]) + 2  # word width + 2-col shadow offset
FREEDOM_MARK_ROWS = 8


def _silhouette(rows: list[str]) -> str:
    """Columns where any row has ink — the word's footprint, gaps preserved."""
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

# ── Star field (fills the hero band around the mark) ─────────────────────────
# Positions are seeded (1776) so the sky is the same every render; `phase`
# rotates each star through bright/gold/dim, so advancing phase makes the
# field sparkle. phase=0 is the resting sky.

_STAR_GLYPHS = "✦✧⋆·˙*"
_STAR_STYLES = [
    Style(color="#f0e4c8", bold=True),  # bright
    Style(color="#d4a017"),             # gold
    Style(color="#3d5680"),             # dim — barely above the navy
]
_STAR_SEED = 1776
_STAR_DENSITY = 14  # one star per N cells

# ── Landmark silhouettes (permanent skyline, bottom-anchored) ─────────────────
# Dim navy-blue silhouettes; the torch flame is the lone gold accent.

_STYLE_LANDMARK = Style(color="#2e4a72")
_STYLE_LANDMARK_ACCENT = Style(color="#d4a017")

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

_LEFT_LANDMARKS = [_WASHINGTON_MONUMENT, _GATEWAY_ARCH]  # edge outward → inward
_RIGHT_LANDMARKS = [_LIBERTY, _CAPITOL_DOME]             # edge inward

BUNTING = "★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★ · ★"


def hero_field(width: int, height: int = HERO_ROWS, phase: int = 0) -> Text:
    """Night sky `width`×`height`: FREEDOM 250 centered, landmark skyline on
    the horizon (two per side, dropped individually when width is too tight),
    stars everywhere else."""
    width = max(width, _MARK_W)
    mark = _mark_lines()
    top = max(0, (height - len(mark)) // 2)
    left = max(0, (width - _MARK_W) // 2)
    mark_right = left + _MARK_W

    # landmarks: bottom-anchored ink cells, silhouette style
    ink: dict[tuple[int, int], tuple[str, Style]] = {}

    def stamp(art: list[str], x0: int) -> None:
        y0 = height - len(art)
        for dy, row in enumerate(art):
            for dx, ch in enumerate(row):
                if ch != " ":
                    style = _STYLE_LANDMARK_ACCENT if ch == "✦" else _STYLE_LANDMARK
                    ink[(x0 + dx, y0 + dy)] = (ch, style)

    x = 1
    for art in _LEFT_LANDMARKS:
        w = max(len(r) for r in art)
        if x + w <= left - 2:
            stamp(art, x)
            x += w + 3
    xr = width - 1
    for art in _RIGHT_LANDMARKS:
        w = max(len(r) for r in art)
        if xr - w >= mark_right + 2:
            stamp(art, xr - w)
            xr -= w + 3

    rng = random.Random(_STAR_SEED)
    stars: dict[tuple[int, int], tuple[str, int]] = {}
    for i in range(max(6, (width * height) // _STAR_DENSITY)):
        sx, sy = rng.randrange(width), rng.randrange(height)
        # keep the mark's rectangle clear so the words float on empty sky
        if top <= sy < top + len(mark) and left - 1 <= sx < mark_right + 1:
            continue
        if (sx, sy) in ink:
            continue
        stars[(sx, sy)] = (rng.choice(_STAR_GLYPHS), i)

    out = Text()
    for y in range(height):
        if y:
            out.append("\n")
        cx = 0
        while cx < width:
            if top <= y < top + len(mark) and cx == left:
                line, style = mark[y - top]
                out.append(line, style)
                cx += _MARK_W
                continue
            cell = ink.get((cx, y))
            if cell:
                out.append(cell[0], cell[1])
            else:
                star = stars.get((cx, y))
                if star:
                    glyph, i = star
                    out.append(glyph, _STAR_STYLES[(i + phase) % len(_STAR_STYLES)])
                else:
                    out.append(" ")
            cx += 1
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


# ≤28 chars — must fit #preview-col (30 wide, 1-col padding each side)
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
}

EAGLE_PLAIN_BLOCK = bell.EAGLE_PLAIN.strip()  # CLI banner eagle lives in bell.py
