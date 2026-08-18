"""The school form — health's first purposed egress (bite 5).

The immunization history is the rare health disclosure that is routine, expected,
and bounded: a school asks for it, the operator hands it over, and everyone agrees
in advance what it contains. That makes it the right first egress — the seam is
exercised on the least fraught disclosure in the domain, not the most.

An export is *"explicit act + purpose + ledgered"* (the S4 spec row), and the whole
mechanism already exists in the engine — `keep/export.export_record` gates one datum
through `serve(…, S4_EGRESS, purpose=…)`, writes the artifact to `exports_dir()`, and
records exactly one `IntegrityLog` entry (a reference and the purpose, never content)
and one `VisibleLog` `EXPORTED` act, with the head anchor held off the log's own tree
(the willow-mcp #280 separation). This module does not reinvent any of that. It does
the one thing the engine's single-record export does not: assemble **a subject's
history** — several doses — into one export, so the school gets one form and the
ledger gets one entry, not one per shot.

## It reaches no payload — it serves, like every other consumer

The chokepoint rule lets only the gate and the store read a `.payload`; an egress
module is neither, and `keep/export` is scrupulous about it. This module keeps that
discipline: it gets each dose's content by **serving** it on S4 with the declared
purpose (`serve`/`serve_all`), never by reaching into the record. The served values —
what the gate says may cross — are what the history carries, and the composed history
is handed back to `export_record`, which serves it once more as the authoritative,
ledgered act. The pre-serve is how content is obtained lawfully; the export is what
gates and records it.

## The history composes to what its hottest dose is

An immunization record composes to `L4` (the vaccine is a medical act on a person),
and a history of them is the `max` of its parts (I-12) — so the whole form is `L4`,
and `L4` crosses S4 only with a purpose declared, which is exactly the ceremony an
export is. A dose that denied at the gate (an `L5` no immunization record should ever
hold, but the rule is the rule) is dropped by `serve_all` and never reaches the form;
an export with nothing left to carry is refused before either log is touched, rather
than ledgered as an export of nothing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from homestead.keep.export import ExportReceipt, ExportRefused, export_record
from homestead.keep.logs import IntegrityLog, VisibleLog
from homestead.keep.rungs import (
    Classified,
    Purpose,
    Surface,
    compose,
    serve_all,
)

from ._egress import validate_subject

__all__ = ["export_history", "HISTORY_ITEM"]

#: The item_type an exported history is keyed under, in the export tree and the
#: ledger reference. One history per subject per export; the export tree's
#: timestamp keeps a second export of the same subject from clobbering the first.
HISTORY_ITEM = "history"


def export_history(
    subject: object,
    doses: Iterable[Classified],
    *,
    purpose: Purpose = Purpose.EXPORT,
    integrity: IntegrityLog | None = None,
    visible: VisibleLog | None = None,
    exports: Path | None = None,
) -> ExportReceipt:
    """Take one subject's immunization history out, on S4, and ledger the act.

    `subject` is the roster ref or id — the export is keyed by it, so the artifact
    and the ledger entry both name whose history left, by the opaque id and never a
    name (H-1). `doses` is that subject's immunization records, already gathered
    (finding them by subject is the surface's job — `Sidecar.records` filtered by the
    subject field); this function is the egress, not the query.

    Each dose is served on S4 with the declared purpose; the ones that may cross make
    up the form, composed to their hottest rung. The composed history is exported
    through `keep/export.export_record`, which writes the artifact and the two log
    entries and returns the receipt — whose `head` is the value to record off the
    machine so `verify(expected_head=…)` means something later.

    Refuses, before either log is written, an empty history (nothing to export is not
    an export) — the same fail-before-ledger posture `export_record` takes for an
    undeclared purpose or an `L5` datum.
    """
    sid = validate_subject(subject)

    # Serve each dose on the egress surface with the purpose declared. serve_all
    # drops anything that denies (an L5), so the form carries only what may cross —
    # and this is how the content is obtained without reaching a .payload.
    served = serve_all(doses, Surface.S4_EGRESS, purpose=purpose)
    if not served:
        raise ExportRefused(
            f"{sid}: no immunization records to export. An export of nothing is not "
            "an export, and is not ledgered as one."
        )

    lines = [s.value for s in served]
    rung = compose(*(s.rung for s in served))
    # The history is a datum in its own right — its rung is the max of its doses
    # (L4), so it needs a derived form (L3/L4 are served derived on some surface).
    # The derived form counts, and names the subject by id, never the vaccines.
    history = Classified(
        rung,
        lines,
        derived=f"immunization history for {sid} ({len(lines)} records)",
    )

    # export_record is the one door: it serves the history on S4 with the purpose,
    # writes the artifact and exactly one entry to each log, references only, head
    # anchor off-tree. It refuses an L5 history the same way — belt and braces on the
    # compose above.
    #
    # A same-instant filename collision in the export tree surfaces from the engine
    # as a bare FileExistsError (the artifact's O_EXCL create, before any log write).
    # This module's contract is ExportRefused, and the collision happens before
    # anything is ledgered, so it is converted here rather than leaking a raw
    # filesystem error to a caller doing rapid batch exports.
    try:
        return export_record(
            history,
            "immunizations",
            HISTORY_ITEM,
            sid,
            purpose=purpose,
            integrity=integrity,
            visible=visible,
            exports=exports,
        )
    except FileExistsError as exc:
        raise ExportRefused(
            f"{sid}: an export of this history already exists for this instant. "
            "The export tree refuses to overwrite (I-9) — retry."
        ) from exc
