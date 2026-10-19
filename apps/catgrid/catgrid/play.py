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
R7    All n x k cats placed: the game is won.
R8    Once won or lost, every move is refused.
R9    ``hint`` places one sure cat (the first row still without one) and never
      costs a heart. Each board gives one free hint; trivia earns more. With
      none to spend, it is refused.
R10   ``trivia`` asks a question from Jeles (``trivia.ask``), drawn from the
      seed. Refused with one already waiting, or when there is no bank.
R11   ``answer A..D`` answers it. Right earns a hint; wrong costs nothing.
      Refused with no question waiting.
R12   Marking x on the cell a napkin hides under (``eggs.hide``) finds it,
      once. The napkin's cell is never shown before.
====  ==========================================================================

R3 is the reading of the original (Meowdoku: "wrong placements cost hearts")
that needs a board with exactly one answer; ``board.generate`` makes no other
kind. The core takes no input and prints nothing; ``main`` is the terminal.
"""
from __future__ import annotations

import sys

from . import eggs, trivia
from .board import Board, address, generate

HEARTS = 3
FREE_HINTS = 1
CAT, X, EMPTY = "cat", "x", ""
CELL_MOVES = ("cat", "x", "clear")


class Refused(ValueError):
    """A move the rules don't allow. The state is unchanged."""


