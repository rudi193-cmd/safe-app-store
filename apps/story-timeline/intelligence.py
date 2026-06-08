"""Intelligence orchestration — Jeles research, KB context, local SLM suggestions."""

from __future__ import annotations

from typing import Any, Optional
import re

import mcp_client
import story_protocol as proto
import suggestion_store as store
import timeline_db as db

SUGGESTION_KIND = "promotion"
READING_RECOMMENDATION_KIND = "reading_recommendation"


def _node_title(node: dict) -> str:
    f = node.get("fields", {})
    return (
        f.get("title") or f.get("name") or
        str(f.get("summary", ""))[:80] or
        node.get("type", "untitled")
    )


def _node_text(node: dict) -> str:
    f = node.get("fields", {})
    parts = [_node_title(node)]
    if node.get("type") == "project":
        for key in ("summary", "status", "tags", "notes", "title"):
            val = str(f.get(key, "")).strip()
            if val:
                parts.append(f"{key}: {val}")
        return "\n".join(parts)
    for key in ("content", "summary", "review", "tags", "author"):
        val = str(f.get(key, "")).strip()
        if val:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


def _recommendation_question(source: dict) -> str:
    title = _node_title(source)
    if source.get("type") == "project":
        return (
            "Recommend books useful for this library project. Include background, "
            "adjacent, contrasting, and foundational works. Do not recommend the "
            "project itself or books already present in the library. Return title, author, and why.\n\n"
            f"Project:\n{_node_text(source)}"
        )
    return (
        "Suggest similar books or useful adjacent works for a reader who is "
        f"interested in this library item: {title}. Do not recommend {title} itself "
        "or books already present in the library. Return title, author, and why."
    )


def _recommendation_slm_context(source: dict, *, research_summary: str = "") -> str:
    if source.get("type") == "project":
        intro = (
            "Recommend books useful for this library project to add to a to-read shelf. "
            "Include background, adjacent, contrasting, and foundational works. "
            "Do not recommend the project itself or books already present in the library. "
            "Return a recommendations list with title, author, reason, tags."
        )
    else:
        intro = (
            "Recommend similar or adjacent books/works to add to a to-read "
            "library list. Do not recommend the source work itself or books already "
            "present in the library. Return a recommendations list with title, author, reason."
        )
    parts = [intro, "", f"Source ({source.get('type', '?')}):\n{_node_text(source)}"]
    if research_summary:
        parts.extend(["", f"Jeles research:\n{research_summary}"])
    return "\n".join(parts)


def _timeline_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for project in proto.list_writing_projects():
        for timeline in proto.list_timelines(project["id"]):
            label = f"{_node_title(project)} / {timeline['fields'].get('name', '?')}"
            options.append({
                "timeline_id": timeline["id"],
                "project_id": project["id"],
                "label": label,
            })
    return options


def gather_context(source: dict) -> dict[str, Any]:
    return {
        "source": source,
        "source_text": _node_text(source),
        "timelines": _timeline_options(),
    }


def _extract_jeles_sources(jeles_result: dict) -> list[dict]:
    sources: list[dict] = []
    for key in ("sources", "citations", "results"):
        val = jeles_result.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    sources.append(item)
    results = jeles_result.get("results")
    if isinstance(results, dict):
        for group in results.values():
            if isinstance(group, list):
                for item in group:
                    if isinstance(item, dict):
                        sources.append(item)
    return sources[:10]


def _mcp_tool_error(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    err = result.get("error")
    if err:
        return str(err)
    return None


def research_view_for_packet(packet: dict) -> dict[str, Any]:
    """Build a research result view from a stored research_packet node."""
    payload = store.research_payload(packet)
    raw = packet.get("fields", {}).get("raw") or {}
    err = _mcp_tool_error(raw)
    if err:
        return {"ok": False, "error": f"Jeles: {err}", "research": payload}
    if not payload.get("summary") and not payload.get("sources"):
        return {
            "ok": False,
            "error": "Research returned no summary or sources.",
            "research": payload,
        }
    return {"ok": True, "research": payload}


def run_jeles_research(source: dict, *, question: str | None = None) -> dict[str, Any]:
    title = _node_title(source)
    q = question or f"What trusted background exists for this writing note: {title}?"
    context = gather_context(source)
    if not mcp_client.available():
        return {
            "ok": False,
            "error": mcp_client.last_error() or "MCP unavailable",
            "context": context,
        }
    try:
        result = mcp_client.jeles_ask(q)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "context": context}

    err = _mcp_tool_error(result)
    if err:
        return {"ok": False, "error": f"Jeles: {err}", "context": context}

    answer = str(result.get("answer") or result.get("summary") or "").strip()
    sources = _extract_jeles_sources(result)
    packet = store.create_research_packet(
        source["id"],
        query=q,
        summary=answer,
        sources=sources,
        provider="jeles",
        raw=result,
    )
    return {
        "ok": True,
        "research": store.research_payload(packet),
        "context": context,
    }


