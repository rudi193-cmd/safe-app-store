"""author.py: a story written as markdown, made into a world game-master plays. Python 3.9+.

    python apps/game/box/author.py STORY.md [--to WORLD.json]

For writing between sessions: a new story, or the next chapter of one, in
plain headings and `key: value` lines, the way the binder is written. It is
the shape story-timeline's `export-story` writes a timeline out in, so a
story can be written in story-timeline, the writer's workbench, and played
here; a comment line, as the export's first, is skipped. It
prints the world as JSON, or writes it to WORLD.json (never over a file
that is there), and every world it makes is game-master's own, checked by
game-master's `validate`. A line it can't read is refused with its number.

The shape, in order:

    # Title
    id: wasp-nest
    setting: One line of where and when.
    stats: Grit, Wit, Heart
    base stat: 1
    offers: guest                       (the kinds of offer it turns on; optional)

    ## Characters
    - pell: Pell | miller's apprentice | seated | Grit 2, Heart 1
    - cogwen: Cogwen | the keeper        (no "seated": the GM's to play)

    ## Places
    - ceiling: The cellar ceiling

    ## Scene up: Up into the ceiling @ ceiling
    Opening lines, one a line.

    ### The prompt, as the GM says it.
    id: climb
    kind: action                        (or: decision)
    by: juno                            (whose beat it is; optional)
    suggests: Wit                       (an action's approach)
    when: up::climb is weak, miss       (or: offered guest is sealed;
                                         or: sealed clockwork-cellar::room::free is sealed,
                                         a ruling in an earlier chapter)
    - strong: what happens
    - weak: what happens
    - miss: what happens
    proposed by: vell                   (a decision's)
    fact: what the ruling would make true

Exit codes, the kernel's: 0 made; 2 refused.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import willow_pin

ROOT = (
    willow_pin.root()
)  # willow, where its pieces live, held to apps/game/willow.pin.json
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "adapters" / "stdlib" / "game-master"))
import game_master as gm
import kernel

KEY = re.compile(r"^([a-z][a-z ]*):\s*(.*)$")
CHARACTER = re.compile(r"^- ([a-z0-9-]+):\s*(.+)$")
SCENE = re.compile(r"^## Scene ([a-z0-9-]+):\s*(.+?)\s*@\s*([a-z0-9-]+)$")
BEAT_WHEN = re.compile(r"^([a-z0-9-]+::[a-z0-9-]+) is (.+)$")
OFFER_WHEN = re.compile(r"^offered ([a-z0-9-]+) is (.+)$")
SEALED_WHEN = re.compile(r"^sealed ([a-z0-9-]+::[a-z0-9-]+::[a-z0-9-]+) is (.+)$")


class StoryError(ValueError):
    """A story that can't be read; the message names the line."""


