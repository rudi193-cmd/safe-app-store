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


# ── k cats per row, column and region (intermediate levels) ─────────────────
#
# The same rules with k > 1: k cats in every row, column and region, no two
# touching. Two cats in one row touch when their columns differ by less than
# 2; across neighbouring rows, when their columns differ by less than 2 (the
# same column is now possible, and touches). A placement is a row-by-row
# tuple of k-column tuples.


def rowsets(n: int, k: int) -> list:
    """The ways k cats sit in one row without touching, in column order."""
    from itertools import combinations

    return [c for c in combinations(range(n), k) if all(b - a >= 2 for a, b in zip(c, c[1:]))]


def _row_tables(n: int, k: int):
    """Each row set as (columns, bitmask, the mask of columns it touches below)."""
    out = []
    for c in rowsets(n, k):
        mask = sum(1 << x for x in c)
        near = 0
        for x in c:
            for y in (x - 1, x, x + 1):
                if 0 <= y < n:
                    near |= 1 << y
        out.append((c, mask, near))
    return out


def solutions_k(n: int, k: int, regions: tuple):
    """Every placement of k cats per row, column and region, lazily, in order."""
    rows = _row_tables(n, k)
    owners = sorted(set(regions))
    # cap[g][r]: the most cats region g can still take in rows r.. : per row, no
    # more than k, and no more than every other one of its cells in that row
    cap = {g: [0] * (n + 1) for g in owners}
    for r in range(n - 1, -1, -1):
        for g in owners:
            cells = sum(regions[r * n + c] == g for c in range(n))
            cap[g][r] = cap[g][r + 1] + min(k, (cells + 1) // 2)
    by_row = [[tuple(regions[r * n + x] for x in c) for c, _, _ in rows] for r in range(n)]
    col = [0] * n
    full = 0  # columns holding k cats
    reg = dict.fromkeys(owners, 0)
    picked: list = []

    def go(r: int, banned: int):
        nonlocal full
        if r == n:
            yield tuple(picked)
            return
        rest = n - r - 1
        for i, (c, mask, near) in enumerate(rows):
            if mask & (banned | full):
                continue
            gs = by_row[r][i]
            if any(reg[g] + gs.count(g) > k for g in gs):
                continue
            for x in c:
                col[x] += 1
                if col[x] == k:
                    full |= 1 << x
            for g in gs:
                reg[g] += 1
            if all(k - col[x] <= rest for x in range(n)) and all(
                k - reg[g] <= cap[g][r + 1] for g in owners
            ):
                picked.append(c)
                yield from go(r + 1, near)
                picked.pop()
            for x in c:
                if col[x] == k:
                    full &= ~(1 << x)
                col[x] -= 1
            for g in gs:
                reg[g] -= 1

    yield from go(0, 0)


def count_k(n: int, k: int, regions: tuple, limit: int = 2) -> int:
    found = 0
    for _ in solutions_k(n, k, regions):
        found += 1
        if found >= limit:
            break
    return found


def other_k(n: int, k: int, regions: tuple, answer: tuple) -> tuple | None:
    return next((s for s in solutions_k(n, k, regions) if s != tuple(answer)), None)


def placements_k(n: int, k: int, order) -> tuple | None:
    """One k-cat placement with no regions yet, rows' sets tried in the order
    ``order(row, sets)`` gives; None when none exists."""
    rows = _row_tables(n, k)
    col = [0] * n
    picked: list = []

    def go(r: int, banned: int, full: int) -> bool:
        if r == n:
            return all(x == k for x in col)
        rest = n - r - 1
        for c, mask, near in order(r, rows):
            if mask & (banned | full):
                continue
            for x in c:
                col[x] += 1
            if all(k - col[x] <= rest for x in range(n)):
                picked.append(c)
                now = full
                for x in c:
                    if col[x] == k:
                        now |= 1 << x
                if go(r + 1, near, now):
                    return True
                picked.pop()
            for x in c:
                col[x] -= 1
        return False

    return tuple(picked) if go(0, 0, 0) else None