def _kb_context(source: dict) -> dict[str, Any]:
    if not mcp_client.available():
        return {"ok": False, "hits": []}
    query = _node_title(source)
    try:
        result = mcp_client.kb_search(query, limit=5)
    except Exception:
        return {"ok": False, "hits": []}
    hits = result.get("knowledge") or []
    if not isinstance(hits, list):
        hits = []
    return {"ok": True, "hits": hits[:5]}


def _heuristic_suggestion(source: dict, timelines: list[dict]) -> dict[str, Any]:
    title = _node_title(source)
    f = source.get("fields", {})
    summary = str(f.get("content") or f.get("summary") or f.get("review") or "")[:500]
    timeline_id = timelines[0]["timeline_id"] if timelines else ""
    timeline_label = timelines[0]["label"] if timelines else ""
    return {
        "timeline_id": timeline_id,
        "timeline_label": timeline_label,
        "title": title,
        "summary": summary,
        "entry_kind": "scene",
        "relation_reason": "derived_from",
        "confidence": 0.3,
        "model": "heuristic",
    }


def _slm_suggestion(
    source: dict,
    timelines: list[dict],
    *,
    research_summary: str = "",
    kb_hits: list[dict] | None = None,
) -> dict[str, Any]:
    if not timelines:
        return _heuristic_suggestion(source, timelines)

    labels = [t["label"] for t in timelines]
    context_parts = [f"Source type: {source['type']}", f"Source:\n{_node_text(source)}"]
    if research_summary:
        context_parts.append(f"Jeles research:\n{research_summary}")
    if kb_hits:
        kb_lines = []
        for hit in kb_hits[:3]:
            kb_lines.append(str(hit.get("title") or hit.get("summary") or hit.get("id")))
        if kb_lines:
            context_parts.append("KB memory:\n" + "\n".join(kb_lines))

    base = _heuristic_suggestion(source, timelines)
    if not mcp_client.available():
        return base

    try:
        summary_result = mcp_client.infer_7b(
            "summarize",
            content=_node_text(source),
            context="\n\n".join(context_parts),
        )
        classify_result = mcp_client.infer_7b(
            "classify",
            content=_node_text(source),
            context="\n\n".join(context_parts),
            categories=labels,
        )
    except Exception:
        return base

    title = base["title"]
    summary = str(summary_result.get("one_line") or summary_result.get("bullets") or base["summary"])
    if isinstance(summary_result.get("bullets"), list):
        summary = "; ".join(str(x) for x in summary_result["bullets"][:3]) or summary

    chosen = str(classify_result.get("category") or "")
    timeline_id = base["timeline_id"]
    timeline_label = base["timeline_label"]
    for opt in timelines:
        if opt["label"] == chosen:
            timeline_id = opt["timeline_id"]
            timeline_label = opt["label"]
            break

    confidence = classify_result.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "timeline_id": timeline_id,
        "timeline_label": timeline_label,
        "title": title,
        "summary": summary[:500],
        "entry_kind": "scene",
        "relation_reason": "derived_from",
        "confidence": confidence,
        "model": "infer_7b",
        "classify_reason": classify_result.get("reason", ""),
    }


def _extract_recommendations(result: dict) -> list[dict[str, Any]]:
    raw = (
        result.get("recommendations")
        or result.get("books")
        or result.get("suggestions")
        or []
    )
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for item in raw[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "author": str(item.get("author") or "").strip(),
            "reason": str(item.get("reason") or item.get("summary") or "").strip(),
            "tags": str(item.get("tags") or item.get("genre") or "").strip(),
        })
    return out


