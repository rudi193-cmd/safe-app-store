#!/usr/bin/env python3
"""stores/checkpoint_governance.py — adopting willow-mcp's `human_loop` under
The Forge's checkpoint (docs/design/the-forge-human-loop.md).

The D12 move applied at the governance layer: `checkpoint_memory` adopted
Nestor as the SEAL (memory — does the maker recognize this decision?); this
adopts the vendored `human_loop` as the ATTESTATION (governance — did the maker
sign THIS commitment, and were they human?) and the `human_required` QUEUE (the
async pause seam + the durable outbox for bite 3 / #67's signals). "Authorship
is not authority": the model may propose the whole decision, but what commits it
is the maker's non-forgeable, on-the-record sign-off.

Store-side (D1): imports the vendored `human_loop` and the `FilesystemSoilStore`
only — NOT `checkpoint` (that would cycle: `checkpoint` imports THIS, to attest
on commit). The checkpoint FLOW halves that need the seal — `run_checkpoint`'s
attest-on-commit, and `resume_checkpoint` — live in `checkpoint.py`; this module
holds the governance primitives they call. `apps/the-forge/` never imports it.

**Anti-forgery is structural (D-HL-3).** `attest_decision` binds
`attested_by = builder_id` and takes `by_human` from the caller; a sandboxed
build can't reach this module (D1), so `attested_by` is never a build's own
free text. Full D11 identity refines `by_human` later; the binding point is
already correct.

Three capabilities:
  * attestation under a decision — `attest_decision` / `has_decision_attestation`
    (D-HL-4), keyed on the decision's Nestor `pair_id`.
  * the park half of the async seam — `park_decision` enqueues the model's full
    proposal as `human_required{kind: attestation}` EVIDENCE; nothing seals
    until a human resumes it (D-HL-5). `resume_checkpoint` (the completing half,
    which seals+attests) is in `checkpoint.py`.
  * the nudge outbox — `route_nudge` persists bite 3 / #67's `review`/`overload`
    signals as queue items, deduped by `source_ref` (D-HL-6), closing #67's
    "nudges aren't persisted" gap. The monitors still only signal; routing is a
    separate opt-in step, so they stay pure.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _REPO / "stores" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


soil_store = _load("soil_store", "soil_store.py")
human_loop = _load("human_loop", "human_loop.py")

# A decision is a "queue_item"-adjacent subject; human_loop's attestation
# subject vocabulary doesn't have a dedicated "decision", so use "other" (its
# catch-all) with a stable convention, rather than widening the vendored
# vocabulary and forking it from upstream.
_DECISION_SUBJECT_TYPE = "other"

# This agent's name in queue rows — the Forge is the source_agent enqueuing.
SOURCE_AGENT = "the-forge"

# Our own collection for the structured payload of a parked decision (enqueue
# stores only human-facing text), keyed by the queue item id.
_PARKED_COLLECTION = "parked_decisions"


class GovernanceError(Exception):
    """This module's own refusal (a bad nudge kind, etc.). `human_loop`'s own
    `HumanLoopError` and `soil_store`'s `SoilStoreError` propagate unwrapped —
    a caller catches those types directly, same discipline `checkpoint_memory`
    uses for Nestor's exceptions."""


def _store(builder_id: str, root: Path) -> "soil_store.FilesystemSoilStore":
    return soil_store.FilesystemSoilStore(builder_id, root=root)


# ── attestation under a decision (D-HL-4) ────────────────────────────────────

def attest_decision(
    builder_id: str,
    decision_key: str,
    *,
    chosen: str,
    by_human: bool = True,
    status: str = "attested",
    root: Path,
) -> dict:
    """Record the maker's non-forgeable sign-off on ONE decision, keyed by its
    Nestor `pair_id` (`decision_key`). `attested_by` is bound to `builder_id`
    here, never taken as caller free text (D-HL-3). `status` is
    attested/rejected/needs_changes (`human_loop`'s vocabulary). Rides ALONGSIDE
    the Nestor seal, not inside it (D-HL-4)."""
    return human_loop.create_attestation(
        _store(builder_id, root),
        subject_id=decision_key,
        subject_type=_DECISION_SUBJECT_TYPE,
        attested_by=builder_id,
        by_human=by_human,
        statement=chosen,
        status=status,
    )


def has_decision_attestation(
    builder_id: str, decision_key: str, *, require_human: bool = False, root: Path
) -> bool:
    """True if this decision carries an `attested` record; with `require_human`,
    only a `by_human` one counts (the 'a person signed this' gate)."""
    return human_loop.has_attestation(
        _store(builder_id, root),
        subject_id=decision_key,
        subject_type=_DECISION_SUBJECT_TYPE,
        require_human=require_human,
    )


# ── the park half of the async seam (D-HL-5) ─────────────────────────────────