def listed(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def character(cid: str, text: str, at: int) -> dict:
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 2:
        raise StoryError(
            f"line {at}: a character is `- id: Name | role [| seated] [| Stat N, ...]`"
        )
    c = {"id": cid, "name": parts[0], "role": parts[1], "seat": False, "stats": {}}
    for p in parts[2:]:
        if p == "seated":
            c["seat"] = True
        elif p:
            for s in listed(p):
                m = re.fullmatch(r"(\S+)\s+(-?\d+)", s)
                if not m:
                    raise StoryError(
                        f"line {at}: {s!r} isn't a stat and a number, as Grit 2"
                    )
                c["stats"][m.group(1)] = int(m.group(2))
    return c


def when_of(text: str, at: int) -> dict:
    if m := SEALED_WHEN.match(text):
        return {"sealed": m.group(1), "is": listed(m.group(2))}
    if m := OFFER_WHEN.match(text):
        return {"offered": m.group(1), "is": listed(m.group(2))}
    if m := BEAT_WHEN.match(text):
        return {"beat": m.group(1), "is": listed(m.group(2))}
    raise StoryError(
        f"line {at}: when is `scene::beat is strong, weak`, `offered KIND is sealed`"
        " or `sealed story::scene::beat is sealed`"
    )


def read(text: str) -> dict:
    """The world a story's markdown writes, or StoryError naming the line."""
    world = {"characters": [], "places": [], "scenes": []}
    section, scene, beat = "head", None, None
    for at, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or (line.startswith("<!--") and line.endswith("-->")):
            continue
        if line.startswith("# ") and section == "head" and "title" not in world:
            world["title"] = line[2:].strip()
        elif line in ("## Characters", "## Places"):
            section, scene, beat = line[3:].lower(), None, None
        elif m := SCENE.match(line):
            scene = {"id": m.group(1), "title": m.group(2), "place": m.group(3), "opening": [], "beats": []}  # fmt: skip
            world["scenes"].append(scene)
            section, beat = "scene", None
        elif line.startswith("### "):
            if scene is None:
                raise StoryError(
                    f"line {at}: a beat comes inside a scene (## Scene id: Title @ place)"
                )
            beat = {"prompt": line[4:].strip()}
            scene["beats"].append(beat)
        elif section in ("characters", "places") and (m := CHARACTER.match(line)):
            if section == "characters":
                world["characters"].append(character(m.group(1), m.group(2), at))
            else:
                world["places"].append({"id": m.group(1), "name": m.group(2).strip()})
        elif beat is not None and (
            m := re.match(r"^- (strong|weak|miss):\s*(.+)$", line)
        ):
            beat.setdefault("outcomes", {})[m.group(1)] = m.group(2)
        elif (m := KEY.match(line)) and (section == "head" or beat is not None):
            key, value = m.group(1), m.group(2).strip()
            if beat is None:
                head = {"id": "id", "setting": "setting", "stats": "stats", "base stat": "base_stat", "offers": "offers"}  # fmt: skip
                if key not in head:
                    raise StoryError(
                        f"line {at}: {key!r} isn't a story's: {', '.join(head)}"
                    )
                world[head[key]] = listed(value) if key in ("stats", "offers") else int(value) if key == "base stat" else value  # fmt: skip
            else:
                fields = {
                    "id": "id",
                    "kind": "kind",
                    "by": "by",
                    "suggests": "suggests",
                }
                if key in fields:
                    beat[fields[key]] = value
                elif key == "when":
                    beat["when"] = when_of(value, at)
                elif key in ("proposed by", "fact"):
                    beat.setdefault("proposes", {})["proposed_by" if key == "proposed by" else "fact"] = value  # fmt: skip
                else:
                    raise StoryError(f"line {at}: {key!r} isn't a beat's: id, kind, by, suggests, when, proposed by, fact")  # fmt: skip
        elif scene is not None and beat is None:
            scene["opening"].append(line)
        else:
            raise StoryError(f"line {at}: {line[:60]!r} isn't part of a story here")
    world.setdefault("base_stat", 1)
    return world


def make(path: Path) -> dict:
    world = read(path.read_text(encoding="utf-8"))
    try:
        return gm.validate(world)
    except gm.WorldError as e:
        raise StoryError(f"{path.name}: {e}") from None


def main(argv: list[str]) -> int:
    opts, args, it = {}, [], iter(argv)
    for a in it:
        if a == "--to":
            opts[a] = next(it, "")
        else:
            args.append(a)
    if len(args) != 1 or ("--to" in opts and not opts["--to"]):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return kernel.REFUSED
    try:
        world = make(Path(args[0]))
    except (OSError, StoryError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return kernel.REFUSED
    text = json.dumps(world, indent=1, ensure_ascii=False) + "\n"
    if "--to" not in opts:
        print(text, end="")
        return kernel.ALIVE
    to = Path(opts["--to"])
    if to.exists():
        print(f"refused: {to} is there; a world is never written over", file=sys.stderr)
        return kernel.REFUSED
    to.write_text(text, encoding="utf-8")
    scenes = world["scenes"]
    print(f"wrote {to}: {world['title']}, {len(scenes)} scenes, {sum(len(s['beats']) for s in scenes)} beats")  # fmt: skip
    return kernel.ALIVE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