def _work_key(title: str, author: str = "") -> tuple[str, str]:
    def clean(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    return clean(title), clean(author)


def _source_work_keys(source: dict) -> set[tuple[str, str]]:
    if source.get("type") != "book":
        return set()
    f = source.get("fields", {})
    title = str(f.get("title") or f.get("name") or "").strip()
    author = str(f.get("author") or "").strip()
    keys = {_work_key(title, author)}
    # Treat title-only matches as duplicates too; imported data often has sparse authors.
    keys.add(_work_key(title, ""))
    return {k for k in keys if k[0]}


def _existing_book_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for book in db.get_nodes(type_="book"):
        f = book.get("fields", {})
        title = str(f.get("title") or f.get("name") or "").strip()
        author = str(f.get("author") or "").strip()
        if title:
            keys.add(_work_key(title, author))
            keys.add(_work_key(title, ""))
    return keys


def _tag_set(text: str) -> set[str]:
    return {t.strip().lower() for t in text.split(",") if t.strip()}


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_meta_recommendation_title(title: str) -> bool:
    t = title.lower().strip()
    return t.startswith("more like ") or t.startswith("background reading for ")


# Offline staples when MCP/SLM unavailable — concrete titles, not meta phrases.
READING_STAPLES: dict[str, list[dict[str, str]]] = {
    "philip k dick": [
        {
            "title": "The Left Hand of Darkness",
            "author": "Ursula K. Le Guin",
            "reason": "Adjacent classic SF exploring identity, politics, and other worlds.",
            "tags": "science fiction",
        },
        {
            "title": "Flowers for Algernon",
            "author": "Daniel Keyes",
            "reason": "Human-scale speculative fiction about consciousness and empathy.",
            "tags": "science fiction",
        },
        {
            "title": "Slaughterhouse-Five",
            "author": "Kurt Vonnegut",
            "reason": "Reality-bending war fiction with satire and metaphysical drift.",
            "tags": "science fiction",
        },
    ],
    "ursula k le guin": [
        {
            "title": "The Dispossessed",
            "author": "Ursula K. Le Guin",
            "reason": "Core Le Guin novel on anarchism, science, and social structure.",
            "tags": "science fiction",
        },
        {
            "title": "The Man in the High Castle",
            "author": "Philip K. Dick",
            "reason": "Counterfactual SF with layered reality and political dread.",
            "tags": "science fiction",
        },
    ],
    "science fiction": [
        {
            "title": "The Left Hand of Darkness",
            "author": "Ursula K. Le Guin",
            "reason": "Foundational social and anthropological science fiction.",
            "tags": "science fiction",
        },
        {
            "title": "Kindred",
            "author": "Octavia E. Butler",
            "reason": "Time-travel SF grounded in history, power, and survival.",
            "tags": "science fiction",
        },
    ],
    "ecology": [
        {
            "title": "The Ecology of Freedom",
            "author": "Murray Bookchin",
            "reason": "Foundational political ecology for worldbuilding projects.",
            "tags": "ecology, politics",
        },
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "reason": "Desert-planet ecology tied to politics and myth.",
            "tags": "science fiction, ecology",
        },
    ],
    "default": [
        {
            "title": "The Left Hand of Darkness",
            "author": "Ursula K. Le Guin",
            "reason": "A widely useful adjacent classic when no live model is available.",
            "tags": "science fiction",
        },
        {
            "title": "Kindred",
            "author": "Octavia E. Butler",
            "reason": "A strong counterpart work for research and reading lists.",
            "tags": "fiction",
        },
    ],
}


