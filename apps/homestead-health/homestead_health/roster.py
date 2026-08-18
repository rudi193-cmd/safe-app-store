"""The roster — subjects before records (bite 2, H-1).

Health records are per person, and a household has several. The engine's founding
simplification — *"a household has one operator, no relay, no untrusted server"* —
never needed a subject, because a legal matter is keyed by `(matter, item_type,
item_id)` and a matter names no one. Health does: a dose belongs to a person, and
the naive spelling of that — `("health:mara", ...)` — puts a **name in a key**, and
keys are exactly what the logs carry (I-15: references, never content). A reference
that *is* the datum defeats the split the two logs exist to hold.

So this module is the answer the plan named H-1:

* **Subjects are opaque ids.** `subj-01`, `subj-02` — minted by a counter, never
  derived from the person. An id resolves to a person (that is its purpose) but
  carries no fragment of the name and no category. It **is** the derived form of
  the person: the thing a key, a log line, or a list row may carry where a name
  may not.
* **The roster maps id → person, and that mapping is itself a classified record
  served through the gate.** A subject's name is stored through `keep/record` like
  anything else, at `L4` when the subject is a minor and `L3` otherwise, and it is
  reached only by `serve()` — on the detail pane, never on an ambient surface.
* **A log line about a subject carries the id and nothing else.** `add()` records a
  `VisibleLog` act whose `ref` is `(subject_id,)` — the same closed-enum, references-
  only log the whole engine uses (F-4). Grepping the rendered log for a name comes
  back empty.

## Why the name's rung turns on minority

The declaration mirrors the custody pack, field for field. `opposing_party` — a
person, no protected category — is `L3`; `child_name` — *"names a person who is a
minor … a category the law follows"* — is `L4`. A roster name is the same shape: an
adult household member resolves to a person (step 2 yes, step 3 no) → `L3`; a minor's
name is a category the law follows (step 3 yes) → `L4`, and the whole model turns on
not rendering it by default. The plan says exactly this — *"roster names declared
`L4` where the subject is a minor."* Over-classifying would fail closed (the safe
direction); this honours the plan's line rather than reaching for it.

The minor flag is not stored beside the name — it **is** the rung. `L4` on the way
out means minor, `L3` means adult, so there is one source of truth for it and a
restart cannot resurrect a subject whose minority disagrees with its own rung.

## The derived form of a name is the subject's own id

`L3` and `L4` are both served as a derived form on at least one surface, so a
`Classified` at either rung must carry one (the engine refuses one that does not —
BUG-5's other half). The derived form of *"Mara Chen"* is `subj-02`: on the list a
minor's name is withheld and the id stands in; in the detail pane the name renders.
The id is the `L3` handle for the person, which is exactly what *"the id is the
derived form of the person"* means, made concrete.

## In-memory by default; persistent when handed a store

A bare `Roster()` is in-memory — it mints ids and holds names in the process, writes
nothing, and dials nothing. Handed a `Sidecar`, it also persists each subject and
resumes its counter from disk on construction, so a subject survives a restart
(bite 2's *done when*). The two are the same object because the id discipline is the
same either way; only the durability differs. A store-bound roster gets a
`VisibleLog` unless one is passed, so the id-only log line is written wherever
subjects are actually kept.

This module never reaches a `.payload`: it hands `Classified` records to callers,
who serve them. The name crosses a boundary only through `serve()`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from homestead.keep.logs import Event, VisibleLog
from homestead.keep.record import Sidecar
from homestead.keep.rungs import Classified, Rung

__all__ = ["SubjectRef", "Roster", "ROSTER_MATTER", "SUBJECT_ITEM"]

#: The reserved sidecar area the roster keeps its subjects under. Not a registered
#: matter — the registry enumerates matter *types* with packs behind them (I-23),
#: and a subject is not a matter. This is infrastructure the module owns, keyed the
#: same way every record is so `Sidecar` files and finds it with no special path.
ROSTER_MATTER = "_roster_"
SUBJECT_ITEM = "subject"

#: A minted id, and the pattern that reads its number back on resume. The counter
#: is the only thing that decides an id, so `subj-01` is position, never identity.
_ID = re.compile(r"^subj-(\d+)$")


def _subject_id(n: int) -> str:
    return f"subj-{n:02d}"


@dataclass(frozen=True)
class SubjectRef:
    """An opaque handle to a household member. Carries the id and nothing else.

    `str(ref)` is `"subj-01"` — what keys, log lines and list rows may hold. It is
    minted by the roster's counter, so it does not depend on the name in any way:
    two rosters that each add a first subject both return `subj-01`, whatever the
    names were. An id that varied with the name would be the name in disguise —
    reversible, and therefore not a reference at all (H-1, tightened by the bite-1
    audit). This type has no `name` field on purpose: a reference that could carry
    the name is one a caller will eventually let carry it.
    """

    id: str

    def __str__(self) -> str:
        return self.id


class Roster:
    """The household's members, by opaque id, with names served through the gate.

    In-memory when constructed bare; persistent when handed a `Sidecar`, resuming
    its counter from whatever subjects the store already holds so ids never collide
    across a restart. The name of each subject is a `Classified` — `L4` for a minor,
    `L3` for an adult — reachable only by serving it; the roster itself never renders
    it.
    """

    def __init__(
        self, store: Sidecar | None = None, *, log: VisibleLog | None = None
    ) -> None:
        self._store = store
        # A store-bound roster logs by default, so the id-only line is written
        # wherever subjects are actually kept. An in-memory roster logs nothing —
        # there is nothing durable to have an audit trail about.
        self._log = log if log is not None else (VisibleLog() if store is not None else None)
        self._names: dict[str, Classified] = {}
        self._counter = 0
        if store is not None:
            self._resume()

    # ── reading ──────────────────────────────────────────────────────────────

    def subjects(self) -> tuple[SubjectRef, ...]:
        """Every subject, as refs — ids only, never names. Ordered by id, which is
        order of enrolment, so the list is stable across calls and restarts."""
        return tuple(SubjectRef(sid) for sid in sorted(self._names, key=self._number))

    def name_of(self, ref: SubjectRef | str) -> Classified:
        """The subject's name, as the `Classified` record to serve.

        Returns the classified datum, not the string: a caller reaches the name by
        `serve(roster.name_of(ref), Surface.S1_DETAIL)`, which renders it in the
        detail pane and derives it (to the id) on an ambient surface. The roster
        hands over the scored object and reads no payload itself (I-16).
        """
        return self._names[self._key(ref)]

    def is_minor(self, ref: SubjectRef | str) -> bool:
        """Whether the subject is a minor — read from the name's rung, the one
        place minority is recorded. `L4` → minor; anything else → not."""
        return self._names[self._key(ref)].rung is Rung.L4

    def __contains__(self, ref: object) -> bool:
        if isinstance(ref, (SubjectRef, str)):
            try:
                return self._key(ref) in self._names
            except (KeyError, TypeError):
                return False
        return False

    def __len__(self) -> int:
        return len(self._names)

    # ── writing ──────────────────────────────────────────────────────────────

    def add(self, *, name: str, minor: bool) -> SubjectRef:
        """Enrol a household member. Mint an opaque id, classify the name, return
        the ref.

        The id comes from the counter, never from the name — that is the whole of
        H-1's tightened claim. The name is stored (when this roster is persistent)
        as a `Classified` at the minority-derived rung, and one `VisibleLog` act is
        written carrying the id alone. Nothing here renders the name.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a subject needs a name (a non-empty string)")

        self._counter += 1
        sid = _subject_id(self._counter)
        rung = Rung.L4 if minor else Rung.L3
        # The derived form is the subject's own id: the L3 handle that stands in for
        # the name wherever the name may not go. Required because L3/L4 are served
        # derived on at least one surface, and chosen so a withheld name resolves to
        # the reference, not to a blank.
        record = Classified(rung, name, derived=sid)

        self._names[sid] = record
        if self._store is not None:
            # No overwrite: the counter is max+1, so a first write can never land on
            # an occupied key, and if it somehow did (a hand-planted file) the store
            # refusing it (I-9) is the right answer, not a silent clobber.
            self._store.put(ROSTER_MATTER, SUBJECT_ITEM, sid, record)
        if self._log is not None:
            # The ref is the id and nothing else. RECORD_SYNCED is the closed-enum
            # act for "a record was stored"; there is no free-text field on this log
            # to leak the name through (F-4), and the ref carries no name either.
            self._log.record(Event.RECORD_SYNCED, ref=(sid,))
        return SubjectRef(sid)

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _key(ref: SubjectRef | str) -> str:
        sid = ref.id if isinstance(ref, SubjectRef) else ref
        if not isinstance(sid, str):
            raise TypeError(f"a subject reference is a SubjectRef or its id, not {sid!r}")
        return sid

    @staticmethod
    def _number(sid: str) -> int:
        m = _ID.match(sid)
        return int(m.group(1)) if m else 0

    def _resume(self) -> None:
        """Rebuild the in-memory map and the counter from the store.

        Reads every subject record through the store's fail-closed loader (a corrupt
        row reads `L5`, never a crash) and sets the counter to the highest id number
        seen, so the next `add()` continues the sequence rather than colliding with
        an existing subject. A record whose id is not the minted shape is skipped for
        the counter but still held, so nothing already stored disappears from the
        roster on load.
        """
        assert self._store is not None
        highest = 0
        for (_, _, item_id), record in self._store.records(ROSTER_MATTER):
            self._names[item_id] = record
            highest = max(highest, self._number(item_id))
        self._counter = highest
