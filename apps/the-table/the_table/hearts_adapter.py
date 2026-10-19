"""``GameSession`` over game-lab's Hearts rules: one hand, four seats.

The first trick-taking game at the table. the-table is the CONSUMER, the way
``crazy_eights_adapter.py`` is: it imports game-lab's pure Hearts helpers
through the same one-directory path shim and never modifies
``apps/game-lab``. ``apps/game-lab/sims/hearts.py`` guards its demo run behind
``if __name__ == '__main__':``, so importing it only defines functions.

REUSE: every legality decision is game-lab's ``legal_plays`` (follow suit,
2 of clubs leads, hearts not led until broken, no points on the first trick
unless forced); the deck is its ``make_deck``, points its ``card_points``, and
where a pass goes its ``pass_direction`` / ``target_seat``.

RESTATED, with a named middle: game-lab's ``play_hand`` resolves a trick (the
highest card of the suit led wins and leads next) and shoots the moon (all 13
hearts and the queen of spades: 0 for the shooter, 26 for everyone else)
inside its own self-play loop, so they can't be called one step at a time.
Those few lines are restated here; ``tests/test_hearts_adapter.py`` plays the
same deal through this adapter and through ``play_hand`` with game-lab's
deterministic "john" policy and asserts the same points, so the two cannot
drift apart unnoticed.

One session is ONE hand (hand 0: the pass goes left), not a race to 100: a
hand is the unit a GM can drive and a ledger can hold, and it ends.

Turn model (seats = 4):
  * pass phase: seats 0..3 in turn each choose three cards,
    ``("pass", card, card, card)``. A chosen pass is hidden from every other
    seat; once all four have chosen, each pass lands in its target's hand.
  * play phase: the 2 of clubs leads; then clockwise. ``("play", card)``.
    After four cards the trick's winner takes its points and leads.
  * Terminal after 13 tricks. ``result()``: the seats with the fewest points
    win (a tie is shared); ``scores`` are each seat's points, lower better.

Hidden information: ``observe(seat)`` shows the seat's own hand and its own
chosen pass, the trick on the table, tricks taken and points so far; never
another seat's hand or pass.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from itertools import combinations

from .crazy_eights_adapter import _ensure_game_lab_sims_on_path

_ensure_game_lab_sims_on_path()

from hearts import (  # noqa: E402  (after the shared shim, on purpose)
    QUEEN_SPADES,
    card_points,
    legal_plays,
    make_deck,
    pass_direction,
    target_seat,
)

from .game_session import Observation, Result  # noqa: E402
from .stream import seed_label  # noqa: E402

HAND_NUMBER = 0  # one hand per session: the pass goes left


def trick_winner(trick: list) -> int:
    """The seat whose card is highest in the suit led (play_hand's rule)."""
    lead = trick[0][1][1]
    return max((t for t in trick if t[1][1] == lead), key=lambda t: t[1][0])[0]


def moon(points: list, hearts: list, queen: list) -> list:
    """play_hand's shoot-the-moon: one seat took all 13 hearts and the queen."""
    for i in range(4):
        if hearts[i] == 13 and queen[i]:
            return [0 if j == i else 26 for j in range(4)]
    return list(points)


class HeartsSession:
    """``GameSession`` adapter over game-lab's Hearts rule functions."""

    seats = 4

    def __init__(self, rng_factory: Callable | None = None) -> None:
        self._rng_factory = rng_factory
        self._hands: list | None = None

    # -- GameSession -----------------------------------------------------

    def reset(self, seed: int) -> Observation:
        rng = self._rng_factory(seed) if self._rng_factory else random.Random(seed)
        deck = make_deck()
        rng.shuffle(deck)  # own rng: never the global ``random`` hearts.deal uses
        self._hands = [sorted(deck[i * 13:(i + 1) * 13]) for i in range(4)]
        self._direction = pass_direction(HAND_NUMBER)
        self._passes: list = [None] * 4
        self._phase = "pass"
        self._turn = 0
        self._trick: list = []
        self._tricks = 0
        self._broken = False
        self._points = [0] * 4
        self._hearts = [0] * 4
        self._queen = [False] * 4
        self._taken = [0] * 4
        self._final: list | None = None
        return Observation(seat=0, view=self._view(0), terminal=False, narration=[
            f"New hand of Hearts ({seed_label(rng, seed)}). Pass three cards left."])

    def current_seat(self) -> int:
        self._require()
        return self._turn

    def observe(self, seat: int) -> Observation:
        self._require(seat)
        return Observation(seat=seat, view=self._view(seat), narration=[],
                           terminal=self._final is not None)

    def legal_moves(self, seat: int) -> list:
        """Side-effect-free; empty for a seat not on turn."""
        self._require(seat)
        if self._final is not None or seat != self._turn:
            return []
        hand = self._hands[seat]
        if self._phase == "pass":
            return [("pass", *[list(c) for c in three]) for three in combinations(hand, 3)]
        return [("play", list(c)) for c in
                legal_plays(hand, self._trick, self._broken, self._tricks == 0)]

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        if self._final is not None:
            raise RuntimeError("step() called on a finished hand")
        if seat != self._turn:
            raise ValueError(f"it is seat {self._turn}'s turn, not {seat!r}")
        if not isinstance(move, (list, tuple)) or not move:
            raise ValueError(f"unknown move {move!r}")
        if self._phase == "pass" and move[0] == "pass" and len(move) == 4:
            said = self._pass(seat, [_card(c) for c in move[1:]])
        elif self._phase == "play" and move[0] == "play" and len(move) == 2:
            said = self._play(seat, _card(move[1]))
        else:
            raise ValueError(f"{move!r} is not a {self._phase} move")
        nxt = self._turn
        return Observation(seat=nxt, view=self._view(nxt), narration=said,
                           terminal=self._final is not None)

    def is_terminal(self) -> bool:
        self._require()
        return self._final is not None

    def result(self) -> Result:
        self._require()
        if self._final is None:
            return Result(winners=[], scores={}, summary="unfinished")
        low = min(self._final)
        winners = [s for s in range(4) if self._final[s] == low]
        return Result(winners=winners, scores={s: float(p) for s, p in enumerate(self._final)},
                      summary="points (lower is better): " + ", ".join(
                          f"seat {s} {p}" for s, p in enumerate(self._final)))

    # -- the phases --------------------------------------------------------

    def _pass(self, seat: int, cards: list) -> list:
        hand = self._hands[seat]
        if len(set(cards)) != 3 or any(c not in hand for c in cards):
            raise ValueError("a pass is three different cards from your own hand")
        self._passes[seat] = cards
        if seat < 3:
            self._turn = seat + 1
            return [f"seat {seat} chooses three cards to pass"]
        for s in range(4):
            for c in self._passes[s]:
                self._hands[s].remove(c)
        for s in range(4):
            self._hands[target_seat(s, self._direction)].extend(self._passes[s])
        for h in self._hands:
            h.sort()
        self._phase = "play"
        self._turn = next(s for s in range(4) if (2, "C") in self._hands[s])
        return [f"seat {seat} chooses three cards to pass", "the passes go left",
                f"seat {self._turn} holds the 2 of clubs and leads"]

    def _play(self, seat: int, card: tuple) -> list:
        legal = legal_plays(self._hands[seat], self._trick, self._broken, self._tricks == 0)
        if card not in legal:
            raise ValueError(f"{card!r} is not a legal play here")
        self._hands[seat].remove(card)
        self._broken = self._broken or card[1] == "H"
        self._trick.append((seat, card))
        said = [f"seat {seat} plays {_name(card)}"]
        if len(self._trick) < 4:
            self._turn = (seat + 1) % 4
            return said
        won = trick_winner(self._trick)
        pts = sum(card_points(c) for _, c in self._trick)
        self._points[won] += pts
        self._taken[won] += 1
        for _, c in self._trick:
            self._hearts[won] += c[1] == "H"
            self._queen[won] = self._queen[won] or c == QUEEN_SPADES
        said.append(f"seat {won} takes the trick ({pts} point(s))")
        self._trick, self._tricks, self._turn = [], self._tricks + 1, won
        if self._tricks == 13:
            self._final = moon(self._points, self._hearts, self._queen)
            if self._final != self._points:
                said.append(f"seat {self._final.index(0)} shoots the moon")
        return said

    # -- internal ----------------------------------------------------------

    def _view(self, seat: int) -> dict:
        return {
            "seat": seat,
            "phase": self._phase,
            "hand": [list(c) for c in self._hands[seat]],
            "my_pass": [list(c) for c in self._passes[seat]] if self._passes[seat] else None,
            "trick": [[s, list(c)] for s, c in self._trick],
            "tricks_played": self._tricks,
            "tricks_taken": list(self._taken),
            "points": list(self._points),
            "hearts_broken": self._broken,
            "hand_sizes": [len(h) for h in self._hands],
            "current_seat": None if self._final is not None else self._turn,
        }

    def _require(self, seat: int | None = None) -> None:
        if self._hands is None:
            raise RuntimeError("reset(seed) must be called before use")
        if seat is not None and (isinstance(seat, bool) or seat not in (0, 1, 2, 3)):
            raise ValueError(f"hearts is 4-seat; seat must be 0-3, got {seat!r}")


def _card(raw) -> tuple:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"a card is [rank, suit], not {raw!r}")
    return (raw[0], raw[1])


def _name(card: tuple) -> str:
    rank = {11: "J", 12: "Q", 13: "K", 14: "A"}.get(card[0], str(card[0]))
    return f"{rank}{card[1]}"
