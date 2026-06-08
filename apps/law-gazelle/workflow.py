"""
workflow.py — lawyer-led action cards and workflow inference.

Converts urgent_queue rows into guided work cards with recommended next actions.
b17: LGWF1  ΔΣ=42
"""

from __future__ import annotations

from typing import Any

import document_store
import gazelle_state
from case_store import get_atom_detail, urgent_queue

# Card display status
STATUS_OVERDUE = "overdue"
STATUS_DUE_SOON = "due_soon"
STATUS_BLOCKED = "blocked"
STATUS_READY_TO_DRAFT = "ready_to_draft"
STATUS_NEEDS_REVIEW = "needs_review"

STATUS_LABELS = {
    STATUS_OVERDUE: "Overdue",
    STATUS_DUE_SOON: "Due Soon",
    STATUS_BLOCKED: "Blocked",
    STATUS_READY_TO_DRAFT: "Ready to Draft",
    STATUS_NEEDS_REVIEW: "Needs Review",
}

MATTER_LABELS = {
    "coparent": "Coparent",
    "bankruptcy": "Bankruptcy",
    "workers_comp": "Workers Comp",
    "cross_case": "Cross-Case",
}

ACTION_DRAFT_SCHEDULE = "draft_schedule_response"
ACTION_DRAFT_ALL_OTHER = "draft_all_other"
ACTION_BUILD_PACKET = "build_packet"
ACTION_VERIFY_FACT = "verify_fact"
ACTION_REVIEW_DEADLINE = "review_deadline"
ACTION_ADD_NOTE = "add_note"

ACTION_LABELS = {
    ACTION_DRAFT_SCHEDULE: "Draft schedule response",
    ACTION_DRAFT_ALL_OTHER: "Draft all-other letter",
    ACTION_BUILD_PACKET: "Build drafting packet",
    ACTION_VERIFY_FACT: "Verify facts & sources",
    ACTION_REVIEW_DEADLINE: "Review deadline",
    ACTION_ADD_NOTE: "Add note",
}

DECK_TRIAGE = "deck_triage"
DECK_BUILD_PACKET = "deck_build_packet"
DECK_AI_BRIEF = "deck_ai_brief"
DECK_AI_DRAFT = "deck_ai_draft"
DECK_DRAFT = "deck_draft"
DECK_REVIEW_FACTS = "deck_review_facts"
DECK_SOURCE_DETAIL = "deck_source_detail"

DECK_STEPS = [
    (DECK_TRIAGE, "1. Triage", "Note, snooze, or mark resolved (n / z / x)"),
    (DECK_BUILD_PACKET, "2. Build Packet", "Facts, chronology, citations, gaps"),
    (DECK_AI_BRIEF, "3. AI Brief", "Local Ollama summary, gaps, next steps"),
    (DECK_AI_DRAFT, "4. AI Draft", "Local Ollama first-pass letter (review before save)"),
    (DECK_DRAFT, "5. Packet", "View drafting packet (no LLM)"),
    (DECK_REVIEW_FACTS, "6. Review Facts", "Verify sources before using in filings"),
    (DECK_SOURCE_DETAIL, "7. Source Detail", "Full case record for this item"),
]


def card_id_for_item(item: dict) -> str:
    source_db = item.get("source_db") or item.get("case", "")
    item_type = item.get("item_type") or item.get("kind", "")
    item_id = item.get("item_id") or item.get("flag_id") or item.get("atom_id", "")
    return f"{source_db}:{item_type}:{item_id}"


def _matter_label(item: dict) -> str:
    case = item.get("case") or item.get("source_db") or ""
    return MATTER_LABELS.get(case, case.replace("_", " ").title())


def _infer_why(item: dict) -> str:
    kind = item.get("kind") or item.get("item_type", "")
    if kind == "deadline":
        dl = item.get("deadline") or ""
        days = item.get("days_until")
        if item.get("overdue"):
            return f"Response deadline passed ({dl})"
        if days is not None:
            return f"Response due {dl} ({days} days)"
        return f"Hard deadline: {item.get('title', '')}"
    if kind == "flag":
        sev = item.get("severity") or "HIGH"
        return f"Critical flag ({sev}) — action required"
    if kind == "atom":
        domain = item.get("domain") or ""
        priority = item.get("priority") or ""
        if domain == "schedule":
            return "Schedule/custody item — letter response context"
        return f"Open {priority} atom — review before drafting"
    return "Requires attention in active matters"


def _fact_blocked(item: dict) -> bool:
    if item.get("kind") != "atom" and item.get("item_type") != "atom":
        return False
    source_db = item.get("source_db") or item.get("case", "")
    item_id = item.get("item_id") or item.get("atom_id", "")
    status = gazelle_state.get_fact_verification(source_db, "atom", item_id)
    return status == "needs_source"


