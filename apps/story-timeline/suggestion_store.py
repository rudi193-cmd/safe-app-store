"""Local suggestion and research record storage for story-timeline intelligence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import timeline_db as db

SLM_SUGGESTION = "slm_suggestion"
RESEARCH_PACKET = "research_packet"

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DISMISSED = "dismissed"


def create_research_packet(
    source_id: str,
    *,
    query: str,
    summary: str = "",
    sources: list[dict] | None = None,
    provider: str = "jeles",
    raw: dict | None = None,
) -> dict:
    fields = {
        "source_id": source_id,
        "query": query.strip(),
        "summary": summary.strip(),
        "sources": sources or [],
        "provider": provider,
        "raw": raw or {},
        "created_at": datetime.now().isoformat(),
    }
    node_id = db.add_node(type_=RESEARCH_PACKET, fields=fields)
    return db.get_node(node_id)


def create_suggestion(
    source_id: str,
    *,
    suggestion_kind: str,
    proposed_fields: dict,
    supporting_sources: list[dict] | None = None,
    research_id: str = "",
    confidence: float = 0.0,
    model: str = "",
    status: str = STATUS_PENDING,
) -> dict:
    fields = {
        "source_id": source_id,
        "suggestion_kind": suggestion_kind,
        "proposed_fields": proposed_fields,
        "supporting_sources": supporting_sources or [],
        "research_id": research_id,
        "confidence": confidence,
        "model": model,
        "status": status,
        "created_at": datetime.now().isoformat(),
    }
    node_id = db.add_node(type_=SLM_SUGGESTION, fields=fields)
    return db.get_node(node_id)


def get_research_packet(research_id: str) -> Optional[dict]:
    node = db.get_node(research_id)
    if node and node["type"] == RESEARCH_PACKET:
        return node
    return None


def get_suggestion(suggestion_id: str) -> Optional[dict]:
    node = db.get_node(suggestion_id)
    if node and node["type"] == SLM_SUGGESTION:
        return node
    return None


def update_suggestion_status(suggestion_id: str, status: str) -> bool:
    node = get_suggestion(suggestion_id)
    if not node:
        return False
    fields = dict(node.get("fields", {}))
    fields["status"] = status
    fields["updated_at"] = datetime.now().isoformat()
    return db.update_node(suggestion_id, fields)


def list_suggestions_for_source(source_id: str, *, status: str | None = None) -> list[dict]:
    nodes = db.get_nodes(type_=SLM_SUGGESTION)
    out = [n for n in nodes if n["fields"].get("source_id") == source_id]
    if status:
        out = [n for n in out if n["fields"].get("status") == status]
    return sorted(out, key=lambda n: n.get("created", ""), reverse=True)


def list_research_for_source(source_id: str) -> list[dict]:
    nodes = db.get_nodes(type_=RESEARCH_PACKET)
    return sorted(
        [n for n in nodes if n["fields"].get("source_id") == source_id],
        key=lambda n: n.get("created", ""),
        reverse=True,
    )


def list_suggestions(*, status: str | None = None) -> list[dict]:
    nodes = db.get_nodes(type_=SLM_SUGGESTION)
    if status:
        nodes = [n for n in nodes if n["fields"].get("status") == status]
    return sorted(nodes, key=lambda n: n.get("created", ""), reverse=True)


def list_research(*, limit: int | None = None) -> list[dict]:
    nodes = sorted(
        db.get_nodes(type_=RESEARCH_PACKET),
        key=lambda n: n.get("created", ""),
        reverse=True,
    )
    if limit is not None:
        return nodes[:limit]
    return nodes


def counts_for_source(source_id: str) -> dict[str, int]:
    return {
        "research": len(list_research_for_source(source_id)),
        "pending_suggestions": len(
            list_suggestions_for_source(source_id, status=STATUS_PENDING)
        ),
        "suggestions": len(list_suggestions_for_source(source_id)),
    }


def pending_for_timeline(timeline_id: str) -> list[dict]:
    pending = list_suggestions(status=STATUS_PENDING)
    return [
        n for n in pending
        if n["fields"].get("proposed_fields", {}).get("timeline_id") == timeline_id
    ]


def dashboard_counts() -> dict[str, int]:
    return {
        "books": len(db.get_nodes(type_="book")),
        "authors": len(db.get_nodes(type_="author")),
        "notes": len(db.get_nodes(type_="note")),
        "library_projects": len(db.get_nodes(type_="project")),
        "writing_projects": len(db.get_nodes(type_="writing_project")),
        "timelines": len(db.get_nodes(type_="timeline")),
        "timeline_entries": len(db.get_nodes(type_="timeline_entry")),
        "pending_suggestions": len(list_suggestions(status=STATUS_PENDING)),
        "research_packets": len(list_research()),
    }


def research_payload(node: dict) -> dict[str, Any]:
    f = node.get("fields", {})
    return {
        "id": node["id"],
        "type": RESEARCH_PACKET,
        "source_id": f.get("source_id"),
        "query": f.get("query"),
        "summary": f.get("summary"),
        "sources": f.get("sources", []),
        "provider": f.get("provider"),
    }
