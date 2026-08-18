"""The pinned immunization schedule — public reference data, held not fetched (H-5).

An immunization schedule is *public* data: what the published schedule recommends
by age is the same for every household, names no one, and is maintained in the open.
So the catalog of where such data lives is the health-almanac's job (face 3), and
this module carries a **pinned snapshot** of the one schedule it needs — versioned,
dated, and updated only by an operator's act. It **never dials** (I-17 has no health
exception; the seat's network scan holds it structurally), and it never resolves a
link at runtime: the bytes are here, frozen, showing their own version and date.

Three properties make this a snapshot rather than a live feed in disguise, and each
is held by a test:

* **It says which version it is and as of when.** A snapshot that cannot name its
  edition or its date is a feed pretending otherwise (H-5). `SCHEDULE.version` and
  `SCHEDULE.as_of` are both required, and `as_of` is a *literal* pinned date — never
  `date.today()`, which is the live-feed tell.
* **It holds no subject.** This is public reference; it is keyed by vaccine, carries
  no person, and takes no subject. Joining it to a *particular* child's record to
  interpret, triage, or recommend is the practice of medicine and the wall H-2 (and,
  when the reference lane lands, H-7) refuses — retrieval of public reference is not
  advice, composing it against a subject is. This module simply cannot cross that
  wall: there is nowhere in it to put a subject.
* **Updating it is an operator's act.** The snapshot is immutable (frozen), and there
  is no fetch, no auto-update, no clock read. A new edition is a new pinned literal,
  committed deliberately and dated — the ledgered operator act H-5 describes.

**This is not medical advice.** It records what a public schedule says, cited to its
source; the operator and their clinician are the authority on any particular child.
`H-2` — no symptom-checker, no care recommendation, at any version — governs here as
everywhere: this module states the public reference and stops.

## Provenance

The data is the CDC/ACIP child & adolescent immunization schedule for the United
States — a U.S. Government work, public domain — reproduced as a pinned snapshot.
`source` carries the citation that rides through to any answer that quotes the
schedule (the attribution discipline the reference lane inherits). The almanac's
catalog, not this repo, is the record of *where* the live schedule is published; this
repo holds only the snapshot it pinned and the date it pinned it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = ["ScheduledDose", "Schedule", "SCHEDULE"]


@dataclass(frozen=True)
class ScheduledDose:
    """One recommended dose in the public schedule — a vaccine, which dose, and the
    age at which it is recommended. Carries no person: the recommendation is the
    same for every household, which is exactly what makes it public reference."""

    vaccine: str
    dose: str
    recommended_age: str


@dataclass(frozen=True)
class Schedule:
    """A pinned snapshot of a public immunization schedule.

    `version` names the edition and `as_of` is the date this snapshot was pinned —
    both required (H-5), so the snapshot can always say what it is and when it was
    taken. `source` is the citation that rides through to any answer quoting it.
    `doses` is the reference itself, keyed by vaccine and age, holding no subject.
    """

    version: str
    as_of: date
    source: str
    doses: tuple[ScheduledDose, ...]

    def citation(self) -> str:
        """The one line that names the snapshot behind any schedule reasoning — the
        plan's Today example: a due date, *"per the pinned snapshot and its version
        date."* Public reference, cited; never a statement about a child."""
        return f"{self.source} ({self.version}, pinned as of {self.as_of.isoformat()})"

    def for_vaccine(self, vaccine: str) -> tuple[ScheduledDose, ...]:
        """Every recommended dose for one vaccine, in schedule order. A pure lookup
        over public reference — it takes a vaccine name, never a subject, so nothing
        here can join the schedule to a particular child."""
        return tuple(d for d in self.doses if d.vaccine == vaccine)

    def vaccines(self) -> tuple[str, ...]:
        """The distinct vaccines the snapshot covers, in first-seen order."""
        seen: dict[str, None] = {}
        for d in self.doses:
            seen.setdefault(d.vaccine, None)
        return tuple(seen)


def _dose(vaccine: str, dose: str, age: str) -> ScheduledDose:
    return ScheduledDose(vaccine=vaccine, dose=dose, recommended_age=age)


#: The pinned snapshot. A new edition replaces this literal in a deliberate,
#: dated commit — the operator act H-5 names — never a runtime fetch. The ages are
#: the standard published recommendations of the CDC/ACIP U.S. child & adolescent
#: schedule (public domain); `source` is the citation. ASCII-clean on purpose: the
#: text may ride out on an export, where a clean encoding is the safe default.
SCHEDULE = Schedule(
    version="CDC/ACIP child & adolescent immunization schedule, United States",
    as_of=date(2026, 8, 18),
    source="U.S. Centers for Disease Control and Prevention (CDC), public domain",
    doses=(
        _dose("HepB", "dose 1 of 3", "birth"),
        _dose("HepB", "dose 2 of 3", "1-2 months"),
        _dose("HepB", "dose 3 of 3", "6-18 months"),
        _dose("DTaP", "dose 1 of 5", "2 months"),
        _dose("DTaP", "dose 2 of 5", "4 months"),
        _dose("DTaP", "dose 3 of 5", "6 months"),
        _dose("DTaP", "dose 4 of 5", "15-18 months"),
        _dose("DTaP", "dose 5 of 5", "4-6 years"),
        _dose("Hib", "dose 1", "2 months"),
        _dose("Hib", "dose 2", "4 months"),
        _dose("Hib", "booster", "12-15 months"),
        _dose("IPV", "dose 1 of 4", "2 months"),
        _dose("IPV", "dose 2 of 4", "4 months"),
        _dose("IPV", "dose 3 of 4", "6-18 months"),
        _dose("IPV", "dose 4 of 4", "4-6 years"),
        _dose("PCV", "dose 1 of 4", "2 months"),
        _dose("PCV", "dose 2 of 4", "4 months"),
        _dose("PCV", "dose 3 of 4", "6 months"),
        _dose("PCV", "dose 4 of 4", "12-15 months"),
        _dose("MMR", "dose 1 of 2", "12-15 months"),
        _dose("MMR", "dose 2 of 2", "4-6 years"),
        _dose("Varicella", "dose 1 of 2", "12-15 months"),
        _dose("Varicella", "dose 2 of 2", "4-6 years"),
        _dose("HepA", "dose 1 of 2", "12-23 months"),
        _dose("HepA", "dose 2 of 2", "6 months after dose 1"),
        _dose("Tdap", "adolescent booster", "11-12 years"),
        _dose("HPV", "dose 1 of 2", "11-12 years"),
        _dose("HPV", "dose 2 of 2", "6-12 months after dose 1"),
        _dose("MenACWY", "dose 1 of 2", "11-12 years"),
        _dose("MenACWY", "dose 2 of 2", "16 years"),
        _dose("Influenza", "annual", "yearly from 6 months"),
    ),
)
