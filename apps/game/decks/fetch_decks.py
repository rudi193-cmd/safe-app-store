"""fetch_decks.py: fetch Die-Namic's card art from where it lives. Python 3.9+.

    python apps/game/decks/fetch_decks.py              (every deck below)
    python apps/game/decks/fetch_decks.py knoll rws1910
    python apps/game/decks/fetch_decks.py --list

The art is never committed. This fetches it into apps/game/ui/decks/ (which
git ignores), one folder a deck, each with a deck.json saying what it holds
and where it came from, and writes ui/decks/NOTICE.md for all of them.
ui/build.py reads the deck.json files and offers each deck on the card pages;
with none fetched, the pages draw their own cards as before.

Every deck here is public domain or CC0, chosen so Die-Namic stays
Apache-2.0 compatible (README.md beside this says why each one is). A deck
that isn't free to share never goes in this list.

Cards are named the way the record writes them: rank 2-9, T, J, Q, K, A, then
suit C, D, H, S (QS.svg, TH.svg); backs back-NAME.svg. Tarot cards are
major-00 .. major-21, then wands-01 .. wands-14 (and cups, swords, pentacles),
ace 01 to king 14, as play-tarot deals them.

It is resumable: a card already on disk is not fetched again. Wikimedia
asks for an honest client name and a gentle pace, so its files are asked for
in batches through its API and downloaded a few seconds apart.

Exit codes: 0 every card fetched; 1 some cards could not be fetched (run it
again); 2 refused (a deck name this doesn't know).
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "ui" / "decks"
UA = "die-namic-decks/0.1 (fetches public-domain card art for a local game table)"

RANKS = "23456789TJQKA"
SUITS = "CDHS"
STANDARD = [r + s for s in SUITS for r in RANKS]
TAROT_SUITS = ("wands", "cups", "swords", "pentacles")

DECKS = {
    "knoll": {
        "name": "Vector Playing Cards",
        "kind": "standard",
        "credit": "Byron Knoll; kept by notpeter",
        "license": "Public domain (or, optionally, WTFPL)",
        "source": "https://github.com/notpeter/Vector-Playing-Cards",
    },
    "tekeye": {
        "name": "Tek Eye",
        "kind": "standard",
        "credit": "Tek Eye",
        "license": "Public domain",
        "source": "https://tekeye.uk/playing_cards/svg-playing-cards",
    },
    "kennard-goodall": {
        "name": "Kennard, old style",
        "kind": "standard",
        "credit": "Adrian Kennard, after Goodall & Son",
        "license": "CC0 1.0",
        "source": "https://www.me.uk/cards/",
        "query": "view&pip=0&back=Goodall&ace=Goodall&noleft=on&noflip=on",
    },
    "kennard-fourcolour": {
        "name": "Kennard, four colour",
        "kind": "standard",
        "credit": "Adrian Kennard",
        "license": "CC0 1.0",
        "source": "https://www.me.uk/cards/",
        "query": "view&fourcolour=on",
    },
    "rws1910": {
        "name": "Smith tarot, 1910",
        "kind": "tarot",
        "credit": "Pamela Colman Smith (1909-1910); the 1910 'Pamela-A' scans on Wikimedia Commons",
        "license": "Public domain (published 1909-1910; the artist died in 1951)",
        "source": "https://commons.wikimedia.org/wiki/Category:Rider-Waite_tarot_deck",
        "width": 360,
    },
}

failed: list[str] = []


def get(url: str, pause: float = 0.0) -> bytes:
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            time.sleep(pause)
            return data
        except Exception as e:  # noqa: BLE001 - every failure is retried, then reported
            wait = 20 * (i + 1) if "429" in str(e) else 3 * (i + 1)
            print(f"  retry in {wait}s: {url[:90]} ({e})", file=sys.stderr)
            time.sleep(wait)
    raise OSError(f"could not fetch {url}")


def keep(folder: Path, name: str, fetch) -> bool:
    """Write one card unless it's there already; a failure is noted, not fatal."""
    path = folder / name
    if path.exists() and path.stat().st_size:
        return True
    try:
        path.write_bytes(fetch())
        return True
    except OSError as e:
        failed.append(f"{folder.name}/{name}: {e}")
        return False


# ── one function a source ────────────────────────────────────────────────────
def knoll(folder: Path, deck: dict) -> dict:
    base = "https://raw.githubusercontent.com/notpeter/Vector-Playing-Cards/master/cards-svg/"
    for c in STANDARD:
        keep(folder, f"{c}.svg", lambda c=c: get(base + c.replace("T", "10") + ".svg"))
    return {"ext": "svg", "backs": []}


def tekeye(folder: Path, deck: dict) -> dict:
    base = "https://tekeye.uk/playing_cards/images/svg_playing_cards/"
    rank = {"A": "ace", "T": "10", "J": "jack", "Q": "queen", "K": "king"}
    suit = {"C": "clubs", "D": "diamonds", "H": "hearts", "S": "spades"}
    for c in STANDARD:
        keep(folder, f"{c}.svg", lambda c=c: get(f"{base}fronts/{suit[c[1]]}_{rank.get(c[0], c[0])}.svg"))
    page = get(deck["source"]).decode("utf-8", "replace")
    backs = sorted(set(re.findall(r"backs/([a-z0-9_]+)\.svg", page)))
    for b in backs:
        keep(folder, f"back-{b}.svg", lambda b=b: get(f"{base}backs/{b}.svg"))
    return {"ext": "svg", "backs": backs}


