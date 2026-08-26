"""Thin wrapper over ``jeles.reactions.conflict_scan``.

Handoff open thread #4. ``conflict_scan.react`` needs a caller-supplied
``Searcher = Callable[[str], list[dict]]`` — the module is deliberately
storage-agnostic so a caller decides where to search (a corpus, a KB, a
mock). :func:`scan` wraps that with a default searcher backed by the
jeles corpus's own ``search_nuggets``, and threads the resulting
proposals through ``conflict_scan.apply`` when a writer callable is
handed over.

Never seals. Proposals from conflict_scan carry
``verification_kind = "machine"`` — they land as jeles nuggets if
applied, and downstream still owes them a human before tier-1.
"""
from __future__ import annotations

from typing import Any, Callable


def _default_searcher(query: str) -> list[dict[str, Any]]:
    from jeles import corpus as jc
    hits = jc.search_nuggets(query, limit=6) or []
    return [{"text": h.get("answer", ""), "sources": h.get("sources") or [], "meta": h} for h in hits]


def scan(
    claim: str,
    *,
    searcher: Callable[[str], list[dict[str, Any]]] | None = None,
    max_results: int = 6,
    min_sources: int | None = None,
    apply: bool = False,
    log_gaps: bool = True,
) -> dict[str, Any]:
    """Run conflict_scan against ``claim``. Return the proposals it makes.

    ``apply=True`` writes any resulting nuggets and gaps back through the
    same jeles functions ``fleet_glue`` uses everywhere else.
    """
    from jeles.reactions import conflict_scan as cs

    s = searcher or _default_searcher
    min_src = min_sources if min_sources is not None else cs.DEFAULT_MIN_SOURCES

    event = {"claim": claim, "queries": cs.frame_queries(claim)}
    proposals = cs.react(event, searcher=s, max_results=max_results, min_sources=min_src)

    applied: list[dict[str, Any]] | None = None
    if apply:
        from jeles import corpus as jc
        applied = cs.apply(
            proposals,
            put_nugget=jc.put_nugget,
            log_gap=jc.log_gap if log_gaps else None,
        )

    return {
        "claim": claim,
        "queries": event["queries"],
        "witness": cs.WITNESS,
        "min_sources": min_src,
        "proposals": proposals,
        "applied": applied,
    }
