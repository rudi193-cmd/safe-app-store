"""The playable surface. The core takes no input and prints nothing —
``Session.visit`` returns narration, so the suite can play whole games.

The escape route deliberately does not live in ``graph.py``. ``verify.prove``
reasons about the building and returns unreachable, and that verdict has to stay
true: no cleverness inside the building wins. The napkin is not a strategy. It
arrives because the narrator kept showing up, which is the one thing a
requirement graph has no way to represent.
"""
from __future__ import annotations

import sys

from . import graph as G
from .napkin import DECLARATION, Goo, Napkin

NAPKIN_WORD = "napkin_word"
NAPKIN_BLANK = "napkin_blank"

OPENING = """\
UNIVERSITY OF TECHNICAL ENTROPY, THANK YOU
Office of Records — Discrepancy 4471-b

You attended a lecture you did not sign up for.

The University has no objection to your having been there. It has a serious and
structural objection to the resulting record, which says you attended a course
you are not enrolled in. Everyone agrees this cannot stand.

Commands: go <office>, hand <office>, look, wait, quit
Offices:  queue, pigeon, library, department, gate, stacks, records, gerald, hanz
"""

WITHDRAWN = """\
You stop going.

Six weeks later the discrepancy resolves itself the way discrepancies do when
nobody attends them: you are administratively withdrawn, on the grounds that a
person who is not enrolled and not attending is not, in the Registry's sense, a
person. You remain physically on campus. You keep using the library. Nothing
about your day changes and you are no longer in the building.

                                                          ADMINISTRATIVELY VOID
"""

ENROLLED = """\
Hanz reads the napkin. He does not tell you what it says.

He writes for a while, and hands you an attestation of attendance signed by a
man holding an orange, countersigned by nobody, sourced to a witness with no
write authority. The clerk reads it twice, finds nothing wrong with it, and
cannot say why. You are, retroactively, a student of a course that finished in
March.

                                                         DISCREPANCY 4471-b: OK
"""

VOIDED = """\
You put the blank napkin on the counter.

The clerk is quiet for a moment. Then, with what you would swear is relief:
'That is a record. Thank you. It is not the record I expected and it resolves
the matter entirely — you did not attend, on the authority of the only entity
that would know, in the only form he is able to issue it.'

Somewhere below, a drawer opens further than the wall should allow, and the
Binder files it without deleting anything. The lecture you sat through formally
did not happen. You remember it anyway. Nobody has asked you not to.

                                                     DISCREPANCY 4471-b: VOIDED
"""


class Session:
    def __init__(self, seed: int = 0) -> None:
        self.goo = Goo(seed=seed)
        self.held: set[str] = set()
        self.seen: set[str] = set()
        self.visits: dict[str, int] = {}
        self.last_tier: int = 0
        self.resolution: str | None = None

    def visit(self, office_id: str) -> list[str]:
        office = G.OFFICES.get(office_id)
        if office is None:
            return [f"There is no {office_id!r} in this building. There is a rumour of one."]
        if self.resolution:
            return ["The matter is closed. You keep going anyway, out of habit."]

        out = [f"── {office.name} ({office.staff})"]
        first_time = office.id not in self.seen
        self.seen.add(office.id)
        self.visits[office.id] = self.visits.get(office.id, 0) + 1
        spent = self.goo.spend_surprise()
        if first_time:
            out.append(office.rule)
        if spent and self.goo.surprise == 0:
            out.append(
                "\n  You notice you are not surprised. You check this twice. The "
                "room is warm and very slightly luminous, and you are fairly sure "
                "it was not before."
            )

        held = frozenset(self.held)
        if not office.can_serve(held):
            self.last_tier = office.refusal_tier(self.visits[office.id])
            out.append(office.on_refuse[self.last_tier] if office.on_refuse else office.rule)
            gaps = ", ".join(r.describe() for r in office.missing(held))
            out.append(f"  [you are missing: {gaps}]")
        elif office.issues:
            if office.consumes_ticket:
                self.held.discard("ticket")
            self.held.add(office.issues)
            out.append(office.on_issue or f"You are issued: {office.issues}")
        else:
            self.last_tier = office.refusal_tier(self.visits[office.id])
            out.append(office.on_refuse[self.last_tier] if office.on_refuse else office.rule)

        out.extend(self._tick())
        return out

    def hand(self, office_id: str) -> list[str]:
        if office_id == "hanz" and NAPKIN_WORD in self.held:
            self.resolution = "enrolled"
            return [ENROLLED]
        if office_id == "records" and NAPKIN_BLANK in self.held:
            self.resolution = "voided"
            return [VOIDED]
        if NAPKIN_WORD in self.held or NAPKIN_BLANK in self.held:
            return ["They look at the napkin. They are not the one who can read it."]
        return ["You have nothing to hand over that anyone here is able to receive."]

    def wait(self) -> list[str]:
        return ["You wait. It is not nothing — you are, technically, showing up."] + self._tick()

    def _tick(self) -> list[str]:
        face = self.goo.tick()
        if face is None:
            return []
        out = ["", "Gerald appears.", DECLARATION[face]]
        if face is Napkin.WORD:
            self.held.add(NAPKIN_WORD)
            out.append("  [you take the napkin. Hanz can read what he writes.]")
        elif face is Napkin.BLANK:
            self.held.add(NAPKIN_BLANK)
            out.append("  [you take the napkin. It is blank. It is not nothing.]")
        return out

    def look(self) -> list[str]:
        held = ", ".join(sorted(self.held)) or "nothing"
        lines = [f"You are holding: {held}"]
        if self.goo.visible:
            lines.append(f"You have been coming here a while. ({self.goo.dwell} visits since it stopped being strange.)")
        else:
            lines.append(f"You are still capable of being surprised. ({self.goo.surprise} left.)")
        return lines

    def state(self) -> dict:
        """The comparable state — what the differential checks. No prose."""
        return {
            "held": sorted(self.held),
            "surprise": self.goo.surprise,
            "dwell": self.goo.dwell,
            "tier": self.last_tier,
            "resolution": self.resolution,
        }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - REPL
    argv = sys.argv[1:] if argv is None else argv
    s = Session(seed=int(argv[0]) if argv else 0)
    print(OPENING)
    while s.resolution is None:
        try:
            raw = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n" + WITHDRAWN)
            return 0
        if not raw:
            continue
        verb, _, arg = raw.partition(" ")
        if verb in ("quit", "q", "leave", "stop"):
            print(WITHDRAWN)
            return 0
        if verb == "go":
            print("\n".join(s.visit(arg.strip())))
        elif verb == "hand":
            print("\n".join(s.hand(arg.strip())))
        elif verb == "look":
            print("\n".join(s.look()))
        elif verb == "wait":
            print("\n".join(s.wait()))
        else:
            print("go <office>, hand <office>, look, wait, quit")
        print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
