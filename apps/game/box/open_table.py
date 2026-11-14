"""open_table.py: a game master's box, laid with nothing sealed. Python 3.9+.

    python apps/game/box/open_table.py open  --table DIR --key FILE [--now TS]
    python apps/game/box/open_table.py prep  --table DIR
    python apps/game/box/open_table.py end   --table DIR
    python apps/game/box/open_table.py check --table DIR

The box is the game master's binder. `open` lays a fresh one in DIR, which
must not exist yet:

- DIR/pile is the binder: the GM's notes, monsters, people, session notes
  and house rules. It is what the record reads, and what the GM asks.
- DIR/words.txt is the GM's words list, `stats = grit, wit, ...`, the way
  they ask put into the words their binder uses. The kernel reads every
  question through it. It is kept outside the pile, owner-only.
- DIR/worlds holds the stories, kept outside the pile so that what the
  record serves is the binder, and what the table made true is sealed.
- DIR/record is the kernel record over the pile: rolls, rulings, seals.

The kernel makes the key at FILE, for the game master; FILE must not be
inside DIR, so the key is never part of what the record reads. Then each
house rule is handed in for the seal (the rules add-on) and the story is
opened (game-master), and it stops: everything it proposed waits on the
person who holds the key.

`prep` runs the GM's prep sheet, gm-stack.md, through the stack add-on:
thirteen steps over the binder, the threads, what is owed the table, the
dice and whether the record holds. Each run is kept in DIR/prep/NNN, so a
step that writes a file writes it there, and last week's is never in the
way. `end` closes the night with gm-end.md: photos of the GM's handwritten pages,
put in DIR/scans, read by the ocr add-on (tesseract) into DIR/pile/scanned;
then what changed in the binder, the threads and promises with tonight's
page in them, what still waits, the night in plain sentences, one session
seal handed in over it all, a checked backup and a pin of where the record
ends, each run kept in DIR/end/NNN; and last, what the table holds true.

`check` runs the table's own check page,
check.md: every game on the record played again from its first row. Each
then has the kernel verify the chain.

This never seals, declines or reads the key, and writes the record only
through the kernel and the add-ons.

Exit codes, the kernel's: 0 done; 42 something waits on the seal, or a page
flagged a step; 2 refused.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import willow_pin

ROOT = (
    willow_pin.root()
)  # willow, where its pieces live, held to apps/game/willow.pin.json
sys.path.insert(0, str(ROOT))
import kernel

BINDER = HERE / "binder"
WORDS = HERE / "gm-words.txt"
WORLDS = HERE / "worlds"
PAGES = {"prep": HERE / "gm-stack.md", "end": HERE / "gm-end.md", "check": HERE / "check.md"}  # fmt: skip
SESSION = HERE / "session.py"
STDLIB = ROOT / "adapters" / "stdlib"
RULES = STDLIB / "rules" / "rules.py"
GM = STDLIB / "game-master" / "game_master.py"
STACK = STDLIB / "stack" / "stack.py"
WORLD = "lantern-fair.json"


def run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *argv], capture_output=True, text=True, check=False
    )


def fail(why: str) -> int:
    print(f"refused: {why}", file=sys.stderr)
    return kernel.REFUSED


def inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def cmd_open(table: Path, key: Path, now: str) -> int:
    if table.exists():
        return fail(f"{table} is already there: a box is laid fresh, in a folder of its own")  # fmt: skip
    if inside(key, table):
        return fail("the key goes outside the box, so the record never reads it")
    pile, box, words = table / "pile", table / "record", table / "words.txt"
    table.mkdir(parents=True)
    shutil.copytree(BINDER, pile)
    shutil.copytree(WORLDS, table / "worlds")
    shutil.copytree(
        HERE / "stories", table / "stories"
    )  # written between sessions; author.py makes worlds of them
    (
        table / "scans"
    ).mkdir()  # photos of the GM's handwritten pages, read at the end of the night
    for page in PAGES.values():
        shutil.copy(page, table / page.name)
    shutil.copy(WORDS, words)
    words.chmod(0o600)  # the kernel reads a words list only its owner can
    steps = (
        ("the record", [str(ROOT / "kernel.py"), "init", "--box", str(box), "--pile", str(pile),
                        "--key", str(key), "--words", str(words), "--now", now]),
        ("the house rules", [str(RULES), "propose", "--box", str(box), "--now", now,
                             str(pile / "house-rules.md")]),
        ("the story", [str(GM), "--box", str(box), "open", "--world", str(table / "worlds" / WORLD),
                       "--now", now]),
    )  # fmt: skip
    for what, argv in steps:
        done = run(*argv)
        if done.returncode == kernel.REFUSED:
            return fail(f"{what}: {(done.stderr or done.stdout).strip()}")
        print(f"## {what}\n{done.stdout.rstrip()}\n")
    rows, _ = kernel.read(box / "record.jsonl")
    waiting = [r["subject"] for r in rows if r["kind"] == "proposal" and r.get("verdict") == "pass"]  # fmt: skip
    print(f"the box is laid at {table}: {len(waiting)} waiting on the seal, nothing sealed.")  # fmt: skip
    print(f"whoever holds {key} is the game master; seal or decline each with")
    print(f"  python kernel.py seal --box {box} proposal:<id>")
    return kernel.ESCALATE if waiting else kernel.ALIVE


def cmd_page(table: Path, which: str) -> int:
    box, page = table / "record", table / PAGES[which].name
    if not (box / "kernel.json").exists() or not page.exists():
        return fail(f"{table} isn't a box laid by open")
    keep = []
    if which in (
        "prep",
        "end",
    ):  # each run kept in a folder of its own, for the steps that write
        runs = table / which
        runs.mkdir(exist_ok=True)
        keep = ["--to", str(runs / f"{len(list(runs.iterdir())) + 1:03d}")]
    done = run(str(STACK), "--box", str(box), "--stack", str(page), *keep)
    print(done.stdout.rstrip())
    if done.returncode == kernel.REFUSED:
        return fail(f"the {which} page: {done.stderr.strip()}")
    chain = run(str(ROOT / "kernel.py"), "verify", "--box", str(box))
    print(chain.stdout.rstrip())
    if chain.returncode != kernel.ALIVE:
        return fail(f"the chain: {(chain.stderr or chain.stdout).strip()}")
    if which == "end":  # what the table made true, to close the night on
        canon = run(str(SESSION), "--table", str(table), "canon")
        print("\n## what the table holds true\n" + canon.stdout.rstrip())
    return done.returncode


def main(argv: list[str]) -> int:
    opts, args, it = {}, [], iter(argv)
    for a in it:
        if a in ("--table", "--key", "--now"):
            opts[a] = next(it, "")
        else:
            args.append(a)
    if not opts.get("--table") or args not in (["open"], ["prep"], ["end"], ["check"]):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return kernel.REFUSED
    table = Path(opts["--table"])
    if args != ["open"]:
        return cmd_page(table, args[0])
    if not opts.get("--key"):
        return fail("open needs --key: where the kernel makes the key for the game master")  # fmt: skip
    return cmd_open(table, Path(opts["--key"]), opts.get("--now") or kernel.now())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
