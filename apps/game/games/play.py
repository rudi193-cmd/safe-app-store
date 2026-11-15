"""play.py: one of Die-Namic's games, played on a box's record. Python 3.9+.

    python apps/game/games/play.py GAME --table DIR [ARGS...]
    python apps/game/games/play.py GAME [ARGS...]          (a game that reads no box)

Each game is a willow add-on, and stays in willow: Die-Namic plays it where
it lives, through the pin the box uses (apps/game/willow.pin.json,
box/willow_pin.py), which refuses a willow whose files differ. GAME is a
folder here, and the add-on of the same name.

With --table, the game plays on that box's record, `DIR/record`, as if it
were given `--box DIR/record`; the rest of the arguments are the game's own
(`move 11-15`, `play --size 6`, `roll 2d6+1`), passed as they are. A game
that reads no box (play-odds, play-horoscope, oracle-text) takes its arguments alone.

Exit codes are the game's own, the kernel's: 0 done; 42 waiting on the
person's seal, or nothing found; 2 refused.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "box"))
import willow_pin

REFUSED = 2


def script(root: Path, game: str) -> Path:
    folder = root / "adapters" / "stdlib" / game
    named = folder / f"{game.replace('-', '_')}.py"
    if named.is_file():
        return named
    found = [p for p in folder.glob("*.py") if not p.name.startswith("test_")]
    if len(found) != 1:
        raise FileNotFoundError(f"{game}: no one script in {folder}")
    return found[0]


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return REFUSED
    game, rest = argv[0], argv[1:]
    if not (HERE / game).is_dir() or game not in willow_pin.pin()["add_ons"]:
        here = sorted(
            p.name
            for p in HERE.iterdir()
            if p.is_dir() and not p.name.startswith(("_", "."))
        )
        print(
            f"refused: {game!r} isn't one of the games: {', '.join(here)}",
            file=sys.stderr,
        )
        return REFUSED
    try:
        root = willow_pin.root()
        run = script(root, game)
    except (willow_pin.Unpinned, FileNotFoundError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return REFUSED
    if "--table" in rest:
        i = rest.index("--table")
        if i + 1 >= len(rest):
            print("refused: --table needs the box's folder", file=sys.stderr)
            return REFUSED
        table = Path(rest[i + 1])
        if not (table / "record" / "kernel.json").is_file():
            print(
                f"refused: {table} isn't a box laid by box/open_table.py",
                file=sys.stderr,
            )
            return REFUSED
        rest = ["--box", str(table / "record"), *rest[:i], *rest[i + 2 :]]
    return subprocess.run([sys.executable, str(run), *rest], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
