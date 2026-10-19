"""Measured difficulty: how far plain reasoning gets, and how players fare.

Nothing here is asserted; every number comes from playing or reasoning over
real boards, seeded, so the same call gives the same numbers.

``deduce(board)`` reasons the way a player does without the answer, with two
plain rules, repeated until nothing changes:

* a cat rules out its eight neighbours, and a row, column or region holding its
  k cats rules out the rest of its cells;
* a row, column or region that needs m more cats and has exactly m cells left
  gets a cat in each.

It never looks at ``board.solution``; a test checks that every cat it places is
in the answer. The share of the answer it reaches is the board's *plain*
share: 1.0 means plain reasoning solves it; less means a player has to think
harder (or guess) somewhere.

``measure(n, k, seeds)`` plays each board three ways, every policy drawn from
its own seeded stream:

* **random**: any legal move, the way the table's baselines play every game;
* **careful**: marks what reasoning (look-ahead included) rules out, places what
  it forces, and only then takes a hint, or, with none left, guesses among cells
  still open, marking a wrong guess;
* plus each board's share reached by the plain rules, and with look-ahead.

``tier(board)`` names a board by the least reasoning that solves it.
"""
from __future__ import annotations

import statistics
from types import SimpleNamespace

from .board import Board, address, generate
from .play import Game
from .rng import Rng


def _lines(b: Board) -> list:
    n = b.n
    rows = [[r * n + c for c in range(n)] for r in range(n)]
    cols = [[r * n + c for r in range(n)] for c in range(n)]
    regs = [[i for i, g in enumerate(b.regions) if g == want]
            for want in sorted(set(b.regions))]
    return rows + cols + regs


def _near(i: int, n: int) -> list:
    r, c = divmod(i, n)
    return [rr * n + cc for rr in (r - 1, r, r + 1) for cc in (c - 1, c, c + 1)
            if (rr, cc) != (r, c) and 0 <= rr < n and 0 <= cc < n]


def _broken(b: Board, lines: list, cats: set, out: set) -> bool:
    """Whether these cells already break a rule: touching cats, a line over
    its k, or a line that can no longer reach its k."""
    if any(j in cats for i in cats for j in _near(i, b.n)):
        return True
    for line in lines:
        have = sum(i in cats for i in line)
        open_ = sum(i not in cats and i not in out for i in line)
        if have > b.k or have + open_ < b.k:
            return True
    return False


def deduce(b: Board, cats=(), out=(), ahead: bool = False) -> tuple[set, set]:
    """(cats, ruled_out): what reasoning reaches from the cells already known
    (``cats`` placed, ``out`` marked). Never reads the answer.

    With ``ahead``, a third rule: a cell is ruled out when a cat there, followed
    through the plain rules, breaks one. That is the "if it went here, that
    region would have nowhere left" step a player takes once the plain rules
    stall."""
    n, k = b.n, b.k
    lines = _lines(b)
    cats, out = set(cats), set(out)
    changed = True
    while changed:
        changed = False
        if ahead and not changed:
            cats, out = deduce(b, cats, out)
            for i in range(n * n):
                if i in cats or i in out:
                    continue
                c2, o2 = deduce(b, cats | {i}, out)
                if _broken(b, lines, c2, o2):
                    out.add(i)
                    changed = True
        for i in list(cats):
            for j in _near(i, n):
                if j not in out:
                    out.add(j)
                    changed = True
        for line in lines:
            have = [i for i in line if i in cats]
            open_ = [i for i in line if i not in cats and i not in out]
            if len(have) >= k:
                for i in open_:
                    out.add(i)
                    changed = True
            elif open_ and len(open_) == k - len(have):
                for i in open_:
                    cats.add(i)
                    changed = True
    return cats, out


def public(view: dict) -> SimpleNamespace:
    """The board as a player sees it (``Game.state()``): size, k and regions,
    no answer. ``deduce`` and ``tier`` take this as readily as a Board."""
    return SimpleNamespace(n=view["n"], k=view["k"], regions=tuple(view["regions"]))


