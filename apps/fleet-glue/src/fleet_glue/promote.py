"""Gap promote recipes and the canon-door helper.

Two promote paths:

* :func:`promote_gap_to_jeles` — answer becomes a nugget with sources.
  If a willow ``gap_id`` is provided (from :func:`fleet_glue.log_gap`),
  the willow gap row is resolved and its ``promoted_to`` is set to the
  new nugget id.

* :func:`promote_gap_to_nestor_draft` — answer becomes a Nestor draft
  via :func:`fleet_glue.corroborate_to_draft`.

Neither seals. Neither treats a jeles nugget as tier-1.

:func:`advisory_ratify` is the read-only canon door. It builds a real
``RatifyRequest`` against ``willow_mcp.mem_ratify`` (§7 of the handoff)
and returns the ``Decision`` — a caller decides whether to proceed.
"""
from __future__ import annotations

from typing import Any


def promote_gap_to_jeles(
    question: str,
    answer: str,
    sources: list[str],
    *,
    topic: str = "promoted",
    verified_by: str = "operator",
    verification_kind: str = "human",
    willow_gap_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Answer → jeles nugget (+ willow gap resolve when id is passed)."""
    from jeles import corpus as jc

    nugget = jc.put_nugget(
        question=question,
        answer=answer,
        sources=sources,
        verified_by=verified_by,
        verification_kind=verification_kind,
        tags=tags or [f"topic:{topic}", "promoted-from-gap"],
    )
    nugget_id = nugget.get("id") if isinstance(nugget, dict) else None

    resolved: Any = None
    marked: Any = None
    if willow_gap_id:
        try:
            from willow_mcp import gaps as wgaps
            resolved = wgaps.resolve(willow_gap_id, note=f"promoted to jeles:{nugget_id}")
            # willow's mark_promoted silently returns None on a missing id, so
            # gate on a successful resolve rather than trusting mark_promoted's
            # own signal — otherwise a bogus gap id reports marked=True.
            if isinstance(resolved, dict) and "error" not in resolved:
                wgaps.mark_promoted(willow_gap_id, str(nugget_id or question[:40]))
                marked = True
            else:
                marked = False
        except Exception as exc:
            resolved = {"error": type(exc).__name__, "detail": str(exc)}
            marked = False

    return {
        "nugget": nugget,
        "nugget_id": nugget_id,
        "willow_gap_id": willow_gap_id,
        "gap_resolve": resolved,
        "gap_marked_promoted": marked,
    }


def promote_gap_to_nestor_draft(
    question: str,
    answer: str,
    source_lang: str,
    target_lang: str,
    *,
    sources: list[str] | None = None,
    store=None,
) -> dict[str, Any]:
    """Answer → Nestor draft with citation evidence. Never sealed."""
    from .corroborate import corroborate_to_draft

    return corroborate_to_draft(
        question,
        answer,
        source_lang,
        target_lang,
        sources=sources or [],
        store=store,
        verifier_label="gap-promote",
    )


def advisory_ratify(
    claim_id: str,
    proposer_id: str,
    *,
    current_tier: str = "contested",
    target_tier: str = "frontier",
    witnesses: list[dict[str, Any]] | None = None,
    ledger_evidence_ref: str | None = None,
    operator_key_signature: str | None = None,
    prior_frontier_ratifiers: list[str] | None = None,
) -> dict[str, Any]:
    """Ask ``willow_mcp.mem_ratify`` whether this promotion would be allowed.

    Read-only. No side effects. The returned dict is what a caller uses
    to decide whether to write a nugget / draft; a refused decision is
    still a useful record to attach to the gap or the pair.

    Tier strings map to :class:`willow_mcp.mem_ratify.Tier` case-insensitively;
    unknown values raise ``ValueError``.

    ``witnesses`` items must have ``agent_id`` and ``base_model``.
    ``independence_evidence`` is optional; when omitted, ratify counts it
    as non-independent and adds a flag_for_human.
    """
    from willow_mcp.mem_ratify import (
        Decision,
        RatifyRequest,
        Tier,
        Witness,
        ratify,
    )

    def _to_tier(name: str) -> Tier:
        key = (name or "").strip().upper()
        try:
            return Tier[key]
        except KeyError as exc:
            allowed = ", ".join(t.name for t in Tier)
            raise ValueError(f"unknown tier {name!r}; expected one of {allowed}") from exc

    ws: list[Witness] = []
    for w in witnesses or []:
        if isinstance(w, Witness):
            ws.append(w)
            continue
        if not isinstance(w, dict):
            raise TypeError(f"witness must be dict or Witness, got {type(w).__name__}")
        ws.append(
            Witness(
                agent_id=str(w["agent_id"]),
                base_model=str(w["base_model"]),
                independence_evidence=w.get("independence_evidence"),
            )
        )

    req = RatifyRequest(
        claim_id=claim_id,
        current_tier=_to_tier(current_tier),
        target_tier=_to_tier(target_tier),
        proposer_id=proposer_id,
        witnesses=tuple(ws),
        ledger_evidence_ref=ledger_evidence_ref,
        operator_key_signature=operator_key_signature,
        prior_frontier_ratifiers=frozenset(prior_frontier_ratifiers or ()),
    )
    decision: Decision = ratify(req)
    return {
        "allowed": decision.allowed,
        "claim_id": decision.claim_id,
        "current_tier": decision.current_tier.name,
        "target_tier": decision.target_tier.name,
        "reasons": list(decision.reasons),
        "independent_witness_count": decision.independent_witness_count,
        "placeholders_relied_on": list(decision.placeholders_relied_on),
        "flags_for_human": list(decision.flags_for_human),
    }
