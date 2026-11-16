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


# The games played on a page of their own, in the table frame every one of
# them shares (tables/frame.src.html), each with its rules in tables/GAME.js.
# Their lids' colours match the front page's. deckKind: the card art it
# offers, if any; also: other games on the shelf this page plays (the dice
# tray rolls both dice's notation and dice5e's).
PAGES = {
    "play-hearts": {"name": "Hearts", "lid": "#b8263f", "ink": "#fff0f2", "deckKind": "standard"},
    "play-crazy-eights": {"name": "Crazy Eights", "lid": "#d9662a", "ink": "#fff4ea", "deckKind": "standard"},
    "play-tarot": {"name": "Tarot", "lid": "#0f3d3a", "ink": "#f1d9a0", "deckKind": "tarot"},
    "play-dice": {"name": "Dice", "lid": "#2a9d8f", "ink": "#f0fffc", "also": ["play-dice5e"]},
    "play-liars-dice": {"name": "Liar's Dice", "lid": "#2f2f2f", "ink": "#ffd34d"},
}


def decks() -> list[dict]:
    """The card art fetched into ui/decks/ (decks/fetch_decks.py), as the
    pages offer it: what each deck is, whose it is, and its backs. None
    fetched, none offered, and the pages draw their own cards."""
    out = []
    for p in sorted((HERE / "decks").glob("*/deck.json")):
        d = json.loads(p.read_text())
        out.append({k: d[k] for k in ("id", "name", "kind", "credit", "license", "ext", "backs", "cards")})
    # in the order fetch_decks.py lists them, the first offered first
    order = re.findall(r'^    "([a-z0-9-]+)": \{$', (GAME / "decks" / "fetch_decks.py").read_text(), re.M)
    return sorted(out, key=lambda d: order.index(d["id"]) if d["id"] in order else len(order))


def table_page(g: dict, lid: dict, also: list) -> None:
    frame = (HERE / "tables" / "frame.src.html").read_text()
    script = (HERE / "tables" / f"{g['id']}.js").read_text()
    for mark in ("/*__TITLE__*/", "/*__GAME_SCRIPT__*/"):
        assert frame.count(mark) == 1, f"frame: needs one {mark}"
    assert "</script" not in script, f"{g['id']}.js: no </script inside"
    kind = lid.get("deckKind")
    data = {**g, **lid, "also": also, "decks": [d for d in decks() if d["kind"] == kind] if kind else []}
    text = frame.replace("/*__TITLE__*/", f"{lid['name']} · Die-Namic").replace("/*__GAME_SCRIPT__*/", script)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    assert text.count(MARK) == 1
    (HERE / f"{g['id']}.html").write_text(HEAD + text.replace(MARK, blob))


def main() -> None:
    games = [game(p.parent) for p in sorted((GAME / "games").glob("*/README.md"))]
    worlds = [json.loads(p.read_text()) for p in sorted((GAME / "box" / "worlds").glob("*.json"))]
    by_id = {g["id"]: g for g in games}
    for gid, lid in PAGES.items():
        table_page(by_id[gid], lid, [by_id[a] for a in lid.get("also", [])])
    # each game on the shelf that has a page, and the page that plays it
    pages = {gid: gid for gid in PAGES} | {a: gid for gid, lid in PAGES.items() for a in lid.get("also", [])}
    data = {"games": games, "worlds": [w["title"] for w in worlds], "pages": pages}
    lay("index.src.html", "index.html", data)
    lay("table.src.html", "table.html", worlds, whole=True)
    print(f"index.html: {len(games)} games; table.html: {len(worlds)} worlds; "
          f"pages: {', '.join(f'{g}.html' for g in PAGES)}")


if __name__ == "__main__":
    main()
