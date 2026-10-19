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

import functools
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
#: For k cats per row, column and region, the smallest board with any placement,
#: found by exhaustive search (no 2-cat board below 8x8, no 3-cat below 12x12).
#: 3 cats on 14x14 took 78 s to place once in plain Python, so 3-cat boards
#: stop at 13; more than 3 cats a row isn't built.
SMALLEST = {2: 8, 3: 12}
#: Search nodes one k-cat draw's repair may spend, over all its second-answer
#: searches. A draw that needs more is dropped and the seed's next draw is taken:
#: the same seed still gives the same board (node counts are exact), and a
#: rare hard draw no longer costs half a minute.
REPAIR_BUDGET = 40_000
#: Region growths one k-cat placement gets before the seed draws another.
GROWTHS = 8
LARGEST = {1: 9, 2: 10, 3: 13}


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
    solution: tuple  # k == 1: the cat's column in each row; else each row's k columns
    k: int = 1  # cats per row, column and region

    def cats(self) -> set:
        """Every answer cell's row-major index."""
        if self.k == 1:
            return {r * self.n + c for r, c in enumerate(self.solution)}
        return {r * self.n + c for r, cs in enumerate(self.solution) for c in cs}

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
        body = {"n": self.n, "regions": list(self.regions), "solution": list(self.solution)}
        if self.k != 1:  # a 1-cat board's bytes are what they always were
            body = {**body, "k": self.k, "solution": [list(cs) for cs in self.solution]}
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

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


def _grow_k(n: int, k: int, cats: set, rng: Rng) -> list | None:
    """Regions for a k-cat placement: n of the cats, drawn from the seed, each
    start a region. While a cat is unheld, the regions still short of k take
    the step, over all of them, that ends nearest such a cat (ties drawn from
    the seed); once every cat is held, regions take the empty cells left.
    A region takes a cat only while it holds fewer than k. None when a draw
    strands a cat."""
    region = [0] * (n * n)
    held = {}
    for g, i in enumerate(rng.shuffled(sorted(cats))[:n], 1):
        region[i] = g
        held[g] = 1
    left = n * n - n
    while left:
        free_cats = [j for j in cats if not region[j]]
        frontier: dict = {}
        for i, owner in enumerate(region):
            if not owner:
                continue
            r, c = divmod(i, n)
            for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                j = rr * n + cc
                if (0 <= rr < n and 0 <= cc < n and not region[j]
                        and (j not in cats or held[owner] < k)):
                    frontier.setdefault(owner, set()).add(j)
        needy = [g for g in sorted(frontier) if held[g] < k] if free_cats else []
        if needy:
            spots = [divmod(f, n) for f in free_cats]

            def dist(j):
                r, c = divmod(j, n)
                return min(abs(r - fr) + abs(c - fc) for fr, fc in spots)

            # the move, over every needy region, that ends nearest a cat nobody holds
            moves = sorted((dist(j), g, j) for g in needy for j in frontier[g])
            best = moves[0][0]
            _, owner, cell = rng.pick([m for m in moves if m[0] == best])
        elif frontier:
            owner = rng.pick(sorted(frontier))
            cell = rng.pick(sorted(frontier[owner]))
        else:
            return None
        region[cell] = owner
        held[owner] += cell in cats
        left -= 1
    return region if all(h == k for h in held.values()) else None


def _repair_k(n: int, k: int, answer: tuple, cats: set, region: list, rng: Rng) -> bool:
    budget = [REPAIR_BUDGET]
    for _ in range(REPAIRS):
        alt = solve.other_k(n, k, tuple(region), answer, budget)
        if alt is None:
            return True
        moves = []
        for r, cs in enumerate(alt):
            for c in cs:
                i = r * n + c
                if i in cats:
                    continue
                for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if 0 <= rr < n and 0 <= cc < n and region[rr * n + cc] != region[i]:
                        moves.append((i, region[rr * n + cc]))
        for i, to in rng.shuffled(sorted(set(moves))):
            was = region[i]
            region[i] = to
            if _connected(region, n, was):
                break
            region[i] = was
        else:
            return False
    return solve.other_k(n, k, tuple(region), answer) is None


def _generate_k(seed: int, n: int, k: int, tries: int) -> Board:
    rng = Rng(seed)
    for _ in range(tries):
        answer = solve.placements_k(n, k, lambda row, sets: rng.shuffled(sets))
        if answer is None:  # unreachable at SMALLEST and above; said, not assumed
            raise NoBoard(f"no {n}x{n} placement of {k} cats a row exists")
        cats = {r * n + c for r, cs in enumerate(answer) for c in cs}
        # growth is cheap and a placement is not, so a stranded growth tries
        # again on the same placement before the seed draws a new one
        region = next((g for g in (_grow_k(n, k, cats, rng) for _ in range(GROWTHS)) if g), None)
        try:
            if region is None or not _repair_k(n, k, answer, cats, region, rng):
                continue
        except solve.Budget:
            continue
        regions = _canonical(region)
        if solve.count_k(n, k, regions, limit=2) == 1:  # checked again, as handed out
            return Board(n=n, regions=regions, solution=answer, k=k)
    raise NoBoard(f"no {n}x{n} {k}-cat board with one answer in {tries} draws for seed {seed}")


def generate(seed: int, n: int, tries: int = TRIES, k: int = 1) -> Board:
    """The board for (seed, n, k): the same arguments, the same board, every time.
    A pure function of its arguments with a frozen result, so it is memoised:
    a 12x12 three-cat board costs about a second to make, and only once. The
    arguments are checked first, so what can't be a board is refused, never cached."""
    for name, v in (("seed", seed), ("size", n), ("tries", tries), ("cats a row", k)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise NoBoard(f"the {name} is a whole number, not {v!r}")
    return _generate(seed, n, tries, k)


@functools.lru_cache(maxsize=256)
def _generate(seed, n, tries, k) -> Board:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise NoBoard(f"a board is a positive whole size, not {n!r}")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1 or k > max(SMALLEST):
        raise NoBoard(f"1 to {max(SMALLEST)} cats a row are built, not {k!r}")
    if k > 1:
        if n < SMALLEST[k]:
            raise NoBoard(f"no {n}x{n} board holds {k} cats a row: they can't avoid touching")
        if n > LARGEST[k]:
            raise NoBoard(f"{k}-cat boards are built up to {LARGEST[k]}x{LARGEST[k]}")
        return _generate_k(seed, n, k, tries)
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