def infer_recommended_action(item: dict) -> str:
    kind = item.get("kind") or item.get("item_type", "")
    if kind == "deadline":
        key = item.get("deadline_key") or ""
        if key == "schedule":
            return ACTION_DRAFT_SCHEDULE
        if key == "all_other":
            return ACTION_DRAFT_ALL_OTHER
        return ACTION_REVIEW_DEADLINE
    if kind == "flag":
        return ACTION_VERIFY_FACT
    if kind == "atom":
        domain = item.get("domain") or ""
        if _fact_blocked(item):
            return ACTION_VERIFY_FACT
        if domain == "schedule":
            return ACTION_DRAFT_SCHEDULE
        return ACTION_VERIFY_FACT
    return ACTION_ADD_NOTE


def infer_card_status(item: dict) -> str:
    if _fact_blocked(item):
        return STATUS_BLOCKED
    if item.get("overdue"):
        return STATUS_OVERDUE
    days = item.get("days_until")
    if days is not None and days <= 7:
        return STATUS_DUE_SOON
    action = infer_recommended_action(item)
    if action in (ACTION_DRAFT_SCHEDULE, ACTION_DRAFT_ALL_OTHER):
        return STATUS_READY_TO_DRAFT
    return STATUS_NEEDS_REVIEW


def item_to_action_card(item: dict) -> dict:
    """Build a workflow action card from an urgent_queue row."""
    source = dict(item)
    action = infer_recommended_action(item)
    cid = card_id_for_item(item)
    return {
        "card_id": cid,
        "matter": _matter_label(item),
        "matter_key": item.get("case") or item.get("source_db", ""),
        "status": infer_card_status(item),
        "status_label": STATUS_LABELS[infer_card_status(item)],
        "title": (
            item.get("title")
            or item.get("flag_id")
            or item.get("atom_id")
            or item.get("item_id")
            or "—"
        ),
        "why": _infer_why(item),
        "recommended_action": action,
        "recommended_action_label": ACTION_LABELS.get(action, action),
        "source_item": source,
        # For TUI row registration
        "source_db": "workflow",
        "item_type": "action_card",
        "item_id": cid,
        "kind": "action_card",
    }


def today_cards(show_resolved: bool = False) -> list[dict]:
    """All action cards for the Today home screen."""
    return [item_to_action_card(item) for item in urgent_queue(show_resolved=show_resolved)]


def action_deck_entries(card: dict) -> list[dict]:
    """Rows for the action deck route."""
    entries: list[dict] = []
    for step_id, label, desc in DECK_STEPS:
        entries.append({
            "source_db": "workflow",
            "item_type": "deck_step",
            "item_id": step_id,
            "step_id": step_id,
            "label": label,
            "description": desc,
            "card": card,
        })
    return entries


def suggested_doc_type(card: dict) -> str | None:
    action = card.get("recommended_action")
    if action == ACTION_DRAFT_SCHEDULE:
        return "schedule_response"
    if action == ACTION_DRAFT_ALL_OTHER:
        return "letter_all_other"
    source = card.get("source_item") or {}
    if source.get("domain") == "schedule":
        return "schedule_response"
    return None


def atom_ids_for_card(card: dict) -> list[str]:
    source = card.get("source_item") or {}
    kind = source.get("kind") or source.get("item_type", "")
    if kind == "atom":
        aid = source.get("atom_id") or source.get("item_id")
        return [aid] if aid else []
    if kind == "deadline" and source.get("deadline_key") == "schedule":
        from case_store import schedule_atoms

        return [r["atom_id"] for r in schedule_atoms(status="open")[:15]]
    return []


