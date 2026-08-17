"""``GameSession`` over game-lab's real Crazy Eights rule logic.

the-table is the CONSUMER here, exactly the same relationship
``bureau_adapter.py`` has to bureau: it imports game-lab's pure Crazy Eights
helpers, never the reverse, and never modifies anything under
``apps/game-lab``. game-lab is not installed as a package, so the only way to
reach it is a path shim -- see ``_ensure_game_lab_sims_on_path`` below, the
same narrow one-directory-once pattern ``bureau_adapter.py`` uses for
``apps/bureau``. ``apps/game-lab/sims/crazy_eights.py`` guards its demo run
behind ``if __name__ == '__main__':`` (see the bottom of that file), so
importing it only defines functions/constants -- no side effects.

REUSE, NOT REIMPLEMENTATION: every legality decision in this adapter is
delegated to game-lab's own ``is_legal`` / ``legal_cards`` (and its
``make_deck`` for the 52-card deck and ``SUITS`` for suit enumeration). This
module owns none of the Crazy Eights *rules* -- it owns the turn-by-turn
*loop* around them, expressed as a steppable ``GameSession``.

WHY THE LOOP DIFFERS FROM game-lab's OWN SELF-PLAY (documented, not hidden):
game-lab's ``play_hand()`` self-plays a whole hand with a *global* policy
and, when a seat can't play, draws-until-playable-or-empty inside a single
ply. the-table's ``GameSession`` contract instead requires ``legal_moves()``
to be side-effect-free and ``step()`` to apply exactly one move, so drawing
is modeled here as its own forced single-card ``("draw",)`` step: a seat that
can't play draws one card, control returns to the GM loop, and
``legal_moves()`` is recomputed against the now-larger hand. This means
the-table will NOT reproduce game-lab's own baseline numbers (its
`avg_plies`, its ply accounting) -- that is expected and correct, not a bug:
the-table is not re-running game-lab's baseline, it is driving the *same
rules* through the uniform protocol, and one card per step means every draw
is its own auditable ledger row (``ledger_sink.py`` snapshots each ``step``).

Reproducibility: this adapter owns its own ``random.Random(seed)`` instance
in ``reset()`` and never touches the global ``random`` module (game-lab's
``play_hand()`` calls the global ``random.shuffle`` -- we deliberately do
not, so a the-table seed is deterministic and independent of anything
game-lab or anyone else does to the global RNG state).

Turn model (seats = 4, pinned):
  * Deal 5 cards to each of 4 seats, flip 1 card to start the discard pile;
    its suit is the initial ``active_suit`` (an 8 flip's own suit still
    applies -- there is no separate case, ``active_suit`` is always the
    flipped card's suit).
  * ``legal_moves(seat)`` (side-effect-free, computed fresh from current
    state each call):
      - has >=1 legal card (via game-lab's ``legal_cards``): one
        ``("play", card, suit_call)`` move per legal card -- an 8 offers one
        move per suit in ``SUITS`` (``suit_call`` set), a non-8 offers one
        move with ``suit_call=None``.
      - else, stock non-empty: the single forced move ``("draw",)``.
      - else (no legal card, empty stock): the single forced move
        ``("pass",)``.
  * ``step(seat, move)``:
      - ``("play", card, suit_call)``: removes ``card`` from the seat's
        hand, sets it as the new discard top, sets ``active_suit`` to
        ``suit_call`` if the card's rank is 8 (else the card's own suit).
        Empty hand afterwards -> that seat wins, game terminal, turn does
        NOT advance. Otherwise turn advances to ``(seat + 1) % 4``.
      - ``("draw",)``: pops one card from the stock into the seat's hand.
        Turn does NOT advance -- the same seat is asked to move again, and
        ``legal_moves()`` reflects the newly drawn card.
      - ``("pass",)``: turn advances to ``(seat + 1) % 4``.
  * Terminal: a seat emptied its hand (see above), OR a stall -- 4
    consecutive ``("pass",)`` steps (stock empty, nobody can move) -- OR a
    defensive turn cap (``_DEFENSIVE_TURN_CAP``) is hit, which is treated
    the same as a stall (no trustworthy winner).
  * ``result()``: a winner -> ``Result(winners=[w], scores={w: 1.0}, ...)``.
    Stall / cap-out -> ``Result(winners=[], scores={}, summary="stalled")``.

Hidden information: ``observe(seat)`` (and the ``Observation`` a ``step()``
returns) exposes only the acting/observing seat's OWN hand, never another
seat's cards -- opponents are represented purely as hand-size counts. bureau
is single-player and can't showcase this; Crazy Eights, with 4 seats and
real hidden hands, is the first place the-table's per-seat ``observe()``
actually matters.

Move vocabulary (JSON-serializable tuples, per the pinned contract):
  ("play", (rank, suit), suit_call_or_None)
  ("draw",)
  ("pass",)
"""
from __future__ import annotations

