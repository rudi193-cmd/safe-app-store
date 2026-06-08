"""
intelligence.py — Local LLM intelligence for Law Gazelle.

Drafting copilot, action-card briefing, and Today triage ranking.
Uses tool_context (Gazelle + CourtListener) then Ollama.

b17: LGINT1  ΔΣ=42
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import document_store
import gazelle_state
import llm_client
import tool_context
import workflow

SYSTEM_PROMPT = """You are Law Gazelle, a legal operations assistant for a pro se litigant.

Rules:
- Use ONLY facts from the CASE FACTS section for this matter's events, dates, parties, and atoms.
- LEGAL RESEARCH from CourtListener is background authority only — never treat it as evidence of what happened in this case.
- Do not cite or discuss case law unless it appears in the LEGAL RESEARCH section.
- Do NOT invent dates, amounts, court orders, or events.
- Preserve markers: [FACT NEEDED], [VERIFY], [UNCERTAIN] — do not remove or fill them with guesses.
- Be concise and actionable. This is not legal advice.
"""


def _run(prompt: str) -> dict[str, Any]:
    result = llm_client.generate(prompt, system=SYSTEM_PROMPT)
    return {
        "ok": result.get("ok", False),
        "text": result.get("text", ""),
        "model": result.get("model"),
        "provider": result.get("provider"),
        "error": result.get("error"),
    }


def _cached_or_run(
    *,
    cache_key: str,
    event_type: str,
    fingerprint: str,
    source_db: str | None,
    item_type: str | None,
    item_id: str | None,
    run: Callable[[], dict[str, Any]],
    force: bool = False,
) -> dict[str, Any]:
    """Return sidecar-cached LLM output when fingerprint matches; else run Ollama."""
    if not force:
        hit = gazelle_state.get_ai_cache(cache_key, fingerprint=fingerprint)
        if hit:
            return {
                "ok": True,
                "text": hit["body"],
                "model": hit.get("model"),
                "provider": "sidecar",
                "error": None,
                "cached": True,
                "cached_at": hit.get("created_at"),
            }

    out = run()
    if out.get("ok") and out.get("text"):
        gazelle_state.put_ai_cache(
            cache_key,
            event_type,
            out["text"],
            model=out.get("model"),
            fingerprint=fingerprint,
            source_db=source_db,
            item_type=item_type,
            item_id=item_id,
        )
    out["cached"] = False
    return out


def _fact_scope(row: dict) -> tuple[str, str, str]:
    atom_id = row.get("atom_id") or row.get("item_id") or ""
    source_db = ((row.get("card") or {}).get("source_item") or {}).get("source_db", "coparent")
    return source_db, "atom", atom_id


def _fact_fingerprint(row: dict) -> str:
    source_db, item_type, item_id = _fact_scope(row)
    detail = row.get("detail") or {}
    return gazelle_state.fingerprint_payload(
        {
            "atom_id": item_id,
            "verification": gazelle_state.get_fact_verification(source_db, item_type, item_id),
            "fact": row.get("fact"),
            "case_summary": row.get("case_summary"),
            "source_summary": row.get("source_summary") or row.get("evidence"),
            "evidence_count": len(detail.get("evidence") or []),
            "citation_count": len(detail.get("citations") or []),
        }
    )


def _card_fingerprint(card: dict, *, extra: dict | None = None) -> str:
    source = card.get("source_item") or {}
    source_db = source.get("source_db") or source.get("case", "")
    item_type = source.get("item_type") or source.get("kind", "")
    item_id = source.get("item_id") or source.get("flag_id") or source.get("atom_id", "")
    verification = (
        gazelle_state.get_fact_verification(source_db, item_type, item_id)
        if item_id and item_type
        else None
    )
    payload: dict[str, Any] = {
        "card_id": card.get("card_id"),
        "status": card.get("status"),
        "recommended_action": card.get("recommended_action"),
        "source_item_id": item_id,
        "verification": verification,
    }
    if extra:
        payload.update(extra)
    return gazelle_state.fingerprint_payload(payload)


def _rank_fingerprint(cards: list[dict]) -> str:
    rows = [
        {
            "card_id": c.get("card_id"),
            "status": c.get("status"),
            "title": c.get("title"),
        }
        for c in cards
    ]
    return gazelle_state.fingerprint_payload({"cards": rows})


def brief_card(
    card: dict,
    *,
    include_courtlistener: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Summarize risks, gaps, and recommended next steps for one action card."""
    bundle = tool_context.build_context_bundle(
        card=card, include_courtlistener=include_courtlistener
    )
    context = tool_context.format_context_for_prompt(bundle)
    prompt = f"""Brief this work item for the attorney.

Output markdown with sections:
1. **What this is** (1-2 sentences)
2. **Why it matters now**
3. **Fact gaps** (list [FACT NEEDED] / unverified items)
4. **Recommended next steps** (numbered, concrete)
5. **Risks if delayed**

Do not draft a full letter.

{context}
"""
    source = card.get("source_item") or {}
    cache_key = gazelle_state.ai_cache_key(
        "ai_brief", card.get("card_id") or workflow.card_id_for_item(source)
    )
    fingerprint = _card_fingerprint(
        card, extra={"include_courtlistener": include_courtlistener}
    )

    def run() -> dict[str, Any]:
        out = _run(prompt)
        out["card_id"] = card.get("card_id")
        out["context_sources"] = _source_labels(bundle)
        return out

    out = _cached_or_run(
        cache_key=cache_key,
        event_type="ai_brief",
        fingerprint=fingerprint,
        source_db=source.get("source_db") or source.get("case"),
        item_type=source.get("item_type") or source.get("kind"),
        item_id=source.get("item_id") or source.get("flag_id") or source.get("atom_id"),
        run=run,
        force=force,
    )
    out["card_id"] = card.get("card_id")
    if not out.get("context_sources"):
        out["context_sources"] = _source_labels(bundle)
    if out.get("ok") and not out.get("cached"):
        gazelle_state.log_activity(
            "ai_brief",
            f"AI briefing for {card.get('card_id', '')}",
            source_db=source.get("source_db"),
            item_type=source.get("item_type") or source.get("kind"),
            item_id=source.get("item_id") or source.get("flag_id") or source.get("atom_id"),
        )
    return out