def park_decision(
    builder_id: str,
    *,
    decision_type: str,
    surface: str,
    options: list,
    recommended: str | None,
    root: Path,
) -> dict:
    """Park a decision the model reached with no human present: enqueue the FULL
    proposal (surface + options + tradeoffs + recommended) as
    `human_required{kind: attestation}` EVIDENCE. Nothing seals, nothing
    attests — parking is not deciding (D-HL-5). Returns the queue item; a human
    later resumes it via `checkpoint.resume_checkpoint`. The evidence is the
    model's narrative, and it stays evidence until a human acts on it —
    `human_session`'s 'narrative is evidence, not instructions,' made
    mechanical: a parked item cannot self-seal or time out into a default."""
    opt_lines = "\n".join(f"  - {label}: {tradeoff}" for label, tradeoff in options)
    rec_line = f"\nmodel-recommended: {recommended}" if recommended else ""
    summary = (
        f"A decision was reached with no human present and PARKED for sign-off. "
        f"The model proposes (evidence, not a decision):\n\n{surface}\n\n"
        f"options:\n{opt_lines}{rec_line}\n\n"
        f"decision_type: {decision_type}"
    )
    store = _store(builder_id, root)
    item = human_loop.enqueue(
        store,
        kind="attestation",
        title=f"decide: {decision_type}",
        summary=summary,
        source_agent=SOURCE_AGENT,
        priority="normal",
        source_ref=f"parked:{decision_type}:{surface}",
    )
    # human_loop's queue row is human-facing text; the STRUCTURED decision (so
    # resume_checkpoint can rebuild the Decision and run its choose() flow) is
    # stored beside it, keyed by the queue item id, in our own collection —
    # enqueue itself has no structured-payload field.
    store.put(
        _PARKED_COLLECTION,
        {
            "id": item["id"],
            "decision_type": decision_type,
            "surface": surface,
            "options": [list(o) for o in options],
            "recommended": recommended,
        },
        record_id=item["id"],
    )
    return item


def get_parked_decision(builder_id: str, item_id: str, *, root: Path) -> dict | None:
    """The structured decision (`decision_type`/`surface`/`options`/
    `recommended`) stored by `park_decision` for a queue item, or None. Used by
    `checkpoint.resume_checkpoint` to rebuild the `Decision` when a human
    finally acts on a parked item."""
    return _store(builder_id, root).get(_PARKED_COLLECTION, item_id)


def get_queue_item(builder_id: str, item_id: str, *, root: Path) -> dict | None:
    """The raw `human_required` queue row for `item_id`, or None. Its `status`
    (open / resolved / dismissed / acknowledged) is the single source of truth
    for whether a parked decision has already been acted on — `resume_checkpoint`
    reads it to enforce single-use (a resolved item cannot be resumed twice)."""
    return _store(builder_id, root).get(human_loop.QUEUE_COLLECTION, item_id)


def open_items(builder_id: str, *, root: Path, kind: str = "", limit: int = 50) -> list:
    """The builder's open `human_required` items (parked decisions + routed
    nudges), newest first. `kind` filters (attestation/review/overload/…)."""
    return human_loop.list_queue(_store(builder_id, root), status="open", kind=kind, limit=limit)


def resolve_item(
    builder_id: str, item_id: str, *, resolved_by: str, status: str = "resolved", note: str = "", root: Path
) -> dict:
    """Resolve/dismiss/acknowledge a queue item in place (states-not-deletions)."""
    return human_loop.resolve(
        _store(builder_id, root), item_id, resolved_by=resolved_by, status=status, note=note
    )


# ── the nudge outbox (D-HL-6) ────────────────────────────────────────────────

def route_nudge(
    builder_id: str,
    *,
    kind: str,
    title: str,
    source_ref: str,
    summary: str = "",
    priority: str = "normal",
    root: Path,
) -> dict | None:
    """Persist a bite-3 / #67 signal as a `human_required` item — `review` (a
    rubber-stamp / mirror flag worth a human's eyes) or `overload` (a sustained
    run). Deduped by `source_ref`: the same episode routed twice does not pile
    up a second OPEN row (returns None on the duplicate). Closes #67's
    'nudges aren't persisted' gap (D-HL-6). The monitors themselves stay pure —
    a caller opts into routing; this never runs inside a monitor."""
    k = (kind or "").strip().lower()
    if k not in ("review", "overload", "consent"):
        raise GovernanceError(
            f"route_nudge kind {kind!r} must be a review/overload/consent "
            f"human_required kind — a nudge is one of those, not {kind!r}"
        )
    store = _store(builder_id, root)
    # Scan ALL open items of this kind for the dedup, not a capped page — a
    # capped scan would silently admit a duplicate once the open queue grew past
    # the cap. `human_loop.list_queue` has no "unbounded" sentinel, so pass a
    # bound far above any realistic open-queue size for one builder.
    for existing in human_loop.list_queue(store, status="open", kind=k, limit=1_000_000):
        if existing.get("source_ref") == source_ref:
            return None  # already an open item for this episode — dedupe
    return human_loop.enqueue(
        store, kind=k, title=title, summary=summary, source_agent=SOURCE_AGENT,
        priority=priority, source_ref=source_ref,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_queue(args: argparse.Namespace) -> int:
    items = open_items(args.builder_id, root=Path(args.root), kind=args.kind or "")
    print(json.dumps(
        [{"id": i["id"], "kind": i["kind"], "title": i["title"], "priority": i["priority"]} for i in items],
        indent=2,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint_governance.py")
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("queue", help="list a builder's open human_required items")
    q.add_argument("builder_id")
    q.add_argument("--root", default=str(soil_store.DEFAULT_CHECKPOINT_ROOT))
    q.add_argument("--kind", default="")
    q.set_defaults(func=_cmd_queue)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
