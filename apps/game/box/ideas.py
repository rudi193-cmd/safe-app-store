"""ideas.py: story ideas between sessions, made from what's in the box. Python 3.9+.

    python apps/game/box/ideas.py --table DIR [--seed TEXT] [--count N]

For the GM's eyes, between sessions. Nothing here is canon and nothing is
handed in: an idea the GM likes, they write in their binder or into a story.

Four parts, all from the box itself:

- **Seeds.** A grammar built from the box's own words: the characters and
  places of its stories, the monsters and people of the binder, the threads
  promised for next time, and what the table made true. The oracle-text
  add-on deals readings from it with willow's seeded stream, so a seed (the
  day, unless given) and a number always deal the same idea again.
- **Set up, never played.** A monster or person with a page in the binder
  whose name no session's notes, typed or scanned, has said yet.
- **Still open.** Every promise made for next time.
- **Something you wrote and forgot.** One passage of the binder drawn by the
  surprise add-on, replayable from its seed (a `surprise` row on the record).

Exit codes, the kernel's: 0 done; 2 refused.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import willow_pin

ROOT = (
    willow_pin.root()
)  # willow, where its pieces live, held to apps/game/willow.pin.json
STDLIB = ROOT / "adapters" / "stdlib"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(STDLIB / "game-master"))
import game_master as gm
import kernel
import session

ORACLE = STDLIB / "oracle-text" / "oracle_text.py"
SURPRISE = STDLIB / "surprise" / "surprise.py"
NOTES = ("sessions", "scanned")


def fail(why: str) -> int:
    print(f"refused: {why}", file=sys.stderr)
    return kernel.REFUSED


def titled(folder: Path) -> list[str]:
    """Each page's first heading: the name it was written under."""
    out = []
    for p in sorted(folder.glob("*.md")):
        head = next((ln[2:].strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("# ")), "")  # fmt: skip
        if head:
            out.append(head)
    return out


def said_in_notes(pile: Path) -> str:
    """Every word the session notes, typed and scanned, have said, lower case."""
    text = []
    for name in NOTES:
        for p in sorted((pile / name).glob("*")) if (pile / name).is_dir() else []:
            text.append(p.read_text(encoding="utf-8", errors="replace").lower())
    return "\n".join(text)


def unplayed(pile: Path) -> list[str]:
    """The binder's monsters and people no session's notes have named yet."""
    said = said_in_notes(pile)
    out = []
    for folder in ("monsters", "people"):
        for name in titled(pile / folder):
            words = [
                w
                for w in re.findall(r"[a-z']+", name.lower())
                if w not in ("the", "a", "an")
            ]
            if words and not all(
                re.search(rf"\b{re.escape(w)}\b", said) for w in words
            ):
                out.append(f"{name}  ({folder}/)")
    return out


def lower_first(text: str) -> str:
    return (
        text[:1].lower() + text[1:]
        if text[:1].isupper() and not text[1:2].isupper()
        else text
    )


def story(table: Path, rows: list[dict]) -> list[dict]:
    """The story last played on this record, the one ideas are for: its
    world, or every world in the box when none has been opened yet."""
    worlds = {}
    for f in sorted((table / "worlds").glob("*.json")):
        try:
            w = gm.load_world(f)
        except gm.WorldError:
            continue
        worlds[w["id"]] = w
    played = [
        g["open"].get("world") for g in gm.games(rows) if g["beats"] or g["offers"]
    ]
    return (
        [worlds[played[-1]]]
        if played and played[-1] in worlds
        else list(worlds.values())
    )


