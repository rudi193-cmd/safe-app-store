"""
tool_context.py — Assemble Gazelle case context and CourtListener research for the LLM.

Uses the same data paths as gazelle_mcp tools (local modules), not duplicate logic.
CourtListener is optional and labeled as legal research only.

b17: LGCTX1  ΔΣ=42
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

import case_store
import document_store
import gazelle_state
import workflow

COURTLISTENER_BASE = os.environ.get(
    "COURTLISTENER_BASE_URL",
    "https://www.courtlistener.com/api/rest/v4",
).rstrip("/")

_CITATION_RE = re.compile(
    r"\b\d+\s+[A-Z][a-z.]*\s+\d+\b|\b\d+\s+U\.?\s*S\.?\s+\d+\b",
)


def _block(
    source: str,
    title: str,
    summary: str,
    *,
    payload: Any = None,
    kind: str = "case_fact",
) -> dict[str, Any]:
    """Structured context block for prompts."""
    return {
        "kind": kind,
        "source": source,
        "title": title,
        "summary": summary,
        "payload_excerpt": _excerpt(payload),
    }


def _excerpt(payload: Any, max_len: int = 4000) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, default=str, indent=2)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def gazelle_context_for_card(card: dict) -> list[dict[str, Any]]:
    """Deterministic case context from Gazelle modules (MCP-equivalent data)."""
    blocks: list[dict[str, Any]] = []
    source = card.get("source_item") or {}

    blocks.append(
        _block(
            "gazelle",
            "Action card",
            (
                f"Title: {card.get('title')}\n"
                f"Status: {card.get('status_label')}\n"
                f"Why: {card.get('why')}\n"
                f"Recommended: {card.get('recommended_action_label')}"
            ),
            kind="case_fact",
        )
    )

    source_db = source.get("source_db") or source.get("case", "")
    item_type = source.get("item_type") or source.get("kind", "")
    item_id = source.get("item_id") or source.get("flag_id") or source.get("atom_id", "")
    if item_id and item_type:
        detail = case_store.get_item_detail(source_db, item_type, item_id)
        if detail:
            blocks.append(
                _block(
                    "gazelle_detail",
                    f"Item detail ({item_type} {item_id})",
                    case_store.format_detail_text(detail),
                    payload=detail,
                    kind="case_fact",
                )
            )
        notes = gazelle_state.list_notes(source_db, item_type, item_id)
        if notes:
            blocks.append(
                _block(
                    "gazelle_notes",
                    "Sidecar notes",
                    "\n".join(f"- {n.get('body', '')}" for n in notes[:10]),
                    payload=notes,
                    kind="case_fact",
                )
            )
        fv = gazelle_state.get_fact_verification(source_db, item_type, item_id)
        if fv:
            blocks.append(
                _block(
                    "gazelle_verification",
                    "Fact verification",
                    f"Status: {fv}",
                    kind="case_fact",
                )
            )

    doc_type = workflow.suggested_doc_type(card)
    if doc_type:
        atom_ids = workflow.atom_ids_for_card(card)
        ctx = document_store.draft_context(doc_type, atom_ids=atom_ids or None)
        if not ctx.get("error"):
            blocks.append(
                _block(
                    "gazelle_draft",
                    f"Draft context ({doc_type})",
                    document_store.format_draft_context_markdown(ctx),
                    payload={"doc_type": doc_type, "atom_ids": ctx.get("atom_ids")},
                    kind="case_fact",
                )
            )

    matter_key = source.get("case") or source.get("source_db") or "coparent"
    if matter_key in ("coparent", "workers_comp"):
        chrono = document_store.chronology_builder(case=matter_key)
        if not chrono.get("error"):
            blocks.append(
                _block(
                    "gazelle_chronology",
                    "Chronology",
                    document_store.format_chronology_markdown(chrono),
                    payload={"event_count": chrono.get("event_count"), "gaps": chrono.get("gaps")},
                    kind="case_fact",
                )
            )

    activity = gazelle_state.list_activity(limit=8)
    if activity:
        lines = [
            f"{e.get('created_at', '')[:19]} [{e.get('event_type')}] {e.get('summary', '')}"
            for e in activity
        ]
        blocks.append(
            _block(
                "gazelle_activity",
                "Recent activity",
                "\n".join(lines),
                kind="case_fact",
            )
        )

    return blocks


def gazelle_context_for_today(cards: list[dict]) -> list[dict[str, Any]]:
    """Brief context for ranking all Today cards."""
    urgent = case_store.urgent_queue(show_resolved=False)
    milestones = case_store.milestone_banner()
    lines = [
        f"- {c.get('status_label', '?')}: {c.get('title', '?')} — {c.get('why', '')}"
        for c in cards[:25]
    ]
    blocks = [
        _block(
            "gazelle_urgent",
            "Raw urgent queue count",
            f"{len(urgent)} items in urgent_queue",
            kind="case_fact",
        ),
        _block(
            "gazelle_today",
            "Today action cards",
            "\n".join(lines) or "(empty)",
            kind="case_fact",
        ),
    ]
    if milestones:
        blocks.append(
            _block("gazelle_milestones", "Milestones", milestones, kind="case_fact")
        )
    return blocks


def _courtlistener_enabled() -> bool:
    if os.environ.get("LAW_GAZELLE_DISABLE_COURTLISTENER", "").lower() in ("1", "true", "yes"):
        return False
    return bool(os.environ.get("COURTLISTENER_API_KEY", "").strip())


def _cl_headers() -> dict[str, str]:
    key = os.environ.get("COURTLISTENER_API_KEY", "").strip()
    return {
        "Authorization": f"Token {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def courtlistener_verify_citations(text: str) -> dict[str, Any]:
    """Verify citations via CourtListener REST (legal research only)."""
    if not _courtlistener_enabled():
        return {"ok": False, "skipped": True, "error": "COURTLISTENER_API_KEY not set"}
    citations = list(dict.fromkeys(_CITATION_RE.findall(text)))[:5]
    if not citations:
        return {"ok": True, "citations": [], "results": [], "message": "No citations found in text"}

    url = f"{COURTLISTENER_BASE}/citation-lookup/"
    try:
        resp = requests.post(
            url,
            headers=_cl_headers(),
            json={"text": "\n".join(citations)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "citations": citations, "results": data, "error": None}
    except requests.RequestException as exc:
        return {"ok": False, "citations": citations, "results": [], "error": str(exc)}


def courtlistener_search(query: str, *, limit: int = 3) -> dict[str, Any]:
    """Keyword search on CourtListener opinions (legal research only)."""
    if not _courtlistener_enabled():
        return {"ok": False, "skipped": True, "error": "COURTLISTENER_API_KEY not set"}
    url = f"{COURTLISTENER_BASE}/search/"
    params = {"q": query, "type": "o", "page_size": limit}
    try:
        resp = requests.get(url, headers=_cl_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "query": query, "results": data, "error": None}
    except requests.RequestException as exc:
        return {"ok": False, "query": query, "results": [], "error": str(exc)}


def courtlistener_context_for_card(card: dict) -> list[dict[str, Any]]:
    """Optional citation-verification blocks — never broad case-law search."""
    blocks: list[dict[str, Any]] = []
    if not _courtlistener_enabled():
        return blocks

    packet_md = workflow.build_packet_markdown(card)
    verify = courtlistener_verify_citations(packet_md)
    if verify.get("ok") and verify.get("citations"):
        blocks.append(
            _block(
                "courtlistener_citations",
                "Citation verification",
                _excerpt(verify.get("results"), 3000),
                payload=verify,
                kind="legal_research",
            )
        )
    elif verify.get("error") and not verify.get("skipped"):
        blocks.append(
            _block(
                "courtlistener_citations",
                "Citation verification (error)",
                verify["error"],
                kind="legal_research",
            )
        )

    return blocks


def build_context_bundle(
    *,
    card: dict | None = None,
    cards: list[dict] | None = None,
    include_courtlistener: bool = True,
) -> dict[str, Any]:
    """Full context bundle for intelligence prompts."""
    case_blocks: list[dict[str, Any]] = []
    research_blocks: list[dict[str, Any]] = []

    if card:
        case_blocks.extend(gazelle_context_for_card(card))
        if include_courtlistener:
            research_blocks.extend(courtlistener_context_for_card(card))
    if cards:
        case_blocks.extend(gazelle_context_for_today(cards))

    return {
        "case_facts": case_blocks,
        "legal_research": research_blocks,
    }


def format_context_for_prompt(bundle: dict[str, Any]) -> str:
    """Render context blocks into prompt sections."""
    parts: list[str] = []

    if bundle.get("case_facts"):
        parts.append("## CASE FACTS (from Gazelle — authoritative for this matter)")
        for b in bundle["case_facts"]:
            parts.append(f"\n### {b['title']} [{b['source']}]\n{b['summary']}")

    if bundle.get("legal_research"):
        parts.append("\n## LEGAL RESEARCH (CourtListener — not case evidence)")
        for b in bundle["legal_research"]:
            parts.append(f"\n### {b['title']} [{b['source']}]\n{b['summary']}")

    return "\n".join(parts)
