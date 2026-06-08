"""
story_protocol.py — Record contract for story-timeline.

Turns commonplace material (books, notes, ideas, imports) into named
timeline entries across multiple writing projects, with provenance and
SOIL-facing collection conventions.

Local nodes remain in timeline_db; protocol types use stable `type` values
and `fields` shapes. Relations use willow_edges with a small standard vocabulary.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import timeline_db as db
import willow_edges

APP_ID = "story-timeline"

# Protocol node types (stored in timeline_db.nodes.type)
COMMONPLACE_ITEM = "commonplace_item"
WRITING_PROJECT = "writing_project"
TIMELINE = "timeline"
TIMELINE_ENTRY = "timeline_entry"

PROTOCOL_TYPES = frozenset({
    COMMONPLACE_ITEM,
    WRITING_PROJECT,
    TIMELINE,
    TIMELINE_ENTRY,
})

WRITING_PROJECT_TYPES = frozenset({WRITING_PROJECT})

# Existing writer-tool types that may be promoted into timelines
PROMOTABLE_SOURCE_TYPES = frozenset({
    "note",
    "book",
    "author",
    "commonplace_item",
    "project",
    "theme",
    "character",
    "place",
    "event",
})

# Stable relation labels for agents and cross-app reads
REL_DERIVED_FROM = "derived_from"
REL_BELONGS_TO_PROJECT = "belongs_to_project"
REL_APPEARS_ON_TIMELINE = "appears_on_timeline"
REL_INSPIRED_BY = "inspired_by"
REL_SUPPORTS_SCENE = "supports_scene"
REL_CONTRADICTS = "contradicts_or_tensions_with"

STANDARD_RELATIONS = frozenset({
    REL_DERIVED_FROM,
    REL_BELONGS_TO_PROJECT,
    REL_APPEARS_ON_TIMELINE,
    REL_INSPIRED_BY,
    REL_SUPPORTS_SCENE,
    REL_CONTRADICTS,
})

# SOIL collection suffixes under user-{uuid}/story-timeline/
COLLECTION_COMMONPLACE = "commonplace"
COLLECTION_TIMELINES = "timelines"
COLLECTION_TIMELINE_ENTRIES = "timeline_entries"
COLLECTION_ATOMS = "atoms"
COLLECTION_EDGES = "_graph/edges"

COLLECTIONS = {
    COMMONPLACE_ITEM: COLLECTION_COMMONPLACE,
    TIMELINE: COLLECTION_TIMELINES,
    TIMELINE_ENTRY: COLLECTION_TIMELINE_ENTRIES,
}


def _safe_uuid(uuid: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)


def collection_path(uuid: str, collection: str) -> str:
    """Return a SOIL collection path for story-timeline protocol records."""
    return f"user-{_safe_uuid(uuid)}/story-timeline/{collection}/"


def collection_for_type(record_type: str) -> Optional[str]:
    """Map a protocol record type to its SOIL collection suffix."""
    return COLLECTIONS.get(record_type)


def _node_title(node: dict) -> str:
    fields = node.get("fields", {})
    return (
        fields.get("title")
        or fields.get("name")
        or str(fields.get("summary", ""))[:80]
        or node.get("type", "untitled")
    )


def _validate_fields(required: tuple[str, ...], fields: dict, label: str) -> None:
    missing = [k for k in required if not str(fields.get(k, "")).strip()]
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")


def create_writing_project(
    title: str,
    *,
    summary: str = "",
    status: str = "planning",
) -> dict:
    """Create a writing project container."""
    fields = {
        "title": title.strip(),
        "summary": summary.strip(),
        "status": status.strip() or "planning",
    }
    _validate_fields(("title",), fields, "writing_project")
    node_id = db.add_node(type_=WRITING_PROJECT, fields=fields)
    return db.get_node(node_id)


def is_writing_project(node: Optional[dict]) -> bool:
    return node is not None and node.get("type") in WRITING_PROJECT_TYPES


def create_timeline(
    project_id: str,
    name: str,
    *,
    timeline_kind: str = "world",
    description: str = "",
) -> dict:
    """Create a named timeline under a writing project."""
    project = db.get_node(project_id)
    if not is_writing_project(project):
        raise ValueError(f"writing project not found: {project_id}")
    fields = {
        "name": name.strip(),
        "project_id": project_id,
        "timeline_kind": timeline_kind.strip() or "world",
        "description": description.strip(),
    }
    _validate_fields(("name", "project_id"), fields, "timeline")
    node_id = db.add_node(type_=TIMELINE, fields=fields)
    return db.get_node(node_id)


def create_commonplace_item(
    title: str,
    *,
    content: str = "",
    source_kind: str = "note",
    tags: str = "",
) -> dict:
    """Create an explicit commonplace capture record."""
    fields = {
        "title": title.strip(),
        "content": content.strip(),
        "source_kind": source_kind.strip() or "note",
        "tags": tags.strip(),
    }
    _validate_fields(("title",), fields, "commonplace_item")
    node_id = db.add_node(type_=COMMONPLACE_ITEM, fields=fields)
    return db.get_node(node_id)


def create_timeline_entry(
    timeline_id: str,
    title: str,
    *,
    summary: str = "",
    order_index: int = 0,
    world_date: str = "",
    entry_kind: str = "scene",
) -> dict:
    """Create a timeline entry on a named timeline."""
    timeline = db.get_node(timeline_id)
    if not timeline or timeline["type"] != TIMELINE:
        raise ValueError(f"timeline not found: {timeline_id}")
    fields = {
        "title": title.strip(),
        "timeline_id": timeline_id,
        "summary": summary.strip(),
        "order_index": int(order_index),
        "world_date": world_date.strip(),
        "entry_kind": entry_kind.strip() or "scene",
    }
    _validate_fields(("title", "timeline_id"), fields, "timeline_entry")
    node_id = db.add_node(type_=TIMELINE_ENTRY, fields=fields)
    return db.get_node(node_id)


def get_timeline(timeline_id: str) -> Optional[dict]:
    node = db.get_node(timeline_id)
    if node and node["type"] == TIMELINE:
        return node
    return None


def get_writing_project(project_id: str) -> Optional[dict]:
    node = db.get_node(project_id)
    if is_writing_project(node):
        return node
    return None


def find_timeline_by_name(project_id: str, name: str) -> Optional[dict]:
    target = name.strip().lower()
    for node in db.get_nodes(type_=TIMELINE):
        if node["fields"].get("project_id") != project_id:
            continue
        if node["fields"].get("name", "").strip().lower() == target:
            return node
    return None


def list_writing_projects() -> list[dict]:
    return db.get_nodes(type_=WRITING_PROJECT)


def writing_setup_status() -> dict[str, bool]:
    """Whether promotion/suggestion flows need project or timeline setup."""
    projects = list_writing_projects()
    timelines = list_timelines()
    return {
        "ready": bool(projects and timelines),
        "needs_project": not projects,
        "needs_timeline": bool(projects) and not timelines,
    }


def list_timelines(project_id: Optional[str] = None) -> list[dict]:
    timelines = db.get_nodes(type_=TIMELINE)
    if project_id is None:
        return timelines
    return [t for t in timelines if t["fields"].get("project_id") == project_id]


def list_timeline_entries(timeline_id: str) -> list[dict]:
    entries = [
        n for n in db.get_nodes(type_=TIMELINE_ENTRY)
        if n["fields"].get("timeline_id") == timeline_id
    ]
    return sorted(entries, key=lambda n: (
        n["fields"].get("order_index", 0),
        n.get("created", ""),
    ))


def _ensure_promotable_source(source: dict) -> None:
    if source["type"] not in PROMOTABLE_SOURCE_TYPES:
        raise ValueError(
            f"source type {source['type']!r} is not promotable; "
            f"allowed: {sorted(PROMOTABLE_SOURCE_TYPES)}"
        )


def _link(
    from_id: str,
    to_id: str,
    relation: str,
    *,
    context: str = "",
    uuid: Optional[str] = None,
) -> Optional[str]:
    if relation not in STANDARD_RELATIONS:
        raise ValueError(f"unknown relation {relation!r}; use one of {sorted(STANDARD_RELATIONS)}")
    return willow_edges.add_edge(from_id, to_id, relation, context=context, uuid=uuid)


def wire_timeline_to_project(
    timeline_id: str,
    project_id: str,
    *,
    uuid: Optional[str] = None,
) -> Optional[str]:
    """Link timeline to its owning project."""
    timeline = get_timeline(timeline_id)
    project = get_writing_project(project_id)
    if not timeline or not project:
        raise ValueError("timeline or project not found")
    return _link(timeline_id, project_id, REL_BELONGS_TO_PROJECT, uuid=uuid)


def promote_to_timeline(
    source_id: str,
    timeline_id: str,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    order_index: Optional[int] = None,
    world_date: Optional[str] = None,
    entry_kind: str = "scene",
    uuid: Optional[str] = None,
    mirror: bool = True,
) -> dict[str, Any]:
    """
    Promote an existing note/book/commonplace record into a timeline entry.

    Writes:
      - timeline_entry node (local SQLite)
      - derived_from edge (entry -> source)
      - appears_on_timeline edge (entry -> timeline)
      - optional SOIL mirrors when uuid is set and mirror=True
    """
    source = db.get_node(source_id)
    if not source:
        raise ValueError(f"source record not found: {source_id}")
    _ensure_promotable_source(source)

    timeline = get_timeline(timeline_id)
    if not timeline:
        raise ValueError(f"timeline not found: {timeline_id}")

    entry_title = (title or _node_title(source)).strip()
    entry_summary = summary if summary is not None else str(source["fields"].get("content") or source["fields"].get("summary") or "")
    if order_index is None:
        existing = list_timeline_entries(timeline_id)
        order_index = len(existing)
    entry_world_date = world_date if world_date is not None else str(source["fields"].get("world_date") or "")

    entry = create_timeline_entry(
        timeline_id,
        entry_title,
        summary=entry_summary,
        order_index=order_index,
        world_date=entry_world_date,
        entry_kind=entry_kind,
    )

    provenance = {
        "source_id": source_id,
        "source_type": source["type"],
        "source_title": _node_title(source),
        "timeline_id": timeline_id,
        "timeline_name": timeline["fields"].get("name", ""),
    }

    derived_edge = _link(
        entry["id"],
        source_id,
        REL_DERIVED_FROM,
        context=f"promoted from {source['type']}",
        uuid=uuid,
    )
    timeline_edge = _link(
        entry["id"],
        timeline_id,
        REL_APPEARS_ON_TIMELINE,
        context=timeline["fields"].get("name", ""),
        uuid=uuid,
    )

    soil_mirrors: dict[str, bool] = {}
    if mirror and uuid:
        import soil_protocol
        soil_mirrors["entry"] = soil_protocol.mirror_protocol_record(entry, uuid=uuid)
        soil_mirrors["provenance"] = soil_protocol.mirror_provenance(
            entry_id=entry["id"],
            provenance=provenance,
            uuid=uuid,
        )

    return {
        "entry": entry,
        "provenance": provenance,
        "edges": {
            REL_DERIVED_FROM: derived_edge,
            REL_APPEARS_ON_TIMELINE: timeline_edge,
        },
        "soil_mirrors": soil_mirrors,
    }


def sources_for_entry(entry_id: str, *, uuid: Optional[str] = None) -> list[dict]:
    """Source nodes linked to a timeline entry via derived_from."""
    sources: list[dict] = []
    for edge in willow_edges.edges_for(entry_id, uuid=uuid):
        if edge.get("from_id") == entry_id and edge.get("relation") == REL_DERIVED_FROM:
            source = db.get_node(edge["to_id"])
            if source:
                sources.append(source)
    return sources


def entries_from_source(source_id: str, *, uuid: Optional[str] = None) -> list[dict]:
    """Timeline entries promoted from a library/commonplace source."""
    entries: list[dict] = []
    for edge in willow_edges.edges_for(source_id, uuid=uuid):
        if edge.get("to_id") == source_id and edge.get("relation") == REL_DERIVED_FROM:
            entry = db.get_node(edge["from_id"])
            if entry and entry.get("type") == TIMELINE_ENTRY:
                entries.append(entry)
    return sorted(entries, key=lambda n: (
        n["fields"].get("order_index", 0),
        n.get("created", ""),
    ))


def timeline_label(timeline_id: str) -> str:
    timeline = get_timeline(timeline_id)
    if not timeline:
        return timeline_id[:12]
    project = get_writing_project(timeline["fields"].get("project_id", ""))
    project_name = _node_title(project) if project else "?"
    return f"{project_name} / {timeline['fields'].get('name', '?')}"


def protocol_record_payload(node: dict) -> dict:
    """Serialize a protocol node for SOIL storage."""
    return {
        "id": node["id"],
        "type": node["type"],
        "app_id": APP_ID,
        "fields": node.get("fields", {}),
        "created": node.get("created"),
        "updated": node.get("updated"),
    }
