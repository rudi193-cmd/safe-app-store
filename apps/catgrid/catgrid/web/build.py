#!/usr/bin/env python3
"""Inline the engine and its data into one HTML page: the browser port, and
what an APK wraps.

The data is exported from the Python's own readers, never hand-copied: the
napkin words come from ``eggs.load_napkins`` (Gerald's file, in this repo).
The trivia bank does not ship in the page: Jeles's corpus stays with Jeles
(the store's rule: ship the reader, the corpus stays with whoever grew it), so
the page's trivia says ``unavailable`` and why, and the board plays the same.

    python3 catgrid/web/build.py   ->  catgrid/web/catgrid.html
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catgrid import eggs  # noqa: E402
from catgrid.board import LARGEST, SMALLEST  # noqa: E402

HERE = Path(__file__).resolve().parent
NO_TRIVIA = "the page carries no trivia bank: Jeles's corpus stays with Jeles"


def export() -> dict:
    words, why = eggs.load_napkins()
    return {"words": words, "words_why": why, "bank_why": NO_TRIVIA,
            "smallest": SMALLEST, "largest": LARGEST}


def render() -> str:
    """The page, as text: what ``build`` writes."""
    data = export()
    page = (HERE / "page.html").read_text(encoding="utf-8")
    engine = (HERE / "engine.js").read_text(encoding="utf-8")
    engine = re.sub(r"\nif \(typeof module.*?\n\}\n", "\n", engine, flags=re.S)
    blob = json.dumps(data, ensure_ascii=False)
    if "</script" in engine or "</script" in blob:
        sys.exit("payload contains a script-closing sequence; refusing to inline")
    marker = "/* ENGINE */"
    if marker not in page:
        sys.exit("page.html lost its /* ENGINE */ marker")
    return page.replace(marker, "var CATGRID_DATA = " + blob + ";\n" + engine)


def build() -> Path:
    dest = HERE / "catgrid.html"
    dest.write_text(render(), encoding="utf-8")
    return dest


if __name__ == "__main__":
    p = build()
    print(f"{p} ({p.stat().st_size:,} bytes)")
