"""The rules, as a search: how many ways the cats can sit on a board.

A placement puts one cat in every row, every column and every region, and no
two cats touch, diagonals included. With one cat per row and per column, two
cats can only touch across neighbouring rows, and only diagonally, so the
no-touch rule is exactly: neighbouring rows' columns differ by at least 2.

``count`` stops at ``limit``: a generator asking "is this board's answer
unique?" only needs to know whether there is a second one.
"""
from __future__ import annotations


def fits(col: int, row: int, cols: list, regions: tuple, n: int, used_cols: set,
         used_regions: set) -> bool:
    """Whether a cat at (row, col) breaks nothing already placed in rows < row."""
    if col in used_cols or regions[row * n + col] in used_regions:
        return False
    return row == 0 or abs(col - cols[row - 1]) >= 2


def solutions(n: int, regions: tuple):
    """Every placement of n cats on this board, in column order, lazily."""
    cols: list = []
    used_cols: set = set()
    used_regions: set = set()

    def go(row: int):
        if row == n:
            yield tuple(cols)
            return
        for col in range(n):
            if fits(col, row, cols, regions, n, used_cols, used_regions):
                cols.append(col)
                used_cols.add(col)
                used_regions.add(regions[row * n + col])
                yield from go(row + 1)
                used_regions.discard(regions[row * n + col])
                used_cols.discard(col)
                cols.pop()

    yield from go(0)


def count(n: int, regions: tuple, limit: int = 2) -> int:
    """Placements of n cats on this board, counted up to ``limit``."""
    found = 0
    for _ in solutions(n, regions):
        found += 1
        if found >= limit:
            break
    return found


def other(n: int, regions: tuple, answer: tuple) -> tuple | None:
    """A placement that is not ``answer``, or None when ``answer`` is the only one."""
    return next((s for s in solutions(n, regions) if s != tuple(answer)), None)


def placements(n: int, order) -> list | None:
    """One placement with no regions yet (every row, column, no touching),
    trying columns in the order ``order(row)`` gives; None when none exists."""
    cols: list = []

    def go(row: int) -> bool:
        if row == n:
            return True
        for col in order(row):
            if col not in cols and (row == 0 or abs(col - cols[-1]) >= 2):
                cols.append(col)
                if go(row + 1):
                    return True
                cols.pop()
        return False

    return cols if go(0) else None
