"""Easter eggs: Gerald's napkin words, hidden on a board by its seed.

The words are Gerald's napkin vocabulary, read from the gerald bot beside this
app (``apps/UTETY-Reddit-Bots/gerald-bot/src/data/napkins.json``): single
words that "feel load-bearing even when they don't make sense", canon from
the operator's material. The bot drops one at random; here the seed decides,
so the same board always holds the same napkin in the same cell, and a found
one can be found again and shown to someone else.

About one board in ``ODDS`` has a napkin. It sits under a cell with no cat in
the answer, and it turns up when that cell is marked x: the move a careful
player makes anyway.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .rng import Rng

ODDS = 3


def default_path() -> Path:
    """``$CATGRID_NAPKINS``, else the gerald bot's napkin file in this repo."""
    if os.environ.get("CATGRID_NAPKINS"):
        return Path(os.environ["CATGRID_NAPKINS"]).expanduser()
    return (Path(__file__).resolve().parents[2] / "UTETY-Reddit-Bots" / "gerald-bot"
            / "src" / "data" / "napkins.json")


def load_napkins(path: Path | None = None) -> tuple[list, str]:
    """(words, why): the single-word napkins, or [] and why."""
    try:
        data = json.loads((path or default_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [], f"no napkin words to read ({type(e).__name__})"
    words = sorted({
        w for w in data.get("words", [])
        if isinstance(w, str) and w and not any(ch.isspace() for ch in w)
        and "todo" not in w.lower()
    })
    return (words, "") if words else ([], "the napkin file holds no words")


def hide(seed: int, words: list, empties: list) -> tuple[str, str] | None:
    """(cell, word) for this seed's napkin, or None when this board has none.
    ``empties`` are the cells with no cat in the answer, in board order."""
    if not words or not empties:
        return None
    rng = Rng((seed * 2246822519 + 0xE66) & 0xFFFFFFFF)
    if rng.below(ODDS):
        return None
    return rng.pick(empties), rng.pick(words)
