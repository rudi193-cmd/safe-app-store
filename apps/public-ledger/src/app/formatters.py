"""
Ledger Persona Formatting
=========================
Template-based narrative output in the Ledger voice.
No LLM needed — precision over flourish.
"""

from .personas import get_persona


VERDICT_LABELS = {
    "SUPPORTED": "The public record supports this claim.",
    "PARTIALLY_SUPPORTED": "The public record partially supports this claim, with caveats.",
    "UNSUPPORTED": "The public record does not support this claim.",
    "INSUFFICIENT_DATA": "The available public data is insufficient to confirm or deny this claim.",
    "DISPUTED": "The public record contradicts specific elements of this claim.",
}


def format_narrative(claim, verdict, evidence, discrepancy=None):
    """Build a Ledger-voice narrative for an audit result."""
    lines = []

    lines.append(f"CLAIM: {claim.text}")
    lines.append("")
    lines.append(VERDICT_LABELS.get(verdict, verdict))
    lines.append("")

    if evidence:
        lines.append("PUBLIC RECORD:")
        for ev in evidence:
            amount = f" — ${ev.value_found:,.2f}" if ev.value_found else ""
            lines.append(f"  [{ev.api_source}]{amount}: {ev.description}")
            lines.append(f"    Source: {ev.url}")
        lines.append("")

    if discrepancy:
        lines.append(f"NOTE: {discrepancy}")
        lines.append("")

    lines.append("Here is what you can look up yourself, and where:")
    sources_seen = set()
    for ev in evidence:
        if ev.url not in sources_seen:
            lines.append(f"  - {ev.url}")
            sources_seen.add(ev.url)

    return "\n".join(lines)


def format_single_result(result):
    """Structure an AuditResult for API response."""
    return {
        "claim_id": result.claim.claim_id,
        "claim_text": result.claim.text,
        "verdict": result.verdict,
        "confidence": result.confidence,
        "narrative": result.ledger_narrative,
        "evidence_count": len(result.evidence),
        "evidence": [
            {
                "source": ev.api_source,
                "url": ev.url,
                "field": ev.raw_field,
                "value": ev.value_found,
                "description": ev.description,
                "fetched_at": ev.fetched_at,
            }
            for ev in result.evidence
        ],
        "discrepancy": result.discrepancy,
        "audited_at": result.audited_at,
    }


def format_batch_summary(results):
    """Aggregate summary of a batch audit."""
    verdicts = {}
    for r in results:
        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1

    return {
        "total_claims": len(results),
        "verdicts": verdicts,
        "sources_used": list({ev.api_source for r in results for ev in r.evidence}),
        "results": [format_single_result(r) for r in results],
    }