def kennard(folder: Path, deck: dict) -> dict:
    """His generator shows a whole deck as inline SVGs, one a card, each
    with face="QS" (T for ten, 1B and 2B the backs): each is cut out whole."""
    page = get(f"https://www.me.uk/cards/makeadeck.cgi?{deck['query']}").decode("utf-8", "replace")
    cards = {m.group(1): m.group(0) for m in re.finditer(r'<svg[^>]*face="([^"]+)".*?</svg>', page, re.S)}
    for c in STANDARD:
        if c in cards:
            keep(folder, f"{c}.svg", lambda c=c: cards[c].encode())
        else:
            failed.append(f"{folder.name}/{c}.svg: not in the generator's page")
    backs = []
    for code, b in (("1B", "one"), ("2B", "two")):
        if code in cards and keep(folder, f"back-{b}.svg", lambda code=code: cards[code].encode()):
            backs.append(b)
    return {"ext": "svg", "backs": backs}


def tarot_name(file: str) -> str | None:
    """'RWS_Tarot_1910_-_00_The_Fool.png' -> major-00; '..._Cups_13_(Queen).png' -> cups-13."""
    m = re.match(r"RWS_Tarot_1910_-_(\d\d)_", file)
    if m:
        return f"major-{m.group(1)}"
    m = re.match(r"RWS_Tarot_1910_-_(Wands|Cups|Swords|Pentacles)_(\d\d)", file)
    return f"{m.group(1).lower()}-{m.group(2)}" if m else None


def rws1910(folder: Path, deck: dict) -> dict:
    api = "https://commons.wikimedia.org/w/api.php?"
    listing = json.loads(get(api + urllib.parse.urlencode({"action": "query", "list": "allimages", "aiprefix": "RWS_Tarot_1910_-_", "ailimit": "100", "format": "json"}), 2))
    files = {tarot_name(i["name"]): i["name"] for i in listing["query"]["allimages"]}
    files.pop(None, None)
    if len(files) != 78:
        failed.append(f"rws1910: Commons lists {len(files)} cards, not 78")
    todo = {k: v for k, v in files.items() if not (folder / f"{k}.jpg").exists()}
    urls: dict = {}
    names = sorted(todo.values())
    for i in range(0, len(names), 40):  # the API answers up to 50 titles at once
        q = {"action": "query", "titles": "|".join("File:" + n for n in names[i : i + 40]), "prop": "imageinfo", "iiprop": "url", "iiurlwidth": str(deck["width"]), "format": "json"}
        info = json.loads(get(api + urllib.parse.urlencode(q), 3))
        norm = {x["to"]: x["from"] for x in info["query"].get("normalized", [])}
        for p in info["query"]["pages"].values():
            if "imageinfo" in p:
                urls[norm.get(p["title"], p["title"])[len("File:"):]] = p["imageinfo"][0]["thumburl"]
    for key, file in sorted(todo.items()):
        if file.replace(" ", "_") in urls or file in urls:
            url = urls.get(file) or urls.get(file.replace(" ", "_"))
            keep(folder, f"{key}.jpg", lambda url=url: get(url, 5))
        else:
            failed.append(f"rws1910/{key}: no URL from Commons")
    return {"ext": "jpg", "backs": [], "sources": {k: "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(v) for k, v in sorted(files.items())}}


FETCH = {"knoll": knoll, "tekeye": tekeye, "kennard-goodall": kennard, "kennard-fourcolour": kennard, "rws1910": rws1910}


def notice() -> None:
    lines = ["# The card art in this folder", "",
             "Fetched by apps/game/decks/fetch_decks.py; never committed. Every deck is public domain or CC0.", ""]
    for p in sorted(OUT.glob("*/deck.json")):
        d = json.loads(p.read_text())
        lines += [f"## {d['name']} ({d['id']})", "", f"- By: {d['credit']}", f"- Licence: {d['license']}", f"- From: {d['source']}"]
        if d.get("sources"):
            lines.append(f"- Each card's own page: listed in {d['id']}/deck.json")
        lines.append("")
    (OUT / "NOTICE.md").write_text("\n".join(lines))


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for k, d in DECKS.items():
            print(f"{k:20} {d['kind']:9} {d['license']}  ({d['source']})")
        return 0
    want = argv or list(DECKS)
    unknown = [w for w in want if w not in DECKS]
    if unknown:
        print(f"refused: no deck named {', '.join(unknown)}; --list names them", file=sys.stderr)
        return 2
    for key in want:
        deck = DECKS[key]
        folder = OUT / key
        folder.mkdir(parents=True, exist_ok=True)
        print(f"{key}: fetching into {folder.relative_to(HERE.parents[2])}")
        held = FETCH[key](folder, deck)
        cards = sorted(p.stem for p in folder.iterdir() if p.suffix in (".svg", ".jpg") and not p.stem.startswith("back-"))
        meta = {"id": key, **{k: v for k, v in deck.items() if k not in ("query", "width")}, **held, "cards": len(cards)}
        (folder / "deck.json").write_text(json.dumps(meta, indent=1) + "\n")
        print(f"{key}: {len(cards)} cards, {len(held['backs'])} backs")
    notice()
    if failed:
        print(f"{len(failed)} not fetched; run it again to pick them up:", file=sys.stderr)
        for f in failed[:20]:
            print("  " + f, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