def plain_share(b: Board, ahead: bool = False) -> float:
    """The share of the answer reasoning reaches from an empty board: the plain
    rules alone, or with ``ahead``, the look-ahead rule too."""
    cats, _ = deduce(b, ahead=ahead)
    return len(cats) / (b.n * b.k)


def _careful(game: Game, rng: Rng) -> None:
    b = game.board
    while game.status == "playing":
        cats = {b.index(a) for a, v in game.cells.items() if v == "cat"}
        out = {b.index(a) for a, v in game.cells.items() if v == "x"}
        got, ruled = deduce(b, cats, out, ahead=True)
        move = next((("cat", address(*divmod(i, b.n))) for i in sorted(got - cats)), None)
        if move is None:
            move = next((("x", address(*divmod(i, b.n))) for i in sorted(ruled - out - cats)), None)
        if move is None and game.hints["free"] + game.hints["earned"]:
            move = ("hint",)
        if move is None:
            open_ = [a for a, v in game.cells.items() if v == ""]
            guess = rng.pick(open_)
            hearts = game.hearts
            game.step(("cat", guess))
            if game.status == "playing" and game.hearts < hearts:
                game.step(("x", guess))  # a wrong guess is a cell learned
            continue
        game.step(move)


#: A random player can mark and clear forever; past this many moves it has
#: not won, and the board counts as unresolved, the table's own cap rule.
RANDOM_CAP = 5000


def _random(game: Game, rng: Rng) -> None:
    for _ in range(RANDOM_CAP):
        if game.status != "playing":
            return
        game.step(rng.pick(game.legal_moves()))


def tier(b: Board) -> str:
    """One board's difficulty, by the least reasoning that solves it:
    ``plain``, ``ahead``, or ``beyond`` (neither rule set finishes it)."""
    if plain_share(b) == 1.0:
        return "plain"
    return "ahead" if plain_share(b, ahead=True) == 1.0 else "beyond"


def measure(n: int, k: int = 1, seeds=range(50)) -> dict:
    """Difficulty of the (n, k) level over ``seeds``, from real play."""
    seeds = list(seeds)
    shares, ahead, rand, careful, hearts = [], [], [], [], []
    for s in seeds:
        b = generate(s, n, k=k)
        shares.append(plain_share(b))
        ahead.append(plain_share(b, ahead=True))
        g = Game(b, s)
        _random(g, Rng(s ^ 0x5A5A5A5A))
        rand.append(g.status == "won")
        g = Game(b, s)
        _careful(g, Rng(s ^ 0xA5A5A5A5))
        careful.append(g.status == "won")
        hearts.append(g.hearts)
    return {
        "level": f"{n}x{n}, {k} cat(s)",
        "boards": len(seeds),
        "plain_share": round(statistics.mean(shares), 3),
        "solved_by_plain": round(sum(x == 1.0 for x in shares) / len(seeds), 3),
        "ahead_share": round(statistics.mean(ahead), 3),
        "solved_by_ahead": round(sum(x == 1.0 for x in ahead) / len(seeds), 3),
        "random_wins": round(sum(rand) / len(seeds), 3),
        "careful_wins": round(sum(careful) / len(seeds), 3),
        "careful_hearts_left": round(statistics.mean(hearts), 2),
    }


LEVELS = ((5, 1), (6, 1), (8, 1), (9, 2), (10, 2), (13, 3))


def format_report(rows: list) -> str:
    """A Markdown table of ``measure`` rows."""
    cols = ("level", "boards", "plain_share", "solved_by_plain", "ahead_share",
            "solved_by_ahead", "random_wins", "careful_wins", "careful_hearts_left")
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    count = int(args[0]) if args else 50
    print(format_report([measure(n, k, range(count)) for n, k in LEVELS]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