def _staple_keys_for_source(source: dict) -> list[str]:
    f = source.get("fields", {})
    keys: list[str] = []
    if source.get("type") == "author":
        keys.append(_normalize_key(_node_title(source)))
    elif source.get("type") == "project":
        keys.append(_normalize_key(_node_title(source)))
        for word in _normalize_key(str(f.get("summary") or "")).split():
            if len(word) > 4:
                keys.append(word)
    author = str(f.get("author") or "").strip()
    if author:
        keys.append(_normalize_key(author))
    keys.extend(_normalize_key(tag) for tag in _tag_set(str(f.get("tags") or "")))
    keys.append("default")
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _staple_recommendations(source: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for key in _staple_keys_for_source(source):
        for rec in READING_STAPLES.get(key, []):
            title = rec["title"]
            author = rec.get("author", "")
            if _is_meta_recommendation_title(title):
                continue
            work = _work_key(title, author)
            if work in seen:
                continue
            seen.add(work)
            reason = rec.get("reason", "")
            if source.get("type") == "author":
                reason = f"{reason} Suggested for readers of {_node_title(source)}."
            elif source.get("type") == "project":
                reason = f"{reason} Useful for project: {_node_title(source)}."
            out.append({
                "title": title,
                "author": author,
                "reason": reason,
                "tags": rec.get("tags", ""),
            })
    return out


def _filter_new_recommendations(source: dict, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked = _existing_book_keys() | _source_work_keys(source)
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for rec in recs:
        title = str(rec.get("title") or "").strip()
        author = str(rec.get("author") or "").strip()
        if not title or _is_meta_recommendation_title(title):
            continue
        exact_key = _work_key(title, author)
        title_key = _work_key(title, "")
        if exact_key in blocked or title_key in blocked:
            continue
        if exact_key in seen or title_key in seen:
            continue
        seen.add(exact_key)
        seen.add(title_key)
        out.append(rec)
    return out


def _heuristic_recommendations(source: dict) -> list[dict[str, Any]]:
    return _staple_recommendations(source)


def suggest_reading_recommendations(
    source: dict,
    *,
    with_jeles: bool = True,
    with_kb: bool = True,
) -> dict[str, Any]:
    """Suggest similar works to add to the library to-read shelf."""
    if source["type"] not in proto.PROMOTABLE_SOURCE_TYPES:
        raise ValueError(f"source type {source['type']!r} is not a suggestion source")

    context = gather_context(source)
    research_payload: dict | None = None
    supporting: list[dict] = []
    research_summary = ""

    if with_jeles and mcp_client.available():
        question = _recommendation_question(source)
        research = run_jeles_research(source, question=question)
        if research.get("ok"):
            research_payload = research["research"]
            research_summary = research_payload.get("summary", "")
            supporting.extend(research_payload.get("sources") or [])

    kb = _kb_context(source) if with_kb else {"ok": False, "hits": []}
    if kb.get("hits"):
        supporting.extend(kb["hits"])

    recommendations = _heuristic_recommendations(source)
    model = "heuristic"
    if mcp_client.available():
        try:
            result = mcp_client.infer_7b(
                "recommend_books",
                content=_node_text(source),
                context=_recommendation_slm_context(
                    source, research_summary=research_summary
                ),
            )
            err = _mcp_tool_error(result)
            if err:
                pass
            else:
                parsed = _extract_recommendations(result)
                if parsed:
                    recommendations = parsed
                    model = "infer_7b"
        except Exception:
            pass

    created = []
    for rec in _filter_new_recommendations(source, recommendations)[:5]:
        suggestion = store.create_suggestion(
            source["id"],
            suggestion_kind=READING_RECOMMENDATION_KIND,
            proposed_fields={
                "title": rec["title"],
                "author": rec.get("author", ""),
                "shelf": "to-read",
                "reason": rec.get("reason", ""),
                "tags": rec.get("tags", ""),
            },
            supporting_sources=supporting,
            research_id=research_payload["id"] if research_payload else "",
            confidence=0.7 if model == "infer_7b" else 0.35,
            model=model,
        )
        created.append(suggestion)

    return {
        "suggestions": created,
        "suggestion": created[0] if created else None,
        "research": research_payload,
        "context": context,
        "offline": not mcp_client.available(),
    }


def suggest_promotion(
    source: dict,
    *,
    with_jeles: bool = True,
    with_kb: bool = True,
) -> dict[str, Any]:
    if source["type"] not in proto.PROMOTABLE_SOURCE_TYPES:
        raise ValueError(f"source type {source['type']!r} is not promotable")

    context = gather_context(source)
    timelines = context["timelines"]
    if not timelines:
        raise ValueError("create a writing project and timeline first")

    research_payload: dict | None = None
    research_summary = ""
    if with_jeles:
        research = run_jeles_research(source)
        if research.get("ok"):
            research_payload = research["research"]
            research_summary = research_payload.get("summary", "")

    kb = _kb_context(source) if with_kb else {"ok": False, "hits": []}
    proposed = _slm_suggestion(
        source,
        timelines,
        research_summary=research_summary,
        kb_hits=kb.get("hits") if kb.get("ok") else [],
    )

    supporting = []
    if research_payload and research_payload.get("sources"):
        supporting.extend(research_payload["sources"])
    if kb.get("hits"):
        supporting.extend(kb["hits"])

    suggestion = store.create_suggestion(
        source["id"],
        suggestion_kind=SUGGESTION_KIND,
        proposed_fields={
            "timeline_id": proposed["timeline_id"],
            "timeline_label": proposed.get("timeline_label", ""),
            "title": proposed["title"],
            "summary": proposed["summary"],
            "entry_kind": proposed.get("entry_kind", "scene"),
            "relation_reason": proposed.get("relation_reason", "derived_from"),
        },
        supporting_sources=supporting,
        research_id=research_payload["id"] if research_payload else "",
        confidence=float(proposed.get("confidence", 0.0)),
        model=str(proposed.get("model", "")),
    )

    return {
        "suggestion": suggestion,
        "research": research_payload,
        "proposed": proposed,
        "context": context,
        "offline": not mcp_client.available(),
    }


def accept_suggestion(
    suggestion_id: str,
    *,
    uuid: Optional[str] = None,
    edits: dict | None = None,
) -> dict[str, Any]:
    suggestion = store.get_suggestion(suggestion_id)
    if not suggestion:
        raise ValueError(f"suggestion not found: {suggestion_id}")

    fields = dict(suggestion.get("fields", {}))
    if fields.get("status") != store.STATUS_PENDING:
        raise ValueError("suggestion is not pending")

    kind = fields.get("suggestion_kind") or SUGGESTION_KIND
    proposed = dict(fields.get("proposed_fields") or {})
    if edits:
        proposed.update(edits)

    if kind == READING_RECOMMENDATION_KIND:
        title = str(proposed.get("title") or "").strip()
        if not title:
            raise ValueError("recommendation missing title")
        book_id = db.add_node(type_="book", fields={
            "title": title,
            "author": str(proposed.get("author") or "").strip(),
            "shelf": proposed.get("shelf") or "to-read",
            "rating": "0",
            "tags": str(proposed.get("tags") or "").strip(),
            "review": str(proposed.get("reason") or "").strip(),
        })
        store.update_suggestion_status(suggestion_id, store.STATUS_ACCEPTED)
        return {
            "book": db.get_node(book_id),
            "suggestion_id": suggestion_id,
        }

    source_id = fields.get("source_id")
    timeline_id = proposed.get("timeline_id")
    if not source_id or not timeline_id:
        raise ValueError("suggestion missing source_id or timeline_id")

    result = proto.promote_to_timeline(
        source_id,
        timeline_id,
        title=proposed.get("title"),
        summary=proposed.get("summary"),
        entry_kind=proposed.get("entry_kind", "scene"),
        uuid=uuid,
        mirror=bool(uuid),
    )

    research_id = fields.get("research_id")
    if research_id and uuid:
        _mirror_research_if_present(research_id, uuid)

    store.update_suggestion_status(suggestion_id, store.STATUS_ACCEPTED)
    return {
        "promotion": result,
        "suggestion_id": suggestion_id,
    }


def dismiss_suggestion(suggestion_id: str) -> bool:
    return store.update_suggestion_status(suggestion_id, store.STATUS_DISMISSED)


def bundle_for_suggestion(suggestion_id: str) -> dict[str, Any]:
    suggestion = store.get_suggestion(suggestion_id)
    if not suggestion:
        raise ValueError(f"suggestion not found: {suggestion_id}")
    source_id = suggestion["fields"].get("source_id")
    source = db.get_node(source_id) if source_id else None
    if not source:
        raise ValueError("suggestion source not found")

    research_payload: dict | None = None
    research_id = suggestion["fields"].get("research_id")
    if research_id:
        packet = store.get_research_packet(research_id)
        if packet:
            research_payload = store.research_payload(packet)

    return {
        "suggestion": suggestion,
        "research": research_payload,
        "context": gather_context(source),
    }


def _mirror_research_if_present(research_id: str, uuid: str) -> None:
    import soil_protocol

    node = store.get_research_packet(research_id)
    if not node:
        return
    try:
        import re
        from datetime import datetime
        safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
        collection = f"user-{safe_uuid}/story-timeline/atoms"
        record = {
            "id": f"research-{node['id']}",
            "type": store.RESEARCH_PACKET,
            "app_id": proto.APP_ID,
            "created_at": datetime.now().isoformat(),
            **store.research_payload(node),
        }
        client = soil_protocol._get_client()
        if client:
            client.put(collection, record, record_id=record["id"])
    except Exception:
        pass