import random
import sys
from pathlib import Path


def _ensure_game_lab_sims_on_path() -> None:
    """Put apps/game-lab/sims on sys.path so ``from crazy_eights import ...``
    works, without installing game-lab as a package and without touching
    anything under apps/game-lab itself.

    Resolved relative to this file:
    apps/the-table/the_table/crazy_eights_adapter.py -> repo root is three
    parents up -> apps/game-lab/sims is the sibling directory holding the
    module.
    """
    repo_root = Path(__file__).resolve().parents[3]
    sims_dir = repo_root / "apps" / "game-lab" / "sims"
    sims_str = str(sims_dir)
    if sims_str not in sys.path:
        sys.path.insert(0, sims_str)


_ensure_game_lab_sims_on_path()

from crazy_eights import SUITS, is_legal, legal_cards, make_deck  # noqa: E402

from .game_session import Observation, Result

# Defensive cap on total steps in a single game -- independent of, and much
# larger than, any realistic game (52-card deck, 20 dealt, <=31 ever drawn
# from stock, the rest plays/passes). Exists purely so a latent bug can never
# spin this adapter forever; a real game never gets remotely close to it.
_DEFENSIVE_TURN_CAP = 1000


class CrazyEightsSession:
    """``GameSession`` adapter over game-lab's Crazy Eights rule functions."""

    seats = 4

    def __init__(self) -> None:
        self._hands: list | None = None
        self._stock: list | None = None
        self._discard_top: tuple | None = None
        self._active_suit: str | None = None
        self._turn: int = 0
        self._consecutive_passes: int = 0
        self._winner: int | None = None
        self._terminal: bool = False
        self._steps_taken: int = 0

    # -- GameSession -----------------------------------------------------

    def reset(self, seed: int) -> Observation:
        rng = random.Random(seed)  # OWN rng -- never touches the global `random` module
        deck = make_deck()
        rng.shuffle(deck)

        self._hands = [deck[i * 5:(i + 1) * 5] for i in range(4)]
        stock = deck[20:]
        top = stock.pop(0)
        self._stock = stock
        self._discard_top = top
        self._active_suit = top[1]  # an 8 flip's own suit is still the active suit
        self._turn = 0
        self._consecutive_passes = 0
        self._winner = None
        self._terminal = False
        self._steps_taken = 0

        narration = [
            f"New Crazy Eights game (seed={seed}). "
            f"Top card: {tuple(top)}, active suit: {self._active_suit}.",
        ]
        return Observation(
            seat=0,
            view=self._view(0),
            narration=narration,
            terminal=False,
        )

    def current_seat(self) -> int:
        self._require_reset()
        return self._turn

    def observe(self, seat: int) -> Observation:
        self._require_reset()
        self._require_seat(seat)
        return Observation(
            seat=seat,
            view=self._view(seat),
            narration=[],
            terminal=self._terminal,
        )

    def legal_moves(self, seat: int) -> list:
        """Side-effect-free: computed fresh from current state, no mutation."""
        self._require_reset()
        self._require_seat(seat)
        if self._terminal:
            return []

        top_rank, top_suit = self._discard_top
        hand = self._hands[seat]
        playable = legal_cards(hand, top_rank, top_suit, self._active_suit)

        if playable:
            moves: list = []
            for card in playable:
                if card[0] == 8:
                    for suit in SUITS:
                        moves.append(("play", card, suit))
                else:
                    moves.append(("play", card, None))
            return moves
        if self._stock:
            return [("draw",)]
        return [("pass",)]

    def step(self, seat: int, move) -> Observation:
        self._require_reset()
        self._require_seat(seat)
        if self._terminal:
            raise RuntimeError("step() called on a terminal game")
        if seat != self._turn:
            raise ValueError(f"it is seat {self._turn}'s turn, not {seat!r}")

        verb = move[0]
        narration: list = []

        if verb == "play":
            _, raw_card, suit_call = move
            card = tuple(raw_card)
            top_rank, top_suit = self._discard_top
            if not is_legal(card, top_rank, top_suit, self._active_suit):
                raise ValueError(f"{card!r} is not legal on {self._discard_top!r}/{self._active_suit!r}")
            hand = self._hands[seat]
            hand.remove(card)  # ValueError if not actually in hand
            self._discard_top = card
            self._active_suit = suit_call if card[0] == 8 else card[1]
            self._consecutive_passes = 0
            narration.append(
                f"seat {seat} plays {card}"
                + (f", calls {suit_call}" if card[0] == 8 else "")
            )
            if not hand:
                self._winner = seat
                self._terminal = True
                narration.append(f"seat {seat} empties their hand -- wins")
            else:
                self._turn = (seat + 1) % 4

        elif verb == "draw":
            if not self._stock:
                raise ValueError("cannot draw: stock is empty")
            card = self._stock.pop()
            self._hands[seat].append(card)
            narration.append(f"seat {seat} draws")
            # turn does NOT advance -- same seat moves again

        elif verb == "pass":
            self._consecutive_passes += 1
            narration.append(f"seat {seat} passes")
            self._turn = (seat + 1) % 4
            if self._consecutive_passes >= 4 and not self._stock:
                self._terminal = True
                narration.append("all 4 seats passed in a row with an empty stock -- stalled")

        else:
            raise ValueError(f"unknown move verb {verb!r} in {move!r}")

        self._steps_taken += 1
        if not self._terminal and self._steps_taken >= _DEFENSIVE_TURN_CAP:
            self._terminal = True
            narration.append(f"defensive turn cap ({_DEFENSIVE_TURN_CAP}) reached -- stalled")

        return Observation(
            seat=seat,
            view=self._view(seat),
            narration=narration,
            terminal=self._terminal,
        )

    def is_terminal(self) -> bool:
        self._require_reset()
        return self._terminal

    def result(self) -> Result:
        self._require_reset()
        if self._winner is not None:
            return Result(
                winners=[self._winner],
                scores={self._winner: 1.0},
                summary=f"seat {self._winner} emptied their hand",
            )
        return Result(winners=[], scores={}, summary="stalled")

    # -- internal ----------------------------------------------------------

    def _view(self, seat: int) -> dict:
        """The per-seat view: own hand in full, opponents as counts only."""
        hand = self._hands[seat]
        opponent_hand_sizes = [len(self._hands[s]) for s in range(4) if s != seat]
        return {
            "seat": seat,
            "hand": [list(card) for card in hand],
            "discard_top": list(self._discard_top),
            "active_suit": self._active_suit,
            "stock_count": len(self._stock),
            "opponent_hand_sizes": opponent_hand_sizes,
            "current_seat": self._turn,
        }

    def _require_reset(self) -> None:
        if self._hands is None:
            raise RuntimeError("reset(seed) must be called before use")

    def _require_seat(self, seat: int) -> None:
        if seat not in (0, 1, 2, 3):
            raise ValueError(f"crazy eights is 4-seat; seat must be 0-3, got {seat!r}")