def grammar(table: Path, rows: list[dict]) -> dict:
    """A Tracery grammar of the box's own words."""
    who, npc, places = [], [], []
    for w in story(table, rows):
        for c in w["characters"]:
            (who if c["seat"] else npc).append(c["name"])
        places += [p["name"] for p in w["places"]]
    pile = table / "pile"
    npc += [n for n in titled(pile / "people") if n not in npc]
    npc = [
        ("the " + n[4:]) if n.startswith("The ") else n for n in npc
    ]  # a name said mid-sentence
    monsters = [f"the {n.lower()}" for n in titled(pile / "monsters")]
    threads = []
    for _, _, line in session.promised(pile):
        m = re.search(r"next time:?\s*(.+)", line, re.IGNORECASE)
        if m and len(m.group(1).split()) > 2:
            threads.append(m.group(1).rstrip(".!?"))
    canon = [lower_first(fact.split("  [offered by")[0].split(":")[0].rstrip("."))
             for _, what, fact, _ in session.answers(table / "record", rows, table / "worlds") if what == "sealed"]  # fmt: skip
    g = {"who": sorted(set(who)), "npc": sorted(set(npc)), "place": sorted({p.lower() for p in places}),
         "monster": monsters, "thread": threads, "canon": canon}  # fmt: skip
    g = {k: v for k, v in g.items() if v}
    origin = []
    if {"who", "thread"} <= g.keys():
        origin.append("What if #who# finds out #thread#, and doesn't tell the others?")
    if {"monster", "place", "who"} <= g.keys():
        origin.append("At #place#, #who# comes face to face with #monster#.")
    if {"npc", "who", "thread"} <= g.keys():
        origin.append("#npc.capitalize# asks #who# for help with #thread#.")
    if {"canon", "npc"} <= g.keys():
        origin.append("Because #canon#, #npc# owes someone at the table a favour.")
    if {"canon", "monster"} <= g.keys():
        origin.append("Now that #canon#, #monster# has nowhere to go.")
    if {"who", "npc"} <= g.keys():
        origin.append(
            "#who.capitalize# and #npc# want the same thing, for different reasons."
        )
    g["origin"] = origin
    return g


def main(argv: list[str]) -> int:
    opts, args, it = {}, [], iter(argv)
    for a in it:
        if a in ("--table", "--seed", "--count"):
            opts[a] = next(it, "")
        else:
            args.append(a)
    if not opts.get("--table") or args:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return kernel.REFUSED
    table = Path(opts["--table"])
    box = table / "record"
    if not (box / "kernel.json").exists():
        return fail(f"{table} isn't a box laid by open_table.py")
    try:
        count = int(opts.get("--count", "5"))
    except ValueError:
        return fail("--count is a number")
    rows, breaks = kernel.read(box / "record.jsonl")
    if breaks:
        return fail("the record doesn't verify: " + "; ".join(breaks))
    seed = (
        opts.get("--seed")
        or f"ideas {datetime.datetime.now(datetime.timezone.utc).date().isoformat()}"
    )
    g = grammar(table, rows)
    print("# Ideas, for the GM's eyes\n")
    if g["origin"]:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "grammar.json"
            f.write_text(json.dumps(g), encoding="utf-8")
            got = subprocess.run([sys.executable, str(ORACLE), "--seed", seed, "--grammar", str(f), "--count", str(count)],
                                 capture_output=True, text=True, check=False)  # fmt: skip
        if got.returncode != kernel.ALIVE:
            return fail(f"oracle-text: {got.stderr.strip()}")
        print(f"## Seeds (seed {seed!r}: the same seed deals them again)\n")
        print("\n".join(f"  - {ln}" for ln in got.stdout.splitlines() if ln.strip()))
    else:
        print("## Seeds\n\n  The box has too little in it yet to deal from.")
    gone = unplayed(table / "pile")
    print("\n## Set up, never played\n")
    print(
        "\n".join(f"  - {x}" for x in gone)
        or "  Everything the binder sets up has come out at the table."
    )
    promises = session.promised(table / "pile")
    print("\n## Still open\n")
    print(
        "\n".join(f"  {p}:{i}  {t}" for p, i, t in promises)
        or "  No promises made for next time."
    )
    got = subprocess.run([sys.executable, str(SURPRISE), "--box", str(box)], capture_output=True, text=True, check=False)  # fmt: skip
    print("\n## Something you wrote and forgot\n")
    print(
        "\n".join(f"  {ln}" for ln in got.stdout.rstrip().splitlines())
        or "  (nothing long enough to draw)"
    )
    return kernel.ALIVE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
