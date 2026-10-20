"""catgrid for two: two seats, one seeded board, turns in order.

The board and its one answer are ``generate(seed, n, k)``, the same as a game
for one. What two players add is what the card games at the table have: a
turn order, a score, and something each seat keeps to itself.

* **The cats are public.** A cat placed by either seat is on the board for both.
* **The marks are private.** A seat's x marks are its own notes; the other seat
  never sees them (``observe(seat)``), the way a hand is never shown.
* **Every move passes the turn**, a mark included, so a seat can't stall the
  board on notes. A seat that is out of hearts is skipped.

Rules, each tested by the move it forbids (``tests/test_duel.py``):

D1  Seat 0 moves first; then seats alternate, skipping a seat that is out.
D2  A move is ("cat", cell), ("x", cell), ("clear", cell) or ("hint",).
D3  A cat on an answer cell is placed for both and scores 1 for the mover.
D4  A cat on any other cell is not placed and costs the mover a heart; at none
    left the mover is out.
D5  An x is the mover's own; it can't go on a cell holding a cat, and only its
    own seat can clear it. A cat placed on a cell clears every seat's mark there.
D6  A hint places the next answer cat for nobody: no score. One per seat.
D7  The duel ends when every cat is placed or both seats are out.
D8  The winners are the seats with the top score, when it is above 0; a tie is
    both. No one scored: no winner.
D9  Refused moves (wrong seat, out, ended, malformed, occupied) change nothing.

A duel is its inputs: ``record()`` holds seed, n, k, the board's digest and the
moves with their seats; ``replay(record)`` plays it again and refuses a record
whose board isn't the one it names.
"""
from __future__ import annotations

from .board import address, generate
from .play import HEARTS, Refused

SEATS = 2
CAT, X, EMPTY = "cat", "x", ""


class Duel:
    def __init__(self, seed: int, n: int = 6, k: int = 1) -> None:
        self.seed = seed
        self.board = generate(seed, n, k=k)
        self.cats = {address(*divmod(i, n)) for i in self.board.cats()}
        self.placed: dict = {}  # cell -> seat that placed it, or None for a hint
        self.marks = [set() for _ in range(SEATS)]
        self.hearts = [HEARTS] * SEATS
        self.score = [0] * SEATS
        self.hints = [1] * SEATS
        self.turn = 0
        self.moves: list = []

    # -- state -------------------------------------------------------------

    @property
    def over(self) -> bool:
        return len(self.placed) == len(self.cats) or not any(self.hearts)  # D7

    def winners(self) -> list:
        top = max(self.score)
        return [s for s in range(SEATS) if self.score[s] == top] if top > 0 else []  # D8

    def current(self) -> int:
        return self.turn

    def _cells(self):
        n = self.board.n
        return [address(r, c) for r in range(n) for c in range(n)]

    def legal_moves(self, seat: int) -> list:
        if self.over or seat != self.turn:
            return []
        out = []
        for a in self._cells():
            if a in self.placed:
                continue
            if a in self.marks[seat]:
                out.append(("clear", a))
            else:
                out += [("cat", a), ("x", a)]
        if self.hints[seat]:
            out.append(("hint",))
        return out

    def observe(self, seat: int) -> dict:
        """What ``seat`` sees: every cat, its own marks, both scores and hearts;
        never the other seat's marks, never the answer."""
        _seat(seat)
        cells = {a: (CAT if a in self.placed else X if a in self.marks[seat] else EMPTY)
                 for a in self._cells()}
        return {
            "seat": seat, "n": self.board.n, "k": self.board.k,
            "regions": list(self.board.regions), "cells": cells,
            "placed_by": {a: s for a, s in sorted(self.placed.items())},
            "turn": None if self.over else self.turn,
            "hearts": list(self.hearts), "score": list(self.score),
            "hints": self.hints[seat], "over": self.over,
        }

    # -- moves -------------------------------------------------------------

    def step(self, seat: int, move) -> list:
        """Play ``seat``'s move; returns what happened. Refused changes nothing."""
        _seat(seat)
        if self.over:
            raise Refused("the duel is over")  # D9
        if seat != self.turn:
            raise Refused(f"it is seat {self.turn}'s turn")  # D1
        if isinstance(move, (list, tuple)) and tuple(move) == ("hint",):
            said = self._hint(seat)
        elif (isinstance(move, (list, tuple)) and len(move) == 2
              and move[0] in ("cat", "x", "clear")):
            said = self._cell(seat, move[0], move[1])
        else:
            raise Refused(f"a move is (cat|x|clear, cell) or (hint), not {move!r}")  # D2
        self.moves.append([seat, *move])
        self._pass()
        return said

    def _hint(self, seat: int) -> list:
        if not self.hints[seat]:
            raise Refused("no hint left for this seat")  # D6
        a = next(c for c in self._cells() if c in self.cats and c not in self.placed)
        self.hints[seat] -= 1
        self._place(a, None)
        return [f"seat {seat} hint: {a} holds a cat (no score)"]

    def _cell(self, seat: int, verb: str, a) -> list:
        if not isinstance(a, str) or a not in self._cells():
            raise Refused(f"{a!r} is not a cell on this board")
        if a in self.placed:
            raise Refused(f"{a} already holds a cat")  # D9
        if verb == "x":
            if a in self.marks[seat]:
                raise Refused(f"{a} is already marked")
            self.marks[seat].add(a)  # D5
            return [f"seat {seat} marks a cell"]  # which cell is the seat's own business
        if verb == "clear":
            if a not in self.marks[seat]:
                raise Refused(f"seat {seat} has no mark on {a}")  # D5
            self.marks[seat].discard(a)
            return [f"seat {seat} clears a mark"]
        if a in self.marks[seat]:
            raise Refused(f"{a} is marked; clear it first")
        if a in self.cats:  # D3
            self.score[seat] += 1
            self._place(a, seat)
            return [f"seat {seat}: a cat at {a} (+1)"]
        self.hearts[seat] -= 1  # D4
        out = " and is out" if not self.hearts[seat] else ""
        return [f"seat {seat}: not {a}; {self.hearts[seat]} heart(s) left{out}"]

    def _place(self, a: str, seat) -> None:
        self.placed[a] = seat
        for m in self.marks:
            m.discard(a)  # D5

    def _pass(self) -> None:
        if self.over:
            return
        for step in range(1, SEATS + 1):  # D1: skip a seat that is out
            nxt = (self.turn + step) % SEATS
            if self.hearts[nxt]:
                self.turn = nxt
                return

    # -- the record --------------------------------------------------------

    def record(self) -> dict:
        return {"mode": "duel", "seed": self.seed, "n": self.board.n, "k": self.board.k,
                "board": self.board.digest(), "moves": [list(m) for m in self.moves],
                "score": list(self.score), "hearts": list(self.hearts)}


def replay(record: dict) -> Duel:
    d = Duel(record["seed"], record["n"], record.get("k", 1))
    if d.board.digest() != record["board"]:
        raise ValueError("this board isn't the one the record names")
    for seat, *move in record["moves"]:
        d.step(seat, tuple(move))
    return d


def _seat(seat) -> None:
    if isinstance(seat, bool) or seat not in range(SEATS):
        raise Refused(f"a duel has seats 0 and 1, not {seat!r}")
