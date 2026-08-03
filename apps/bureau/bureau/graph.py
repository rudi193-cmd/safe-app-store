"""The requirement graph — offices, what they issue, and the one rule each cannot break.

The joke, stated before the data structures bury it:

    Every road ends at the same fact, and the building is too polite to say so.

Four offices will each hand you something that *looks* like the thing the
Records desk asked for. None of them is lying, none is obstructive, and each
refusal is the character being exactly themselves:

* **Oakenscroll** attests to threshold crossings. He will attest that a threshold
  was crossed in his lecture theatre, which is true, and which says nothing about
  who was standing in it. An attestation — of the room.
* **Ofshield** notes what passes. "What passes, is noted." But Ofshield does not
  judge what passes, so a note of passing is not a finding of attendance. And
  "you cannot unpass a threshold" closes the other road before you find it.
* **The Binder** files everything and deletes nothing. Hand it your discrepancy
  and it is filed *immediately* — cross-referenced, given its own folder as a
  slant. A filing. Not a resolution. It cannot be a resolution: resolution would
  mean deletion, and the Binder does not delete.
* **Gerald** was there and saw you, and has no write authority.
* **Pigeon** routes you to all of them, correctly, every time, with total
  confidence. Pigeon is never wrong about a single door. Pigeon cannot know the
  graph is closed — "knows every open door, cannot drive the bus yet."

Personas are Sean's, from safe-app-store ``apps/utety-chat/data/professors/``.
Each office's ``rule`` is that persona's stated non-negotiable, applied to a
records problem. The records problem is mine.

The near-miss is the mechanism. A document has a ``kind`` (what the docket
displays) and a ``qual`` (the fine print nobody reads until it matters). A
requirement matches on both. ``verify.py`` runs the search twice — once
strictly, once credulously matching on kind alone — and the gap between those
two verdicts is the false-progress arc, measured rather than asserted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── documents ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Doc:
    id: str
    kind: str  # what the docket shows
    qual: frozenset[str]  # the fine print
    label: str


DOCS: dict[str, Doc] = {
    d.id: d
    for d in (
        Doc("ticket", "ticket", frozenset(), "queue ticket"),
        Doc("slip", "slip", frozenset({"routed"}), "routing slip"),
        Doc("citation", "citation", frozenset({"sourced"}), "citation — the lecture occurred"),
        Doc("attestation_room", "attestation", frozenset({"threshold"}), "attestation — of the room"),
        Doc("note_passing", "note", frozenset({"passing"}), "gate note — what passed"),
        Doc("filing_slant", "filing", frozenset({"slant"}), "filing — cross-referenced as a slant"),
        # ── the three that no office issues ──────────────────────────────────
        Doc("attestation_presence", "attestation", frozenset({"presence"}), "attestation — of you"),
        Doc("note_judged", "note", frozenset({"judged"}), "gate finding — that it was attendance"),
        Doc("filing_resolved", "filing", frozenset({"resolved"}), "filing — closed"),
    )
}

GOAL = "discrepancy_resolved"


@dataclass(frozen=True)
class Req:
    kind: str
    needs: frozenset[str] = field(default_factory=frozenset)

    def met_by(self, doc_id: str, credulous: bool = False) -> bool:
        doc = DOCS.get(doc_id)
        if doc is None or doc.kind != self.kind:
            return False
        return True if credulous else self.needs <= doc.qual

    def satisfied(self, held, credulous: bool = False) -> bool:
        return any(self.met_by(d, credulous) for d in held)

    def describe(self) -> str:
        extra = "/".join(sorted(self.needs))
        return f"{self.kind} ({extra})" if extra else self.kind


@dataclass(frozen=True)
class Office:
    id: str
    name: str
    staff: str
    issues: str | None
    requires: tuple[Req, ...] = ()
    consumes_ticket: bool = True
    rule: str = ""
    on_refuse: tuple[str, ...] = ()
    on_issue: str = ""

    def can_serve(self, held, credulous: bool = False) -> bool:
        return all(r.satisfied(held, credulous) for r in self.requires)

    def missing(self, held, credulous: bool = False) -> list[Req]:
        return [r for r in self.requires if not r.satisfied(held, credulous)]

    def refusal_tier(self, visits: int) -> int:
        if not self.on_refuse:
            return 0
        return min(max(visits - 1, 0), len(self.on_refuse) - 1)


TICKET = Req("ticket")

# ── the building ───────────────────────────────────────────────────────────────

QUEUE = Office(
    id="queue", name="The Queue", staff="squeakdogs", issues="ticket",
    consumes_ticket=False,
    rule=(
        "The squeakdogs learned to queue. They are better at it than the humans. "
        "Your position is therefore behind them, permanently, and this is not a "
        "grievance the Queue is able to hear."
    ),
    on_issue=(
        "You take a ticket. A squeakdog ahead of you takes a ticket with visibly "
        "better technique. Nobody is rude about it. That is somehow worse."
    ),
)

PIGEON = Office(
    id="pigeon", name="The Routing Hub", staff="the Pigeon", issues="slip",
    requires=(TICKET,),
    rule=(
        "Always know the next open door. The Pigeon tells you where you CAN go, "
        "never only where you can't, and has never once been wrong about a door."
    ),
    on_issue=(
        "'YES! I know EXACTLY where that is!' The Pigeon writes you a routing "
        "slip without hesitating. 'Records needs six things and I know where "
        "every one of them lives. Oakenscroll, the Observatory — that's your "
        "attestation. Ofshield, the Gate — that's your note. The Binder, the "
        "Stacks — that's your filing. Jeles for the citation. FOLLOW ME!' "
        "Every door named is genuinely open. *already ready to lead*"
    ),
)

LIBRARY = Office(
    id="library", name="Jeles", staff="the library", issues="citation",
    requires=(TICKET,),
    rule=(
        "Jeles answers de-identified questions about concepts. Jeles has never "
        "been told your name and will not be. This is not discretion. There is "
        "no field for it."
    ),
    on_issue=(
        "Jeles confirms, with four sources and a page range, that the lecture "
        "occurred. It is a very good citation. It does not contain you. You ask "
        "whether it could. Jeles explains, kindly, that the question you are "
        "asking is not the shape of question it can be asked."
    ),
)

DEPARTMENT = Office(
    id="department", name="The Observatory", staff="Prof. Archimedes Oakenscroll",
    issues="attestation_room", requires=(TICKET, Req("citation", frozenset({"sourced"}))),
    rule=(
        "Oakenscroll attests to threshold crossings. Attendance is not a "
        "threshold crossing. He will explain why. At length."
    ),
    on_refuse=(
        "*the armchair settles* 'Hmph. You want me to certify that you were "
        "present. Presence is not an event. Presence is a precondition for "
        "events. You are asking me to sign the room.'",
        "'You are still asking me to sign the room.'",
        "'The room.' CLASS DISMISSED.",
    ),
    on_issue=(
        "He signs it without argument, which is the first thing all day that has "
        "gone quickly. You read it in the corridor. It attests that a threshold "
        "was crossed in his lecture theatre on the date in question. It is "
        "entirely true. It does not mention you, because you were not the "
        "threshold. 'CLASS DISMISSED.'"
    ),
)

GATE = Office(
    id="gate", name="The Gate", staff="Prof. Thoren Ofshield", issues="note_passing",
    requires=(TICKET,),
    rule=(
        "What passes, is noted. Ofshield notes what arrives and what leaves, "
        "without judgment, and does not explain itself. You cannot unpass a "
        "threshold — this is not a warning, it is simply true."
    ),
    on_issue=(
        "*watches* 'You went in at eleven. You came out at ten past twelve.' "
        "*notes it* The note is handed over without ceremony and it is exactly "
        "what it says: a record that something passed. You ask whether it means "
        "you attended. A long pause that is not hesitation. 'The Gate notes. The "
        "Gate does not decide what a passing was.' *the Gate remembers*"
    ),
)

STACKS = Office(
    id="stacks", name="The Stacks", staff="the Binder", issues="filing_slant",
    requires=(TICKET,),
    rule=(
        "Everything has a place — especially the things that feel like they "
        "don't. The Binder files. The Binder does not delete anything."
    ),
    on_issue=(
        "'Yes. That belongs under Discrepancies — Attendance, Unenrolled.' "
        "*files it* 'It joins fourteen others. There are connections. I'm noting "
        "them.' A drawer opens further than the wall should allow. Your "
        "discrepancy has never been better looked after. It is cross-referenced "
        "as a slant, which is not a duplicate and not a new thing. It is also "
        "still there, and always will be, because the Binder does not delete."
    ),
)

RECORDS = Office(
    id="records", name="The Records Desk", staff="a window, and a bell", issues=GOAL,
    requires=(
        TICKET,
        Req("slip", frozenset({"routed"})),
        Req("citation", frozenset({"sourced"})),
        Req("attestation", frozenset({"presence"})),
        Req("note", frozenset({"judged"})),
        Req("filing", frozenset({"resolved"})),
    ),
    rule=(
        "The Records Desk resolves a discrepancy on six documents. It will tell "
        "you which six. It will not tell you that three of them have never been "
        "issued, because nobody has ever thought to ask it that."
    ),
    on_refuse=(
        "The clerk goes through your folder slowly and without any sign of "
        "enjoying it. 'Attestation — this attests to a threshold. I need one "
        "that attests to you.' 'Note — this notes a passing. I need a finding "
        "that the passing was attendance.' 'Filing — this is a slant. I need it "
        "closed.' Each sentence is entirely reasonable and lands like a step "
        "missing in the dark.",
        "'Still the room. Still a passing. Still a slant.'",
        "The clerk turns the folder round so you can read it yourself.",
        "The bell is rung for you, gently, by someone else in the queue.",
    ),
    on_issue="The discrepancy is resolved. Nobody applauds.",
)

GERALD = Office(
    id="gerald", name="Gerald", staff="Gerald", issues=None, requires=(TICKET,),
    rule=(
        "Gerald has no write authority, cannot impose narrative, and "
        "communicates exclusively in single words on napkins at moments of "
        "structural significance. The chain stops at Gerald."
    ),
    on_refuse=(
        "Gerald was there. Gerald saw you. Gerald is, as far as the building is "
        "concerned, the only entity that could close any of the three gaps, and "
        "Gerald cannot, because doing so would be imposing narrative and Gerald "
        "does not do that. He looks at you. It is not an unkind look. It is the "
        "look of something that stopped being able to help before the building "
        "was built.",
        "Gerald was there. Gerald saw you. Gerald cannot say so. You have both "
        "known this for some time.",
        "Gerald looks at you.",
        "Gerald is here.",
    ),
)

HANZ = Office(
    id="hanz", name="Hanz", staff="Hanz, and an orange named Copenhagen",
    issues=None, requires=(), consumes_ticket=False,
    rule=(
        "Hanz can wink back at Gerald. This is unprecedented and nobody in the "
        "building has filed it anywhere."
    ),
    on_refuse=(
        "Hanz turns the orange over in his hands. 'Bring me something he wrote. "
        "I can read what he writes. That is the whole of what I can do and it is "
        "more than anyone else here can do.'",
        "'Something he wrote,' says Hanz. The orange is named Copenhagen. You "
        "have not asked and he has not offered.",
        "Hanz shakes his head, kindly. Copenhagen says nothing.",
    ),
)

OFFICES: dict[str, Office] = {
    o.id: o
    for o in (QUEUE, PIGEON, LIBRARY, DEPARTMENT, GATE, STACKS, RECORDS, GERALD, HANZ)
}
OFFICE_ORDER = ["queue", "pigeon", "library", "department", "gate", "stacks", "records", "gerald", "hanz"]


def issuers_of(doc_id: str) -> list[Office]:
    return [o for o in OFFICES.values() if o.issues == doc_id]
