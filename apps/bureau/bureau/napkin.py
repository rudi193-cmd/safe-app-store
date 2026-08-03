"""The napkin, the goo, and the threshold nobody set.

    Precausal goo is matter in the pre-pattern state. Present in the room. Warm
    and slightly luminous. It does not know it is waiting for anything. [...]
    until the pattern density crosses a threshold you did not set and cannot
    predict, and then something declares itself.
        -- oakenscroll-on-the-goo-and-gerald.md

Two mechanics come out of that paragraph directly.

**You cannot perceive the goo while you are still being surprised.** Surprise is
spent, not gained: the narrator starts full of it and each new absurdity costs
one. At zero the narrator has stopped being surprised, which in this building is
a *sensory upgrade* rather than a defeat. This is Bureaucracy's blood-pressure
meter with the sign flipped — Adams kills you for reaching maximum agitation;
here the arc bottoms out and keeps going, per ``gerald-and-the-narrator.md``:
"The narrator has stopped being surprised. They have not stopped showing up."

**A blank napkin is a value.** Gerald declining to write is a recorded fact and
resolves the discrepancy in the other direction. No napkin at all is a different
fact entirely and resolves nothing. ``NO_NAPKIN is not BLANK`` is enforced in
the tests, because conflating those two is how a tool starts lying.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .rng import Rng

STARTING_SURPRISE = 8


class Napkin(Enum):
    """What Gerald left. Three faces; ``BLANK`` is one of them."""

    WORD = "word"  # a single word. Hanz can read it.
    BLANK = "blank"  # Gerald declined, on the record, in napkin form.
    GRAPE = "grape"  # not a napkin. Also not nothing. The goo is not finished.


NO_NAPKIN = None  # the absence. distinct from Napkin.BLANK, forever.

_FACES = (Napkin.WORD, Napkin.WORD, Napkin.WORD, Napkin.BLANK, Napkin.BLANK, Napkin.GRAPE)


@dataclass
class Goo:
    """Pattern density in the room, and the threshold it has not yet crossed.

    The threshold is drawn once, from a seed the narrator never sees, and
    redrawn on a grape. Deterministic under a fixed seed so the suite can reason
    about it; opaque to the player, which is the only property that matters at
    the table.
    """

    seed: int = 0
    surprise: int = STARTING_SURPRISE
    dwell: int = 0  # visits made *after* surprise ran out
    _threshold: int = 0
    _rng: Rng = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._rng = Rng(self.seed)
        self._threshold = self._rng.between(3, 9)

    # ── the narrator's side ────────────────────────────────────────────────────
    def spend_surprise(self) -> bool:
        """Show up once more. Returns True if it cost you anything."""
        if self.surprise <= 0:
            return False
        self.surprise -= 1
        return True

    @property
    def visible(self) -> bool:
        """Can the narrator see the goo yet?"""
        return self.surprise <= 0

    # ── the room's side ────────────────────────────────────────────────────────
    def tick(self) -> Napkin | None:
        """One more visit. Returns a napkin iff a threshold crossed just now.

        Returns ``NO_NAPKIN`` in every other case, including every visit made
        while the narrator is still capable of being surprised.
        """
        if not self.visible:
            return NO_NAPKIN
        self.dwell += 1
        if self.dwell < self._threshold:
            return NO_NAPKIN
        face = self._rng.pick(_FACES)
        if face is Napkin.GRAPE:
            # Gerald declines to conclude. The wait resets, to a new length you
            # did not set and still cannot predict.
            self.dwell = 0
            self._threshold = self._rng.between(3, 9)
        return face


DECLARATION = {
    Napkin.WORD: (
        "Gerald writes one word on a napkin and puts it down without pushing it "
        "toward you, because pushing it toward you would be imposing narrative."
    ),
    Napkin.BLANK: (
        "Gerald takes out a napkin. Gerald looks at it for some time. Gerald puts "
        "it down, unmarked, squared to the edge of the table, and it is "
        "immediately obvious to everyone present that this was deliberate and "
        "that it counts."
    ),
    Napkin.GRAPE: (
        "Gerald does not write on the napkin. Gerald leaves a grape. The room "
        "does not resolve. Something in it has moved, though, and you find you "
        "are willing to come back."
    ),
}
