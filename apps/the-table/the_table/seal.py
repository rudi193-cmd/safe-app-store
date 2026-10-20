"""seal.py -- the one seal check the table takes (flatten F3).

A decision beat moves only on the human's answer, read through the one-script
(``table.beat_seal``, bound to a box): ``sealed`` or ``rejected``, each a seal
row whose own proof (or Nestor pair) re-checks, over the beat's proposal
(``rejected`` is the human's seal over ``reject:<subject>``). Anything else --
``unsealed``, ``unreachable``, a name, a label -- moves nothing.

``verdict_of`` is that check, held in one place: the answer's state, and that
what was sealed is THIS beat (B2): its path is this world's fact path and its
data this beat's fact, so a seal over another beat or another world's
``s1::b3`` moves nothing. ``StorySession.seal`` calls it; nothing else
decides.

The name list that used to stand here (``NOT_A_PERSON``) retired with F3: a
name is a label, and a label was never a seal (SPEC-rival §3 row 7, A5).
"""
from __future__ import annotations

from .host import onescript_module

#: The two answers that move a beat, and the verdict each records.
VERDICTS = {"sealed": "SEALED", "rejected": "REJECTED"}


class BeatNotSealed(RuntimeError):
    """The human's answer over a decision beat's proposal does not re-check,
    or is not over this beat."""


def beat_path(pending: dict) -> str:
    """Where one-script writes a sealed beat: ``world/<world id>/<fact id>.md``.
    One copy, the one script's ``table.beat_path`` (flatten F5; it was
    restated here while the-table imported no onescript). A beat names its
    world; one with none is a ``KeyError``, never ``world/None/``."""
    return onescript_module("table").beat_path(pending)


def verdict_of(answer: object, pending: dict) -> tuple[str, str]:
    """``(verdict, by)`` for the human's answer over ``pending`` (a beat that
    names its world), or ``BeatNotSealed`` with why."""
    state = answer.get("state") if isinstance(answer, dict) else None
    if state not in VERDICTS:
        why = answer.get("why", "") if isinstance(answer, dict) else repr(answer)
        raise BeatNotSealed(
            f"the beat {pending.get('fact_id')!r} is not sealed by a proof that "
            f"re-checks: {state!r} {why}".strip())
    want = beat_path(pending)
    if answer.get("path") != want or answer.get("data") != pending.get("fact"):
        raise BeatNotSealed(f"the seal is over {answer.get('path')!r}, not this beat ({want!r})")
    return VERDICTS[state], str(answer.get("by") or "human")
