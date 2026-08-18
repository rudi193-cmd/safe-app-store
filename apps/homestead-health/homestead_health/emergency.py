"""The emergency card — the one artifact whose purpose is to leave (H-3).

Allergies, current medications, blood type: the point of the datum is that a
stranger reads it in the worst minute. Two temptations sit here, and the module
refuses both.

**The wrong answer is lowering the rung.** Usefulness does not declassify, any more
than time does — a diagnosis on an emergency card is still `L4`. So the card does not
reach for a lower rung; it is an **export**, and it crosses the same way everything
crosses: `serve(…, S4_EGRESS, purpose=…)` through `keep/export`, one `IntegrityLog`
entry and one `EXPORTED` act, references only, head anchor off-tree. The operator
carries the paper; the ledger holds the act, not the content.

**The wrong answer is a computed card.** *A computed card is a query someone else
effectively wrote, run at the worst possible moment to be surprised.* So the field
set is **authored, never computed** (H-3): the operator chooses what the card holds,
field by field, and there is no `auto_include`, no `relevant_fields`, no path that
assembles "everything relevant." `Card` is a closed tuple of chosen fields and
nothing more; `export_card` exports **exactly** those fields, ignoring any datum the
caller happens to hand it for a field the card did not name. Adding a field is an act
on the card — a new `Card` with the field in its tuple — not a heuristic that pulls
one in.

Two absences are handled differently, and the difference is the rung model, not an
oversight:

* **A field the operator chose but has no datum for** is a *recorded gap*, not a
  silent omission (I-8). An emergency card's blank allergy line is meaningful — "none
  recorded" is not "no known allergies" — so the gap is drawn, carrying no content.
* **A field whose datum is `L5`** is dropped, and *not* recorded as a gap: at `L5`
  the existence of a refusal is itself what must not be rendered (I-13, the `DENY`
  semantics), so a "withheld" line on the card would leak the very thing the rung
  seals. It simply does not appear, the way `serve_all` drops a denial without a
  trace. No emergency-card field should be `L5`, but the rule holds regardless.

**Not medical advice** (H-2). The card lists what the operator recorded and chose to
carry. It recommends nothing, doses nothing, triages nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from homestead.keep.export import ExportReceipt, ExportRefused, export_record
from homestead.keep.logs import IntegrityLog, VisibleLog
from homestead.keep.rungs import (
    Classified,
    Disposition,
    Purpose,
    Surface,
    compose,
    serve,
)

from ._egress import validate_subject

__all__ = ["Card", "export_card", "CARD_ITEM"]

#: The item_type an exported card is keyed under, in the export tree and the ledger.
CARD_ITEM = "card"


@dataclass(frozen=True)
class Card:
    """The emergency card's field set — authored, never computed (H-3).

    A closed tuple of the fields the operator chose the card to hold, in the order
    they chose. There is deliberately no `auto_include` and no `relevant_fields`: the
    class offers no machinery to assemble a card by relevance, because a card
    assembled by relevance is a query someone else wrote. Adding a field is authoring
    a new `Card` with it in the tuple — a deliberate act, not a heuristic.
    """

    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fields, tuple):
            raise TypeError(
                f"a card's fields are a tuple, authored in order, not "
                f"{type(self.fields).__name__} — a mutable or computed collection is "
                "the shape a heuristic would fill in"
            )
        if not self.fields:
            raise ValueError("an emergency card with no fields holds nothing")
        seen: set[str] = set()
        for f in self.fields:
            if not isinstance(f, str) or not f.strip():
                raise ValueError(f"a card field is a non-empty name, not {f!r}")
            if f in seen:
                raise ValueError(
                    f"field {f!r} appears twice — a card is a set of authored "
                    "choices, each made once"
                )
            seen.add(f)


def export_card(
    card: Card,
    subject: object,
    data: Mapping[str, Classified],
    *,
    purpose: Purpose = Purpose.EXPORT,
    integrity: IntegrityLog | None = None,
    visible: VisibleLog | None = None,
    exports: Path | None = None,
) -> ExportReceipt:
    """Export one subject's emergency card — exactly the fields the operator chose.

    Iterates **the card's** fields, in the card's order, and nothing else — a datum
    in `data` for a field the card did not name is ignored, which is the whole of
    "authored, not computed." For each chosen field: a present, serveable datum is
    included at its own rung (served on S4 with the purpose, so usefulness never
    lowers the rung); a chosen field with no datum is a recorded gap (I-8); a datum
    that denies at the gate (`L5`) is dropped without a trace (I-13), never recorded
    as a withheld line that would leak the seal.

    The composed card is exported through `keep/export.export_record` — the one door
    — so it writes the artifact and exactly one entry to each log, references only,
    head anchor off-tree. A card with no field that could cross is refused before any
    log is written: an export of nothing is not an export.
    """
    sid = validate_subject(subject)

    rows: list[dict[str, object]] = []
    rungs: list = []
    for field in card.fields:
        datum = data.get(field)
        if datum is None:
            # A chosen field with no datum: a recorded gap, carrying no content. The
            # operator authored it, so its absence is drawn, not silently omitted.
            rows.append({"field": field, "value": None, "recorded": False})
            continue
        served = serve(datum, Surface.S4_EGRESS, purpose=purpose)
        if served.disposition is Disposition.DENY:
            # L5 — dropped without a trace. A "withheld" line would reveal the
            # refusal, which at L5 is itself the thing sealed (I-13).
            continue
        rows.append({"field": field, "value": served.value, "recorded": True})
        rungs.append(served.rung)

    if not any(r["recorded"] for r in rows):
        raise ExportRefused(
            f"{sid}: the card has no recordable field to export — an export of "
            "nothing is not an export, and is not ledgered as one."
        )

    # The card composes to its hottest recorded field's rung — usefulness does not
    # lower it. On S4 with the purpose declared, an L4 card renders.
    rung = compose(*rungs)
    history = Classified(
        rung,
        rows,
        derived=f"emergency card for {sid} ({len(card.fields)} authored fields)",
    )

    try:
        return export_record(
            history,
            "emergency",
            CARD_ITEM,
            sid,
            purpose=purpose,
            integrity=integrity,
            visible=visible,
            exports=exports,
        )
    except FileExistsError as exc:
        raise ExportRefused(
            f"{sid}: an export of this card already exists for this instant. The "
            "export tree refuses to overwrite (I-9) — retry."
        ) from exc
