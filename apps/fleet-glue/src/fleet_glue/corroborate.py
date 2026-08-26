"""Machine corroboration → Nestor draft.

A caller hands over a (source_text, target_text) claim and one or more
URLs. We land a Nestor draft with an evidence row per URL and a citation
warrant naming the first URL's host as the authority.

Never seals. That's not this lane's job — the human seal path is
untouched. This just makes the claim reviewable without a curator
retyping every URL.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def corroborate_to_draft(
    source_text: str,
    target_text: str,
    source_lang: str,
    target_lang: str,
    *,
    sources: list[str],
    store=None,
    matcher=None,
    verifier_label: str = "fleet-glue-corroborate",
    check_note: str = "",
) -> dict[str, Any]:
    """Land a draft pair + evidence rows + one citation warrant."""
    from nestor import evidence, memory, warrant
    from nestor.matcher import StringMatcher
    from nestor.storage import get_store

    store = store or get_store()
    m = matcher or StringMatcher()

    pair = memory.add_pair(
        source_text=source_text,
        target_text=target_text,
        source_lang=source_lang,
        target_lang=target_lang,
        status="draft",
        origin="corroborated-fleet-glue",
        reason=f"corroborated:{verifier_label}",
        store=store,
        matcher=m,
    )
    pair_id = pair["id"]

    evidence_rows: list[Any] = []
    urls = [s for s in sources if s]
    for loc in urls[:8]:
        kind = "url" if str(loc).startswith("http") else "document"
        try:
            evidence_rows.append(
                evidence.attach(
                    pair_id,
                    kind=kind,
                    locator=str(loc),
                    reason="corroborated",
                    attached_by=verifier_label,
                    store=store,
                )
            )
        except Exception as exc:
            evidence_rows.append({"error": type(exc).__name__, "detail": str(exc), "locator": loc})

    host = "fleet-glue"
    primary = urls[0] if urls else "fleet-glue:corroborate"
    if primary.startswith("http"):
        host = urlparse(primary).netloc or "web"

    try:
        w = warrant.attach(
            pair_id,
            kind="citation",
            authority=f"corroborated:{host}",
            locator=primary,
            check=check_note or (
                f"Machine corroboration via {verifier_label} against "
                f"{len(urls)} source(s); human seal still required for tier-1."
            ),
            attached_by=verifier_label,
            store=store,
        )
    except Exception as exc:
        w = {"error": type(exc).__name__, "detail": str(exc)}

    return {
        "pair_id": pair_id,
        "status": "draft",
        "rung": "corroborated",
        "sources": urls,
        "evidence": evidence_rows,
        "warrant": w,
    }
