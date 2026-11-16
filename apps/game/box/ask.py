"""ask.py: ask the GM's binder in your own words. Python 3.9+.

    python apps/game/box/ask.py [--table DIR] [--top N] QUESTION...

The box's own binder and words list unless --table names a box laid by
open_table.py (then DIR/pile and DIR/words.txt). It prints where to look,
best first, each passage with its page, line and why:

    monsters/clockwork-hound.md:5  (what "dog" usually means here)
        Grit 3, Wit 1, Heart 0, Weird 2. Hits 6.

This is the host side of Die-Namic's search seam (die_namic.binder): the core
is handed willow's reading of the binder (kernel.chunks, the kernel's words,
common words and plain forms, and the words list parsed the kernel's way)
and willow's pile-rank ranker, all found through the box's pin, and imports
none of them itself. It points at where to look; it is not the kernel's
answer. It reads and writes nothing else.

Exit codes, the kernel's: 0 places to look; 42 nothing holds a word of the
question; 2 refused.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import willow_pin  # noqa: E402

ROOT = willow_pin.root()  # willow, held to apps/game/willow.pin.json
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "adapters" / "stdlib" / "pile-rank"))
import kernel  # noqa: E402
import pile_rank  # noqa: E402

from die_namic import Binder  # noqa: E402


def binder(pile: Path, words_file: Path) -> Binder:
    """The binder at `pile`, asked through `words_file`, with willow's reading
    and willow's ranker handed to the core."""
    means: dict = {}
    if words_file.is_file():
        means, why = kernel.parse_words(words_file.read_text(encoding="utf-8"))
        if why:
            raise ValueError(f"{words_file.name}: {why}")
    return Binder(kernel.chunks(pile), pile_rank.Ranker, means,
                  words=kernel.words, common=kernel.FUNCTION, plain=kernel.stem)  # fmt: skip


def main(argv: list[str]) -> int:
    opts, words, it = {}, [], iter(argv)
    for a in it:
        if a in ("--table", "--top"):
            opts[a] = next(it, "")
        elif a.startswith("--"):
            words = []
            break
        else:
            words.append(a)
    question = " ".join(words).strip()
    if not question:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return kernel.REFUSED
    try:
        top = int(opts.get("--top", "6"))
    except ValueError:
        print("refused: --top is a number", file=sys.stderr)
        return kernel.REFUSED
    if opts.get("--table"):
        table = Path(opts["--table"])
        pile, words_file = table / "pile", table / "words.txt"
        if not pile.is_dir():
            print(f"refused: {table} isn't a box laid by open_table.py", file=sys.stderr)
            return kernel.REFUSED
    else:
        pile, words_file = HERE / "binder", HERE / "gm-words.txt"
    try:
        found = binder(pile, words_file).ask(question, top)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return kernel.REFUSED
    if not found:
        print("Nothing in the binder holds those words. A word you use that the "
              "binder doesn't is a line for the words list.")  # fmt: skip
        return kernel.ESCALATE
    for f in found:
        print(f"{f.where}  ({f.why})")
        print("\n".join("    " + ln for ln in f.text.splitlines()))
    return kernel.ALIVE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