def draft_from_card(
    card: dict,
    *,
    include_courtlistener: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Generate a first-pass draft from packet + tool context."""
    doc_type = workflow.suggested_doc_type(card)
    if not doc_type:
        return {
            "ok": False,
            "text": "",
            "error": "No standard document type for this card. Use Brief or Review Facts first.",
            "doc_type": None,
        }

    atom_ids = workflow.atom_ids_for_card(card)
    ctx = document_store.draft_context(doc_type, atom_ids=atom_ids or None)
    if ctx.get("error"):
        return {"ok": False, "text": "", "error": ctx["error"], "doc_type": doc_type}

    bundle = tool_context.build_context_bundle(
        card=card, include_courtlistener=include_courtlistener
    )
    context = tool_context.format_context_for_prompt(bundle)
    template = ctx.get("structure_template") or ""
    instructions = ctx.get("writing_instructions") or ""

    prompt = f"""Produce a first-pass draft letter in markdown.

Document type: {doc_type}
Writing instructions: {instructions}

Fill the structure template below. Keep all [FACT NEEDED], [VERIFY], and [UNCERTAIN] markers where facts are missing.
Do not invent facts. Use only CASE FACTS for this matter.

Structure template:
{template}

{context}
"""
    source = card.get("source_item") or {}
    cache_key = gazelle_state.ai_cache_key(
        "ai_draft", card.get("card_id") or workflow.card_id_for_item(source)
    )
    fingerprint = _card_fingerprint(
        card,
        extra={
            "doc_type": doc_type,
            "atom_ids": atom_ids,
            "include_courtlistener": include_courtlistener,
        },
    )

    def run() -> dict[str, Any]:
        out = _run(prompt)
        out["doc_type"] = doc_type
        out["suggested_filename"] = f"CaseDraft_{doc_type}_{date.today().isoformat()}.md"
        out["context_sources"] = _source_labels(bundle)
        return out

    out = _cached_or_run(
        cache_key=cache_key,
        event_type="ai_draft",
        fingerprint=fingerprint,
        source_db=source.get("source_db") or source.get("case"),
        item_type=source.get("item_type") or source.get("kind"),
        item_id=source.get("item_id") or source.get("flag_id") or source.get("atom_id"),
        run=run,
        force=force,
    )
    out.setdefault("doc_type", doc_type)
    out.setdefault(
        "suggested_filename", f"CaseDraft_{doc_type}_{date.today().isoformat()}.md"
    )
    if not out.get("context_sources"):
        out["context_sources"] = _source_labels(bundle)
    if out.get("ok") and not out.get("cached"):
        gazelle_state.log_activity(
            "ai_draft",
            f"AI draft ({doc_type}) for {card.get('card_id', '')}",
            source_db=source.get("source_db"),
            item_type=source.get("item_type") or source.get("kind"),
            item_id=source.get("item_id") or source.get("flag_id") or source.get("atom_id"),
        )
    return out


def rank_today(
    cards: list[dict],
    *,
    include_courtlistener: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Rank Today action cards by urgency and explain ordering."""
    if not cards:
        return {"ok": True, "text": "No action cards on Today.", "error": None}

    bundle = tool_context.build_context_bundle(cards=cards, include_courtlistener=include_courtlistener)
    context = tool_context.format_context_for_prompt(bundle)
    card_lines = "\n".join(
        f"- {c.get('card_id')}: {c.get('status_label')} | {c.get('title')} | {c.get('why')}"
        for c in cards
    )

    prompt = f"""Rank these Today work items from highest to lowest priority.

Output markdown:
1. **Ranked list** — use card_id, one line each with reason
2. **Top 3 to do first** — bullet list
3. **Can wait** — items safe to defer briefly

Use deadlines, overdue status, and blocked/verify states.

Cards:
{card_lines}

{context}
"""
    cache_key = gazelle_state.ai_cache_key("ai_rank", "today")
    fingerprint = _rank_fingerprint(cards)

    def run() -> dict[str, Any]:
        out = _run(prompt)
        out["context_sources"] = _source_labels(bundle)
        return out

    out = _cached_or_run(
        cache_key=cache_key,
        event_type="ai_rank",
        fingerprint=fingerprint,
        source_db=None,
        item_type=None,
        item_id=None,
        run=run,
        force=force,
    )
    if not out.get("context_sources"):
        out["context_sources"] = _source_labels(bundle)
    if out.get("ok") and not out.get("cached"):
        gazelle_state.log_activity("ai_rank", f"AI ranked {len(cards)} Today cards")
    return out


def fact_inspection_cache_key(row: dict) -> tuple[str, str]:
    """Return (cache_key, fingerprint) for a fact review row."""
    source_db, _, item_id = _fact_scope(row)
    return (
        gazelle_state.ai_cache_key("ai_fact_inspect", f"{source_db}:{item_id}"),
        _fact_fingerprint(row),
    )


def brief_cache_key(card: dict, *, include_courtlistener: bool = False) -> tuple[str, str]:
    source = card.get("source_item") or {}
    key = gazelle_state.ai_cache_key(
        "ai_brief", card.get("card_id") or workflow.card_id_for_item(source)
    )
    return key, _card_fingerprint(card, extra={"include_courtlistener": include_courtlistener})


def draft_cache_key(card: dict, *, include_courtlistener: bool = False) -> tuple[str, str] | None:
    doc_type = workflow.suggested_doc_type(card)
    if not doc_type:
        return None
    source = card.get("source_item") or {}
    key = gazelle_state.ai_cache_key(
        "ai_draft", card.get("card_id") or workflow.card_id_for_item(source)
    )
    return key, _card_fingerprint(
        card,
        extra={
            "doc_type": doc_type,
            "atom_ids": workflow.atom_ids_for_card(card),
            "include_courtlistener": include_courtlistener,
        },
    )


def rank_cache_key(cards: list[dict]) -> tuple[str, str]:
    return gazelle_state.ai_cache_key("ai_rank", "today"), _rank_fingerprint(cards)


def inspect_fact_row(row: dict, *, force: bool = False) -> dict[str, Any]:
    """Review one fact row and suggest a verification status without applying it."""
    atom_id = row.get("atom_id") or row.get("item_id")
    if not atom_id or atom_id == "none":
        return {
            "ok": False,
            "text": "",
            "error": "Select a fact row with an atom before asking AI to inspect it.",
        }

    detail = row.get("detail") or {}
    prompt = f"""Inspect this fact for attorney review.

Output markdown with sections:
1. **Suggested status** — choose one: verified, needs_source, do_not_use
2. **Why** — explain the evidence basis in 2-4 bullets
3. **What to check next** — concrete source checks before drafting
4. **Draft-safe wording** — one cautious sentence, or [FACT NEEDED]

Do not change verification status. Do not say a fact is verified unless linked evidence supports it.

Fact row:
- Atom: {atom_id}
- Fact: {row.get('fact', '')}
- Current status: {row.get('review_status') or row.get('verification') or 'unreviewed'}
- What to check: {row.get('case_summary', '')}
- Source summary: {row.get('source_summary') or row.get('evidence') or ''}

Underlying detail:
{tool_context._excerpt(detail, max_len=6000)}
"""
    source_db, item_type, item_id = _fact_scope(row)
    cache_key = gazelle_state.ai_cache_key("ai_fact_inspect", f"{source_db}:{item_id}")
    fingerprint = _fact_fingerprint(row)

    def run() -> dict[str, Any]:
        out = _run(prompt)
        out["context_sources"] = [f"fact:{atom_id}"]
        return out

    out = _cached_or_run(
        cache_key=cache_key,
        event_type="ai_fact_inspect",
        fingerprint=fingerprint,
        source_db=source_db,
        item_type=item_type,
        item_id=item_id,
        run=run,
        force=force,
    )
    out["atom_id"] = atom_id
    out.setdefault("context_sources", [f"fact:{atom_id}"])
    if out.get("ok") and not out.get("cached"):
        gazelle_state.log_activity(
            "ai_fact_inspect",
            f"AI inspected fact {atom_id} (review-only)",
            source_db=source_db,
            item_type=item_type,
            item_id=item_id,
        )
    return out


def _source_labels(bundle: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for b in bundle.get("case_facts") or []:
        labels.append(f"case:{b.get('source')}")
    for b in bundle.get("legal_research") or []:
        labels.append(f"research:{b.get('source')}")
    return labels
