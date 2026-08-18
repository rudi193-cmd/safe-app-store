"""The immunizations pack — health's first real schema (bite 3).

A US-CA immunization record, classified at **import**. `classify_schema(SCHEMA)`
runs at module top level, so an author who adds a field and forgets its rung stops
the build with that field named (I-11) — the refusal the custody pack proved on a
legal schema, now aimed at health's first. It is the custody pack's shape, field
for field: a closed schema whose every field is a mapping carrying `rung`, its
matter, its jurisdiction, and the sentence that justifies the rung against the
five-step procedure (`homestead/docs/homestead-rungs.md` § "Classifying a new
field"). A reviewer cannot check `L4` for `vaccine` without knowing it is a
*medical act attached to a person*, and the field says so.

**The rungs are declared, never inferred from the field name.** The declarations
below are the ones `homestead/docs/PLAN-homestead-health.md` § "The immunizations
pack, classified" proposes; this file is where they become real, and the build
fails if any is dropped.

**Immunizations is first on merit.** It exercises every seam the law packs proved
plus the new one: real deadlines (`dose_date`, `next_due` — dates that name nobody
by themselves, so `L2`, while the *record* composes to `L4` by I-12's `max`), a
real purposed egress (the school form, bite 5), the subject dimension (`subject`,
the opaque roster id, `L3`), and minors' data — on the least dangerous content in
the domain, so a wrong seam is found at the lowest stakes on the table.

**What this pack cannot catch, and does not pretend to.** `classify_schema` checks
that a rung was *declared*, not that it was declared *well*: it would accept `L1`
for `vaccine` without a murmur. The advisory content matcher — declared `L3`
`provider`, content shaped like a *pediatric oncology* clinic, argued **up** — is
the guard the `L3`/`L4` declarations lean on, and it may only ever raise a rung,
never lower one. No `ssn`, no member id, no insurance field lives here: key
material belongs to the insurance pack when it exists, at `L5`, and importing one
field of it early would be the two-homes drift the plan's exclusion 3 refuses.
"""
from __future__ import annotations

from typing import Any

from homestead.keep.rungs import Rung, classify_schema

__all__ = ["MATTER", "JURISDICTION", "SCHEMA", "FIELDS"]

MATTER = "immunizations"
JURISDICTION = "US-CA"


def _field(rung: Rung, why: str) -> dict[str, Any]:
    return {"rung": rung, "matter": MATTER, "jurisdiction": JURISDICTION, "why": why}


#: The closed immunizations schema. Field → declaration (rung + matter +
#: jurisdiction + reason). Nothing here is keyed on the field name; the rung is a
#: property of the field *in this matter and jurisdiction* (step 5).
SCHEMA: dict[str, dict[str, Any]] = {
    "subject": _field(
        Rung.L3,
        "the opaque subject id (roster's subj-NN). Resolves to a person — that is "
        "its purpose — with no category carried by the id itself (step 2 yes, step "
        "3 no). It IS the derived form of the person: what a log or a list row may "
        "carry where a name may not (H-1).",
    ),
    "vaccine": _field(
        Rung.L4,
        "names a medical act attached to a person (step 3) — health is the first of "
        "L4's familiar four. Uniform across vaccines on purpose: some names carry "
        "more than others (a travel vaccine says travel, HPV says age), and a "
        "per-vaccine ladder would classify by column name, the wrong the rungs doc "
        "opened against. Over-classifying fails closed, and the derived serving mode "
        "keeps it livable.",
    ),
    "dose_date": _field(
        Rung.L2,
        "a date, naming nobody by itself (step 2 no). The record still composes to "
        "L4 — I-12's max — so nothing renders a dose date beside a subject on an "
        "ambient surface; the declaration is per-field, the protection is "
        "per-record.",
    ),
    "next_due": _field(
        Rung.L2,
        "same posture as dose_date: a parsed Deadline (I-1, keep/dates), never a "
        "string. What Today renders is derived from the record and gated by I-31's "
        "k >= 2 count — the plan's worked Today line.",
    ),
    "provider": _field(
        Rung.L3,
        "names a business, not a person — but a care relationship resolves to the "
        "household (step 2), and a specialty-bearing name can carry the category in "
        "a proper noun: a pediatric oncology clinic is a diagnosis wearing a "
        "business name. Declared L3; content shaped hotter is the advisory "
        "matcher's case — argued up, never down.",
    ),
    "lot_number": _field(
        Rung.L2,
        "operational; carries no identity and no category. Kept at all because "
        "recalls are keyed on it.",
    ),
    "source": _field(
        Rung.L3,
        "how this dose is known — the clinic card, a portal printout, the "
        "operator's memory (H-4). Provenance resolves to who was there (step 2), no "
        "category. A dose with no source is a recorded gap, never a silent "
        "promotion to certainty.",
    ),
    "notes": _field(
        Rung.L4,
        "free operator text, the same decision and same residual as custody.notes — "
        "kept at L4 by that decision (2026-08-10), the advisory content matcher as "
        "the guard, synthetic-data-only until the residual closes. Not re-argued "
        "here; a second copy of that argument could drift from the first. A note "
        "never reaches a model prompt (S2, ceiling L2 -> derived) or an agent "
        "(I-15), and the operator reads their own note in the detail pane.",
    ),
}

#: Classified at import (I-11). This line is the build failure: remove any field's
#: rung above and the process defining the schema dies, naming the field.
FIELDS: dict[str, Rung] = classify_schema(SCHEMA)
