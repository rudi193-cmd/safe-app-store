"""session.py: a session at the table played by code, as far as it goes without the person. Python 3.9+.

    python apps/game/box/session.py --table DIR [--world NAME] [--now TS]
    python apps/game/box/session.py --table DIR [--world NAME] offer CHARACTER "FACT" [--as KIND]
    python apps/game/box/session.py --table DIR canon
    python apps/game/box/session.py --table DIR recap
    python apps/game/box/session.py --table DIR export-canon [--to FILE]

The game master's bookkeeping, done by code: every action beat is rolled for
the character whose turn it is, leaning into the approach the beat suggests,
and every decision is handed in for the seal. Then it stops. Only whoever
holds the key moves a decision, with the kernel's own `seal` or `decline`;
run this again after and it settles their answer and plays on to the next.
A story played to its end prints what the table made true: each ruling,
sealed or declined, and the line each roll gave.

A roll can turn the story: a beat with a `when` is played only if the beat
it names came out its way, so a missed riddle leads somewhere a solved one
doesn't. The rulings put to the person are the ones the story reached.

`offer` is a player bringing something to the table on the night, as their
character: "a guest walks in". It is handed in for the seal, and the story
goes on while it waits. Once the GM seals or declines it, the next run
writes their answer down before it plays on, and a sealed offer is canon.

`canon` is the table's memory: every ruling sealed on this record whose seal
still holds, in the order they were sealed, and every one declined. It reads
only seals, never the worlds, so what it says is what the person made true.

`recap` is "previously on...", for the start of the next session. Its first
part is to read aloud: only what the table made true, the sealed canon,
last session's first (a session ends where its session seal says), so
nothing the table hasn't heard is said. Its second part is for the GM's
eyes: the notes of the latest night, typed or scanned, each line cited, the
promises made for next time, and what was said no to.

`export-canon` is the play growing the world: every fact the GM sealed,
as markdown, each with its seal (the proposal's hash and row) and where in
play it came from, for story-timeline's `import-canon` to put on the
writer's timeline. Only what was sealed goes; a declined ruling stays here.

NAME is a world in DIR/worlds (lantern-fair unless said). The story is
opened if it isn't yet. This never seals, declines or reads the key, and
writes only through game-master, which writes through dice and the kernel.

Exit codes, the kernel's: 0 the story is played to its end; 42 a decision
waits on the seal; 2 refused.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import willow_pin

ROOT = (
    willow_pin.root()
)  # willow, where its pieces live, held to apps/game/willow.pin.json
GM_DIR = ROOT / "adapters" / "stdlib" / "game-master"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(GM_DIR))
import game_master as gm
import kernel

GM = GM_DIR / "game_master.py"


def fail(why: str) -> int:
    print(f"refused: {why}", file=sys.stderr)
    return kernel.REFUSED


def step(
    box: Path, world_file: Path, now: str, *argv: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GM), "--box", str(box), *argv, "--world", str(world_file), "--now", now],
        capture_output=True, text=True, check=False,
    )  # fmt: skip


def recap(world: dict, game: dict) -> list[str]:
    """What the table made true, beat by beat: each roll's line, each ruling."""
    beats = {(sc["id"], b["id"]): b for sc, b in gm.flat(world)}
    out = []
    for row in game["beats"]:
        b = beats[(row["scene"], row["beat"])]
        if row["beat_kind"] == "action":
            out.append(
                f"  {row['scene']}::{row['beat']}  {row['band']:<6} {b['outcomes'][row['band']]}"
            )
        else:
            fact = b["proposes"]["fact"]
            out.append(f"  {row['scene']}::{row['beat']}  {row['verdict']:<6} {fact}")
    return out


def answers(
    box: Path, rows: list[dict], worlds: Path
) -> list[tuple[int, str, str, str]]:
    """Every ruling and offer the GM has answered, as (the answer's row,
    sealed or declined, the fact as handed in, which story), in row order."""
    titles = {}
    for f in sorted(worlds.glob("*.json")):
        try:
            w = gm.load_world(f)
        except gm.WorldError:
            continue
        titles[w["id"]] = w["title"]
    out = []
    for g in gm.games(rows):
        where = titles.get(g["open"].get("world"), g["open"].get("world"))
        said = [(a, a["fact"]) for a in g["asks"]]
        said += [(o, f"{o['fact']}  [offered by {o['by']}]") for o in g["offers"]]
        for a, fact in said:
            what, got = gm.ruling(box, rows, a["subject"])
            if what in ("sealed", "declined"):
                out.append((got["n"], what, fact, where))
    return sorted(out)


