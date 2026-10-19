"""A board: its size, its regions, and the one answer it was built around.

Cells are named the way willows-grove's cross-table names them
(``templates/cross-table/README.md``): rows are letters (A-Z, then AA, AB...),
columns are numbers, so the corner is ``A1``. An address names one cell and is
never renumbered.

``generate(seed, n)`` is the whole of a board's making, and it reads nothing
but its two arguments:

1. A placement: a cat per row and column, no two touching, its columns tried
   in an order drawn from the seed.
2. Regions: each cat starts its own region, and the regions grow one
   neighbouring cell at a time, region and cell drawn from the seed, until
   every cell is in one. Grown cell by neighbouring cell, every region is
   connected by construction.
3. Uniqueness: ``solve.count`` must find exactly one placement. While a
   second answer exists, one of its cells that isn't a cat of the first moves
   to a neighbouring region (cell and region drawn from the seed), only where
   its old region stays connected. A board still with a second answer after
   ``REPAIRS`` such moves is never handed out; the same generator draws again.

2x2 and 3x3 have no placement at all (the cats in neighbouring rows must sit
two columns apart, and there is no room), so they are refused, never searched.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from . import solve
from .rng import Rng

#: How many draws one seed gets before it says no board was found.
TRIES = 400
#: How many cells one draw may move to make its answer the only one.
REPAIRS = 200
#: Sizes with no placement at all (see the module docstring).
IMPOSSIBLE = frozenset({2, 3})


class NoBoard(ValueError):
    """No board exists for this size, or none was found for this seed."""


def row_name(r: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, the way spreadsheet columns run on."""
    out = ""
    r += 1
    while r:
        r, rem = divmod(r - 1, 26)
        out = chr(65 + rem) + out
    return out


def address(r: int, c: int) -> str:
    return f"{row_name(r)}{c + 1}"


@dataclass(frozen=True)
class Board:
    n: int
    regions: tuple  # row-major, region ids 1..n, numbered by first appearance
    solution: tuple  # the cat's column in each row

    def addresses(self) -> list:
        return [address(r, c) for r in range(self.n) for c in range(self.n)]

    def index(self, addr: str) -> int | None:
        """The cell's row-major index, or None when ``addr`` is not on this board."""
        try:
            i = self.addresses().index(addr)
        except ValueError:
            return None
        return i

    def canon(self) -> bytes:
        """The board as bytes: the same board is always the same bytes."""
        return json.dumps(
            {"n": self.n, "regions": list(self.regions), "solution": list(self.solution)},
            sort_keys=True, separators=(",", ":"),
        ).encode()

    def digest(self) -> str:
        return hashlib.sha256(self.canon()).hexdigest()


def _canonical(regions: list) -> tuple:
    """Renumber region ids 1..n in order of first appearance, row by row, so two
    boards with the same shape are equal however their ids were drawn."""
    seen: dict = {}
    return tuple(seen.setdefault(r, len(seen) + 1) for r in regions)


def _grow(n: int, cols: list, rng: Rng) -> list:
    region = [0] * (n * n)
    for r, c in enumerate(cols):
        region[r * n + c] = r + 1
    left = n * n - n
    while left:
        frontier: dict = {}
        for i, owner in enumerate(region):
            if not owner:
                continue
            r, c = divmod(i, n)
            for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= rr < n and 0 <= cc < n and not region[rr * n + cc]:
                    frontier.setdefault(owner, set()).add(rr * n + cc)
        owner = rng.pick(sorted(frontier))
        cell = rng.pick(sorted(frontier[owner]))
        region[cell] = owner
        left -= 1
    return region


def _connected(region: list, n: int, owner: int) -> bool:
    cells = [i for i, o in enumerate(region) if o == owner]
    if not cells:
        return False
    seen, todo = {cells[0]}, [cells[0]]
    while todo:
        r, c = divmod(todo.pop(), n)
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            j = rr * n + cc
            if 0 <= rr < n and 0 <= cc < n and region[j] == owner and j not in seen:
                seen.add(j)
                todo.append(j)
    return len(seen) == len(cells)


def _repair(n: int, cols: list, region: list, rng: Rng) -> bool:
    """Move cells until ``cols`` is the board's only answer; False if it won't go."""
    cats = {r * n + c for r, c in enumerate(cols)}
    for _ in range(REPAIRS):
        alt = solve.other(n, tuple(region), tuple(cols))
        if alt is None:
            return True
        moves = []
        for r, c in enumerate(alt):
            i = r * n + c
            if i in cats:
                continue
            for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= rr < n and 0 <= cc < n and region[rr * n + cc] != region[i]:
                    moves.append((i, region[rr * n + cc]))
        rng_moves = rng.shuffled(sorted(set(moves)))
        for i, to in rng_moves:
            was = region[i]
            region[i] = to
            if _connected(region, n, was):
                break
            region[i] = was
        else:
            return False
    return solve.other(n, tuple(region), tuple(cols)) is None


def generate(seed: int, n: int, tries: int = TRIES) -> Board:
    """The board for (seed, n): the same arguments, the same board, every time."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise NoBoard(f"a board is a positive whole size, not {n!r}")
    if n in IMPOSSIBLE:
        raise NoBoard(f"no {n}x{n} board exists: its cats can't avoid touching")
    rng = Rng(seed)
    for _ in range(tries):
        cols = solve.placements(n, lambda row: rng.shuffled(range(n)))
        if cols is None:  # unreachable for n outside IMPOSSIBLE; said, not assumed
            raise NoBoard(f"no {n}x{n} placement exists")
        region = _grow(n, cols, rng)
        if _repair(n, cols, region, rng):
            regions = _canonical(region)
            if solve.count(n, regions, limit=2) == 1:  # checked again, as handed out
                return Board(n=n, regions=regions, solution=tuple(cols))
    raise NoBoard(f"no {n}x{n} board with one answer in {tries} draws for seed {seed}")
