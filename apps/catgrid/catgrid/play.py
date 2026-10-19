"""The playable surface: one board, its cells, three hearts.

The rules, each enforced in ``Game.step`` and refused with ``Refused``:

====  ==========================================================================
R1    A move names a cell on this board (``A1`` ...). Anything else is refused.
R2    ``cat <cell>`` on an empty cell. Right when the board's one answer has a
      cat there; then it stays.
R3    A wrong cat costs a heart and is not placed. Every cat that breaks a rule
      (a second in a row, column or region, or one touching another) is wrong,
      because the one answer breaks none; so are cats that break nothing yet
      but are not the answer.
R4    ``x <cell>`` marks an empty cell "no cat here". Free: it costs nothing and
      claims nothing. ``clear <cell>`` takes an x back off.
R5    Nothing goes on a cell that holds a cat; an x can't be cleared where none is.
R6    Three hearts. At none the game is lost.
R7    All n cats placed: the game is won.
R8    Once won or lost, every move is refused.
====  ==========================================================================

R3 is the reading of the original (Meowdoku: "wrong placements cost hearts")
that needs a board with exactly one answer; ``board.generate`` makes no other
kind. The core takes no input and prints nothing; ``main`` is the terminal.
"""
from __future__ import annotations

import sys

from .board import Board, generate

HEARTS = 3
CAT, X, EMPTY = "cat", "x", ""
MOVES = ("cat", "x", "clear")


class Refused(ValueError):
    """A move the rules don't allow. The state is unchanged."""


class Game:
    def __init__(self, board: Board) -> None:
        self.board = board
        self.cells = {a: EMPTY for a in board.addresses()}
        self.hearts = HEARTS
        self.status = "playing"

    @classmethod
    def new(cls, seed: int, n: int) -> "Game":
        return cls(generate(seed, n))

    # -- the rules -----------------------------------------------------------
    def _answer(self, addr: str) -> bool:
        i = self.board.index(addr)
        r, c = divmod(i, self.board.n)
        return self.board.solution[r] == c

    def legal_moves(self) -> list:
        if self.status != "playing":
            return []
        out = []
        for a, v in self.cells.items():
            if v == EMPTY:
                out += [("cat", a), ("x", a)]
            elif v == X:
                out.append(("clear", a))
        return out

    def step(self, move) -> list:
        """Play one move; returns what happened, as lines. Refused leaves the
        game exactly as it was."""
        if self.status != "playing":
            raise Refused(f"the game is {self.status}; no more moves")  # R8
        if not (isinstance(move, (list, tuple)) and len(move) == 2 and move[0] in MOVES):
            raise Refused(f"a move is (cat|x|clear, cell), not {move!r}")
        verb, addr = move
        if addr not in self.cells:
            raise Refused(f"{addr!r} is not a cell on this board")  # R1
        here = self.cells[addr]
        if here == CAT:
            raise Refused(f"{addr} already holds a cat")  # R5
        if verb == "x":
            if here == X:
                raise Refused(f"{addr} is already marked")
            self.cells[addr] = X  # R4
            return [f"{addr}: marked, no cat here"]
        if verb == "clear":
            if here != X:
                raise Refused(f"{addr} has no mark to clear")  # R5
            self.cells[addr] = EMPTY
            return [f"{addr}: cleared"]
        if here == X:
            raise Refused(f"{addr} is marked; clear it first")
        if not self._answer(addr):  # R3
            self.hearts -= 1
            if self.hearts == 0:  # R6
                self.status = "lost"
                return [f"{addr}: not here. No hearts left; the board wins"]
            return [f"{addr}: not here. {self.hearts} heart(s) left"]
        self.cells[addr] = CAT  # R2
        if sum(v == CAT for v in self.cells.values()) == self.board.n:  # R7
            self.status = "won"
            return [f"{addr}: a cat. Every row, column and region has one: solved"]
        return [f"{addr}: a cat"]

    # -- what a player sees --------------------------------------------------
    def state(self) -> dict:
        """Everything a player can see, and nothing they can't: never the answer."""
        return {
            "n": self.board.n,
            "regions": list(self.board.regions),
            "cells": dict(self.cells),
            "hearts": self.hearts,
            "status": self.status,
        }

    def render(self) -> str:
        n = self.board.n
        head = "    " + " ".join(f"{c + 1:>2}" for c in range(n))
        rows = [head]
        for r, name in enumerate(dict.fromkeys(a.rstrip("0123456789") for a in self.cells)):
            line = []
            for c in range(n):
                v = self.cells[f"{name}{c + 1}"]
                reg = self.board.regions[r * n + c]
                line.append(" @" if v == CAT else " x" if v == X else f"{reg:>2}")
            rows.append(f"{name:>3} " + " ".join(line))
        rows.append(f"hearts: {self.hearts}   {self.status}")
        return "\n".join(rows)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    seed = int(args[0]) if args else 1
    n = int(args[1]) if len(args) > 1 else 6
    game = Game.new(seed, n)
    print(f"catgrid {n}x{n}, seed {seed}. Moves: cat A1 | x A1 | clear A1 | quit")
    print("Numbers are regions; one cat per row, column and region; no two touch.")
    while game.status == "playing":
        print(game.render())
        try:
            line = input("> ").split()
        except EOFError:
            return 0
        if line[:1] == ["quit"]:
            return 0
        try:
            for said in game.step(tuple(line)):
                print(said)
        except Refused as e:
            print(f"refused: {e}")
    print(game.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