def sealed_canon(box: Path, rows: list[dict]) -> list[dict]:
    """Every fact the GM sealed on this record, with where it came from:
    {fact, subject, row, from}, in the order they were sealed."""
    out = []
    for g in gm.games(rows):
        story = g["open"].get("world")
        said = [(a, f"{story}::{a['scene']}::{a['beat']}") for a in g["asks"]]
        said += [(o, f"{story}, offered by {o['by']}" + (f" as a {o['as']}" if o.get("as") else "")) for o in g["offers"]]  # fmt: skip
        for a, where in said:
            what, got = gm.ruling(box, rows, a["subject"])
            if what == "sealed":
                out.append(
                    {
                        "fact": a["fact"],
                        "subject": a["subject"],
                        "row": got["n"],
                        "from": where,
                    }
                )
    return sorted(out, key=lambda f: f["row"])


def export_canon(box: Path, to: str) -> int:
    rows, breaks = kernel.read(box / "record.jsonl")
    if breaks:
        return fail("the record doesn't verify: " + "; ".join(breaks))
    facts = sealed_canon(box, rows)
    if not facts:
        print("nothing sealed yet: no canon to export")
        return kernel.ESCALATE
    lines = [f"<!-- canon from a game box: record {rows[0]['hash']}, {len(rows)} rows -->",
             "# What the table made true", ""]  # fmt: skip
    for f in facts:
        lines += [
            f"- {f['fact']}",
            f"  sealed: {f['subject']} | row {f['row']} | {f['from']}",
        ]
    text = "\n".join(lines) + "\n"
    if not to:
        print(text, end="")
        return kernel.ALIVE
    out = Path(to)
    if out.exists():
        return fail(f"{out} is there; canon is never written over")
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}: {len(facts)} sealed fact{'s' if len(facts) != 1 else ''}")
    return kernel.ALIVE


def canon(box: Path, worlds: Path) -> int:
    rows, breaks = kernel.read(box / "record.jsonl")
    if breaks:
        return fail("the record doesn't verify: " + "; ".join(breaks))
    said = answers(box, rows, worlds)
    true = [(n, f"  {fact}   ({where}, sealed at row {n})") for n, what, fact, where in said if what == "sealed"]  # fmt: skip
    no = [(n, f"  not: {fact}   ({where}, declined at row {n})") for n, what, fact, where in said if what == "declined"]  # fmt: skip
    if not true and not no:
        print("nothing is canon at this table yet: nothing has been sealed")
        return kernel.ESCALATE
    print("what this table holds true:")
    print("\n".join(line for _, line in sorted(true)) or "  nothing sealed yet")
    if no:
        print("what it said no to:")
        print("\n".join(line for _, line in sorted(no)))
    return kernel.ALIVE


DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def last_notes(pile: Path) -> tuple[str, list[tuple[str, int, str]]]:
    """(the latest date a notes file is named for, its lines as (path, line,
    text)): typed and scanned alike, every file named by that date."""
    dated = sorted((m.group(1), p) for p in pile.rglob("*") if p.is_file() and (m := DATED.match(p.name)))  # fmt: skip
    if not dated:
        return "", []
    day = dated[-1][0]
    lines = []
    for d, p in dated:
        if d == day:
            rel = p.relative_to(pile).as_posix()
            for i, text in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):  # fmt: skip
                if text.strip() and not text.lstrip().startswith("#"):
                    lines.append((rel, i, text.strip()))
    return day, lines


def promised(pile: Path) -> list[tuple[str, int, str]]:
    """Every line of the GM's notes that says next time, oldest file first."""
    out = []
    for p in sorted(pile.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".txt"):
            for i, text in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):  # fmt: skip
                if "next time" in text.lower():
                    out.append((p.relative_to(pile).as_posix(), i, text.strip()))
    return out


