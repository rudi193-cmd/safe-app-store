"""build.py: lay Die-Namic's games and worlds into its pages. Python 3.9+.

    python apps/game/ui/build.py

Writes two pages from their sources:
- index.html, the front page (index.src.html): every game in games/, its
  name, line, how to play and where it came from read from its own
  README.md, so the shelf follows the folder.
- table.html, the table (table.src.html): the box's worlds (box/worlds/*.json)
  played in the browser.

Both are sketches in the browser: their dice are the browser's and nothing
is written to the record. The record is the games' own, played by play.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent
MARK = "/*__DATA__*/null"


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def game(folder: Path) -> dict:
    text = (folder / "README.md").read_text()
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip()
    summary = next(ln for ln in lines[1:] if ln.strip())
    playing = section(text, "Playing it")
    block = re.search(r"```\n(.*?)```", playing, re.S)
    commands = [ln for ln in (block.group(1) if block else "").splitlines() if ln.strip()]
    notes = re.sub(r"```.*?```", "", playing, flags=re.S).strip()
    came = section(text, "Where it came from")
    checked = re.search(r"(?:on|in) ([\d,]{4,}) (positions|states|moves|bids)", came)
    card = re.search(r"\((https://github\.com/willow-memory/Willow/tree/[^)]+)\)", text)
    return {
        "id": folder.name,
        "title": title,
        "summary": summary,
        "commands": commands,
        "notes": " ".join(notes.split()),
        "came": " ".join(came.split()),
        "checked": f"{checked.group(1)} {checked.group(2)}" if checked else "",
        "card": card.group(1) if card else "",
    }


HEAD = (
    '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n"
)


def lay(src: str, out: str, data, whole: bool = False) -> None:
    """whole: a page of its own, with its own doctype (table.html, which the
    front page links to); the front page stays a fragment the host wraps."""
    text = (HERE / src).read_text()
    assert text.count(MARK) == 1, f"{src}: needs one {MARK}"
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (HERE / out).write_text((HEAD if whole else "") + text.replace(MARK, blob))


def main() -> None:
    games = [game(p.parent) for p in sorted((GAME / "games").glob("*/README.md"))]
    worlds = [json.loads(p.read_text()) for p in sorted((GAME / "box" / "worlds").glob("*.json"))]
    lay("index.src.html", "index.html", {"games": games, "worlds": [w["title"] for w in worlds]})
    lay("table.src.html", "table.html", worlds, whole=True)
    print(f"index.html: {len(games)} games; table.html: {len(worlds)} worlds")


if __name__ == "__main__":
    main()