class Game:
    """One board in play. ``bank`` (Jeles trivia) and ``words`` (napkins) are
    handed in, never read here: absent, trivia and eggs say ``unavailable``
    and why, and the board plays the same."""

    def __init__(self, board: Board, seed: int = 0, *, bank: list | None = None,
                 words: list | None = None, bank_why: str = "no trivia bank given",
                 words_why: str = "no napkin words given") -> None:
        self.board = board
        self.seed = seed
        self.cells = {a: EMPTY for a in board.addresses()}
        self.hearts = HEARTS
        self.status = "playing"
        self.hints = {"free": FREE_HINTS, "earned": 0}
        self.bank = list(bank or [])
        self.bank_why = "" if self.bank else bank_why
        self.question: dict | None = None
        self.asked: list = []  # [{id, said, right}] in order
        self.words = list(words or [])
        empties = [a for a in board.addresses() if not self._answer(a)]
        self.egg = eggs.hide(seed, self.words, empties)
        self.words_why = "" if words else words_why
        self.found: list = []
        self.moves: list = []  # every move the game accepted, in order

    @classmethod
    def new(cls, seed: int, n: int, k: int = 1, **kw) -> "Game":
        return cls(generate(seed, n, k=k), seed, **kw)

    # -- the rules -----------------------------------------------------------
    def _answer(self, addr: str) -> bool:
        return self.board.index(addr) in self._cats

    @property
    def _cats(self) -> set:
        if not hasattr(self, "_cat_cells"):
            self._cat_cells = self.board.cats()
        return self._cat_cells

    def legal_moves(self) -> list:
        if self.status != "playing":
            return []
        out = []
        for a, v in self.cells.items():
            if v == EMPTY:
                out += [("cat", a), ("x", a)]
            elif v == X:
                out.append(("clear", a))
        if self.hints["free"] + self.hints["earned"]:
            out.append(("hint",))
        if self.bank and self.question is None:
            out.append(("trivia",))
        if self.question is not None:
            out += [("answer", label) for label in trivia.LABELS]
        return out

    def _sure(self) -> str:
        """The first answer cell, row by row, still without its cat."""
        for i in sorted(self._cats):
            a = address(*divmod(i, self.board.n))
            if self.cells[a] != CAT:
                return a
        raise AssertionError("no answer cell without a cat while playing")  # R7 ends it first

    def step(self, move) -> list:
        """Play one move; returns what happened, as lines. Refused leaves the
        game exactly as it was."""
        if self.status != "playing":
            raise Refused(f"the game is {self.status}; no more moves")  # R8
        if isinstance(move, (list, tuple)) and len(move) == 1 and move[0] in ("hint", "trivia"):
            said = self._hint() if move[0] == "hint" else self._trivia()
        elif isinstance(move, (list, tuple)) and len(move) == 2 and move[0] == "answer":
            said = self._answer_trivia(move[1])
        elif isinstance(move, (list, tuple)) and len(move) == 2 and move[0] in CELL_MOVES:
            said = self._cell(*move)
        else:
            raise Refused(f"a move is (cat|x|clear, cell), (hint), (trivia) or (answer, A-D), not {move!r}")
        self.moves.append(list(move))
        return said

    def _hint(self) -> list:
        if not self.hints["free"] + self.hints["earned"]:
            raise Refused("no hints left; answer trivia to earn one")  # R9
        kind = "free" if self.hints["free"] else "earned"
        self.hints[kind] -= 1
        a = self._sure()
        if self.cells[a] == X:
            self.cells[a] = EMPTY  # a mark on the answer was wrong; the hint lifts it
        return [f"hint ({kind}): {a} holds a cat"] + self._place(a)

    def _trivia(self) -> list:
        if not self.bank:
            raise Refused(f"no trivia: {self.bank_why}")  # R10
        if self.question is not None:
            raise Refused("a question is already waiting for its answer")  # R10
        self.question = trivia.ask(self.bank, self.seed, len(self.asked))
        q = self.question
        return [q["question"]] + [f"  {k}. {v}" for k, v in q["options"].items()]

    def _answer_trivia(self, label) -> list:
        if self.question is None:
            raise Refused("no question is waiting")  # R11
        if label not in trivia.LABELS:
            raise Refused(f"answer with one of {', '.join(trivia.LABELS)}")
        q, self.question = self.question, None
        right = label == q["right"]
        self.asked.append({"id": q["id"], "said": label, "right": right})
        if right:
            self.hints["earned"] += 1
            return [f"right: {q['right']}. A hint earned"]
        return [f"not quite: it was {q['right']}. No cost"]  # R11

    def _cell(self, verb: str, addr) -> list:
        if not isinstance(addr, str) or addr not in self.cells:
            raise Refused(f"{addr!r} is not a cell on this board")  # R1
        here = self.cells[addr]
        if here == CAT:
            raise Refused(f"{addr} already holds a cat")  # R5
        if verb == "x":
            if here == X:
                raise Refused(f"{addr} is already marked")
            self.cells[addr] = X  # R4
            said = [f"{addr}: marked, no cat here"]
            if self.egg and self.egg[0] == addr and not self.found:  # R12
                self.found.append({"cell": addr, "word": self.egg[1]})
                said.append(f"a napkin under {addr}: {self.egg[1]}")
            return said
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
        return self._place(addr)  # R2

    def _place(self, addr: str) -> list:
        self.cells[addr] = CAT
        if sum(v == CAT for v in self.cells.values()) == self.board.n * self.board.k:  # R7
            self.status = "won"
            return [f"{addr}: a cat. Every row, column and region has one: solved"]
        return [f"{addr}: a cat"]

    # -- what a player sees --------------------------------------------------
    def state(self) -> dict:
        """Everything a player can see, and nothing they can't: never the answer."""
        q = self.question
        return {
            "n": self.board.n,
            "k": self.board.k,
            "regions": list(self.board.regions),
            "cells": dict(self.cells),
            "hearts": self.hearts,
            "status": self.status,
            "hints": dict(self.hints),
            "trivia": (
                {"state": "unavailable", "why": self.bank_why} if not self.bank
                else {"state": "waiting", "question": q["question"],
                      "options": dict(q["options"]), "source": q["source"]} if q
                else {"state": "available", "source": trivia.SOURCE}
            ),
            "napkins": (
                {"state": "unavailable", "why": self.words_why} if self.words_why
                else {"state": "found", "found": [dict(f) for f in self.found]} if self.found
                else {"state": "none found"}
            ),
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
        hints = self.hints["free"] + self.hints["earned"]
        rows.append(f"hearts: {self.hearts}   hints: {hints}   {self.status}")
        return "\n".join(rows)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    seed = int(args[0]) if args else 1
    n = int(args[1]) if len(args) > 1 else 6
    k = int(args[2]) if len(args) > 2 else 1
    bank, bank_why = trivia.load_jeles()
    words, words_why = eggs.load_napkins()
    game = Game.new(seed, n, k, bank=bank, words=words, bank_why=bank_why, words_why=words_why)
    print(f"catgrid {n}x{n}, {k} cat(s) a row, seed {seed}. Moves: cat A1 | x A1 | clear A1 | hint | "
          "trivia | answer A | quit")
    print(f"Numbers are regions; {k} cat(s) per row, column and region; no two touch.")
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