def previously(box: Path, table: Path) -> int:
    rows, breaks = kernel.read(box / "record.jsonl")
    if breaks:
        return fail("the record doesn't verify: " + "; ".join(breaks))
    said = answers(box, rows, table / "worlds")
    true = [(n, fact) for n, what, fact, _ in said if what == "sealed"]
    ended = [r for r in rows if r["kind"] == "session"]
    print("# Previously on...\n")
    print("## Read aloud: what the table made true\n")
    if not true:
        print("  Nothing yet: the table hasn't made anything true.")
    elif not ended:
        print("So far:")
        print("\n".join(f"  - {fact}" for _, fact in true))
    else:
        lo, hi = ended[-1]["from"], ended[-1]["to"]
        parts = (("Last time:", [f for n, f in true if lo <= n <= hi]),
                 ("Before that:", [f for n, f in true if n < lo]),
                 ("This time, so far:", [f for n, f in true if n > hi]))  # fmt: skip
        for head, facts in parts:
            if facts:
                print(head)
                print("\n".join(f"  - {f}" for f in facts))
    print("\n## For the GM's eyes\n")
    day, lines = last_notes(table / "pile")
    if lines:
        w = max(len(f"{p}:{i}") for p, i, _ in lines)
        print(f"Your notes from {day}:")
        print("\n".join(f"  {f'{p}:{i}':<{w}}  {t}" for p, i, t in lines))
    promises = promised(table / "pile")
    if promises:
        w = max(len(f"{p}:{i}") for p, i, _ in promises)
        print("Promised for next time:")
        print("\n".join(f"  {f'{p}:{i}':<{w}}  {t}" for p, i, t in promises))
    no = [fact for n, what, fact, _ in said if what == "declined"]
    if no:
        print("Said no to:")
        print("\n".join(f"  - {f}" for f in no))
    return kernel.ALIVE if true or lines else kernel.ESCALATE


def answered(box: Path, rows: list[dict], game: dict) -> bool:
    """Whether the GM has sealed or declined an offer not yet written down."""
    return any(gm.ruling(box, rows, o["subject"])[0] in ("sealed", "declined") for o in gm.unheard(game))  # fmt: skip


def offer(box: Path, world_file: Path, now: str, who: str, fact: str, kind: str = "") -> int:  # fmt: skip
    done = step(
        box, world_file, now, "offer", who, fact, *(["--as", kind] if kind else [])
    )
    print((done.stdout or done.stderr).rstrip(), file=sys.stdout if done.stdout else sys.stderr)  # fmt: skip
    return done.returncode


def play(box: Path, world_file: Path, now: str) -> int:
    try:
        world = gm.load_world(world_file)
    except gm.WorldError as e:
        return fail(str(e))
    rows, game, err = gm.current(box, world)
    if err and "open first" in err:
        opened = step(box, world_file, now, "open")
        if opened.returncode == kernel.REFUSED:
            return fail(opened.stderr.strip())
        print(opened.stdout.rstrip())
        rows, game, err = gm.current(box, world)
    if err:
        return fail(err)
    if answered(box, rows, game):  # the GM answered an offer: write it down first
        heard = step(box, world_file, now, "settle")
        if heard.returncode == kernel.REFUSED:
            return fail(heard.stderr.strip())
        print(heard.stdout.rstrip())
        rows, game, err = gm.current(box, world)
    while not gm.finished(game, world):
        sc, b, _ = gm.now_in(world, game)
        if b["kind"] == "action":
            done = step(box, world_file, now, "act", b["suggests"])
        else:
            asked = [
                a
                for a in game["asks"]
                if (a["scene"], a["beat"]) == (sc["id"], b["id"])
            ]
            done = step(box, world_file, now, "settle" if asked else "ask")
        if done.returncode == kernel.REFUSED:
            return fail(f"{sc['id']}::{b['id']}: {done.stderr.strip()}")
        print(done.stdout.rstrip())
        if done.returncode == kernel.ESCALATE:
            return kernel.ESCALATE
        rows, game, err = gm.current(box, world)
        if err:
            return fail(err)
    print(f"\n{world['title']}, played to its end: {gm.tally(game)}")
    print("\n".join(recap(world, game)))
    return kernel.ALIVE


def main(argv: list[str]) -> int:
    opts, args, it = {}, [], iter(argv)
    for a in it:
        if a in ("--table", "--world", "--now", "--as", "--to"):
            opts[a] = next(it, "")
        else:
            args.append(a)
    if not opts.get("--table") or not (
        args in ([], ["canon"], ["recap"], ["export-canon"])
        or (len(args) == 3 and args[0] == "offer")
    ):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return kernel.REFUSED
    table = Path(opts["--table"])
    box = table / "record"
    world_file = table / "worlds" / f"{opts.get('--world') or 'lantern-fair'}.json"
    if not (box / "kernel.json").exists():
        return fail(f"{table} isn't a table laid by open_table.py")
    if args == ["recap"]:
        return previously(box, table)
    if args == ["export-canon"]:
        return export_canon(box, opts.get("--to", ""))
    if args == ["canon"]:
        return canon(box, table / "worlds")
    if not world_file.exists():
        return fail(f"no world {world_file.stem!r} in {world_file.parent}")
    if args:
        return offer(box, world_file, opts.get("--now") or kernel.now(), args[1], args[2], opts.get("--as", ""))  # fmt: skip
    return play(box, world_file, opts.get("--now") or kernel.now())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