def build_packet_markdown(card: dict) -> str:
    """Drafting packet markdown for Build Packet / Draft deck steps."""
    doc_type = suggested_doc_type(card)
    if not doc_type:
        return (
            "# No automatic packet\n\n"
            "This item does not map to a standard letter type. "
            "Use **Review Facts** or **Source Detail** first.\n"
        )
    atom_ids = atom_ids_for_card(card)
    ctx = document_store.draft_context(doc_type, atom_ids=atom_ids or None)
    if ctx.get("error"):
        return ctx["error"]
    header = [
        f"# Drafting Packet: {card.get('title', '')}",
        "",
        f"**Recommended:** {card.get('recommended_action_label', '')}",
        f"**Why:** {card.get('why', '')}",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + document_store.format_draft_context_markdown(ctx)


def fact_review_rows(card: dict) -> list[dict]:
    """Fact review table rows for an action card."""
    source = card.get("source_item") or {}
    kind = source.get("kind") or source.get("item_type", "")
    rows: list[dict] = []

    if kind == "atom":
        aid = source.get("atom_id") or source.get("item_id")
        detail = get_atom_detail(aid, source_db=source.get("source_db", "coparent"))
        if detail:
            atom = detail.get("atom") or {}
            ev_count = len(detail.get("evidence") or [])
            fv = gazelle_state.get_fact_verification(
                source.get("source_db", "coparent"), "atom", aid
            )
            rows.append({
                "source_db": "workflow",
                "item_type": "fact_review",
                "item_id": aid,
                "atom_id": aid,
                "fact": _fact_title(atom, aid),
                "verification": fv or "unreviewed",
                "review_status": verification_label(fv),
                "review_action": _review_action(fv, ev_count),
                "evidence": _evidence_summary(detail),
                "source_summary": _source_summary(detail),
                "case_summary": _case_summary(atom),
                "card": card,
                "detail": detail,
            })
        return rows

    if kind == "deadline":
        doc = suggested_doc_type(card)
        if doc == "schedule_response":
            from case_store import schedule_atoms

            for row in schedule_atoms(status="open")[:20]:
                aid = row["atom_id"]
                detail = get_atom_detail(aid)
                ev_count = len((detail or {}).get("evidence") or [])
                fv = gazelle_state.get_fact_verification("coparent", "atom", aid)
                rows.append({
                    "source_db": "workflow",
                    "item_type": "fact_review",
                    "item_id": aid,
                    "atom_id": aid,
                    "fact": _fact_title(row, aid),
                    "verification": fv or "unreviewed",
                    "review_status": verification_label(fv),
                    "review_action": _review_action(fv, ev_count),
                    "evidence": _evidence_summary(detail),
                    "source_summary": _source_summary(detail),
                    "case_summary": _case_summary((detail or {}).get("atom") or row),
                    "card": card,
                    "detail": detail,
                })
        return rows

    rows.append({
        "source_db": "workflow",
        "item_type": "fact_review",
        "item_id": "none",
        "fact": "No discrete facts — review source detail",
        "verification": "—",
        "review_status": "—",
        "review_action": "Open source detail",
        "evidence": "—",
        "source_summary": "—",
        "case_summary": "This item does not expose atom-level facts.",
        "card": card,
    })
    return rows


def _fact_title(atom: dict, fallback: str) -> str:
    title = atom.get("title") or atom.get("fact") or fallback
    aid = atom.get("atom_id") or fallback
    return f"{aid}: {title}" if aid and not str(title).startswith(str(aid)) else str(title)


def _case_summary(atom: dict) -> str:
    parts = []
    for key in ("action_required", "summary", "description", "content", "note"):
        val = atom.get(key)
        if val:
            parts.append(str(val))
            break
    domain = atom.get("domain")
    priority = atom.get("priority")
    meta = " · ".join(str(x) for x in (domain, priority) if x)
    text = parts[0] if parts else "No action text in atom."
    return f"{text} ({meta})" if meta else text


def _evidence_summary(detail: dict | None) -> str:
    if not detail:
        return "No detail loaded"
    evidence = detail.get("evidence") or []
    citations = detail.get("citations") or []
    docs = detail.get("documents") or detail.get("sources") or []
    counts = []
    if evidence:
        counts.append(f"{len(evidence)} evidence")
    if citations:
        counts.append(f"{len(citations)} citations")
    if docs:
        counts.append(f"{len(docs)} docs")
    return ", ".join(counts) if counts else "No linked evidence"


def _source_summary(detail: dict | None) -> str:
    if not detail:
        return "Open source detail"
    for key in ("evidence", "citations", "documents", "sources"):
        rows = detail.get(key) or []
        if rows:
            first = rows[0]
            if isinstance(first, dict):
                return (
                    first.get("title")
                    or first.get("name")
                    or first.get("citation")
                    or first.get("source")
                    or str(first)[:80]
                )
            return str(first)[:80]
    return "Needs source"


def _review_action(status: str | None, evidence_count: int) -> str:
    if status == "verified":
        return "Ready to use in draft"
    if status == "do_not_use":
        return "Excluded from drafting"
    if status == "needs_source" or evidence_count == 0:
        return "Find/source before using"
    return "Press 1 verified, 2 needs source, 3 do not use"


def verification_label(status: str | None) -> str:
    if status == "verified":
        return "Verified"
    if status == "needs_source":
        return "Needs source"
    if status == "do_not_use":
        return "Do not use"
    return "Unreviewed"
