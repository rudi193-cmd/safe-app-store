"""Verified-source search — flat, ranked result list for the Jeles search TUI."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from askjeles.classify import QueryClass, classify
from askjeles.spell import correct_query
from askjeles.willow_path import bootstrap

bootstrap()

log = logging.getLogger("jeles.search")

try:
    from core.jeles_sources import (
        question_to_intent,
        question_to_query,
        route_sources,
        route_sources_semantic,
        search as jeles_search,
    )

    _DIRECT_AVAILABLE = True
except ImportError:
    _DIRECT_AVAILABLE = False

try:
    from askjeles import mcp_client

    _MCP_IMPORT = True
except ImportError:
    _MCP_IMPORT = False

try:
    from askjeles import web_search as general_web

    _WEB_AVAILABLE = True
except ImportError:
    _WEB_AVAILABLE = False

try:
    from askjeles.kb_search import search_local_kb

    _KB_AVAILABLE = True
except ImportError:
    _KB_AVAILABLE = False

_QUESTION_START = re.compile(
    r"^(what|who|when|where|why|how|which|tell me about|tell about|"
    r"can you|could you|explain|describe)\b",
    re.IGNORECASE,
)
_STOP_TOKENS = frozenset(
    {
        "about", "tell", "give", "show", "find", "look", "search", "author", "writer",
        "book", "novel", "fiction", "science", "information", "details", "overview",
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "was",
        "were", "are", "is", "been", "being",
    }
)
_LIT_HINTS = re.compile(
    r"\b(author|writer|novel|book|poem|poetry|literature|fiction|publish|"
    r"hitchhiker|adams|shakespeare|gutenberg)\b",
    re.IGNORECASE,
)
_ACADEMIC_SOURCES = frozenset({"arxiv", "openalex", "crossref", "semantic_scholar", "pubmed"})
_LIT_SOURCES = frozenset({"openlibrary", "gutenberg", "isfdb", "internet_archive", "loc", "chronicling_america"})
_WEB_SOURCES = frozenset({"web", "maps_osm", "maps_google", "web_ddg"})
_LOCAL_SOURCES = frozenset({"local_kb"})
_MAX_SOURCES = 8
_MAX_HITS = 25
_MIN_SCORE = 0.12
_PROPER_NAME = re.compile(
    r"\b[A-Z][a-z]+(?:['\u2019][A-Z][a-z]+)?(?:\s+(?:[A-Z][a-z]+|von|de|Jon|Mc[A-Z][a-z]+))+"
)
_SPACE_HINTS = re.compile(
    r"\b(apollo|nasa|moon landing|lunar|spacecraft|astronaut|orbit|mars mission|"
    r"space station|hubble|artemis)\b",
    re.IGNORECASE,
)


def available() -> bool:
    return _KB_AVAILABLE or _WEB_AVAILABLE or _DIRECT_AVAILABLE or (_MCP_IMPORT and mcp_client._use_mcp())


def _hostname(url: str) -> str:
    try:
        return urlparse(url).netloc or "source"
    except Exception:
        return "source"


def _tokens(*parts: str) -> list[str]:
    words: list[str] = []
    for part in parts:
        for w in re.findall(r"[a-z0-9']{3,}", (part or "").lower()):
            if w not in _STOP_TOKENS:
                words.append(w)
    return list(dict.fromkeys(words))


def _use_llm_intent(question: str) -> bool:
    """Skip slow LLM rewrite for direct name/topic searches."""
    q = question.strip()
    if _QUESTION_START.match(q):
        return True
    if "?" in q:
        return True
    return len(q.split()) > 8


def _looks_like_person(question: str) -> bool:
    if _PROPER_NAME.search(question):
        return True
    if not _DIRECT_AVAILABLE:
        return False
    cleaned = question_to_query(question)
    words = cleaned.split()
    titled = sum(1 for w in words if w[:1].isupper() and len(w) > 1)
    return titled >= 2 and len(words) <= 6


def _boost_sources(question: str, intent: str) -> list[str]:
    qfull = f"{question} {intent}"
    if _LIT_HINTS.search(qfull) or _looks_like_person(question):
        return [
            "openlibrary", "crossref", "wikidata", "isfdb", "internet_archive",
            "loc", "gutenberg", "openalex",
        ]
    if _SPACE_HINTS.search(qfull):
        return ["nasa", "loc", "openalex", "crossref", "arxiv", "wikidata"]
    return []


def _merge_sources(question: str, intent: str) -> list[str]:
    if not _DIRECT_AVAILABLE:
        return []
    seen: set[str] = set()
    merged: list[str] = []
    for sid in _boost_sources(question, intent) + route_sources(question) + route_sources_semantic(intent):
        if sid not in seen:
            seen.add(sid)
            merged.append(sid)
        if len(merged) >= _MAX_SOURCES:
            break
    return merged


def _rank_hit(
    hit: dict[str, Any],
    tokens: list[str],
    lit_query: bool,
    space_query: bool,
    query_class: QueryClass,
) -> float:
    title = (hit.get("title") or "").lower()
    snippet = (hit.get("snippet") or "").lower()
    url = (hit.get("url") or "").lower()
    blob = f"{title} {snippet}"
    source_id = (hit.get("source_id") or "").lower()
    matched = 0

    if not tokens:
        score = 0.5
    else:
        matched = sum(1 for t in tokens if t in blob)
        score = matched / len(tokens)

        if tokens and all(t in title for t in tokens[:3]):
            score += 0.45
        elif matched >= 2:
            score += 0.15

    if lit_query:
        if source_id in _LIT_SOURCES:
            score += 0.12
        if source_id in _ACADEMIC_SOURCES and matched < len(tokens):
            score -= 0.35

    if space_query:
        if source_id == "nasa" and (not tokens or any(t in blob for t in tokens)):
            score += 0.2
        if "images-assets.nasa.gov" in url and "apollo" in blob:
            score += 0.15

    if query_class == QueryClass.NAVIGATIONAL:
        if source_id in _WEB_SOURCES or source_id == "web":
            score += 0.55
        if source_id in _ACADEMIC_SOURCES:
            score -= 0.3
    elif query_class == QueryClass.GENERAL:
        if source_id in _WEB_SOURCES or source_id == "web":
            score += 0.2

    if source_id in _LOCAL_SOURCES:
        score += 0.65

    if "images-assets.nasa.gov" in url and tokens and not any(t in blob for t in tokens):
        score -= 0.4
    if "/image/" in url and tokens and not any(t in blob for t in tokens):
        score -= 0.25

    return max(0.0, min(1.5, score))


def flatten_results(raw: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for source_id, rows in raw.get("results", {}).items():
        for row in rows:
            url = (row.get("url") or "").strip()
            title = (row.get("title") or "Untitled").strip()
            snippet_raw = row.get("snippet") or ""
            if isinstance(snippet_raw, list):
                snippet = " ".join(str(s) for s in snippet_raw).strip()
            else:
                snippet = str(snippet_raw).strip()
            hits.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": row.get("institution") or row.get("source") or source_id,
                    "date": row.get("date") or "",
                    "source_id": source_id,
                    "hostname": _hostname(url),
                }
            )
    return hits


def _search_queries(question: str, intent: str) -> list[str]:
    if not _DIRECT_AVAILABLE:
        return [question.strip()]
    queries: list[str] = []
    cleaned = question_to_query(question) or question.strip()
    intent_q = question_to_query(intent) or intent.strip()
    for q in (cleaned, intent_q):
        q = re.sub(r"\s+", " ", q).strip()
        if q and q.lower() not in {x.lower() for x in queries}:
            queries.append(q)
    return queries or [question.strip()]


def _institutional_via_mcp(queries: list[str], sources: list[str], per_source: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if not _MCP_IMPORT or not mcp_client.ensure_started(timeout=30):
        return hits
    for query in queries[:2]:
        try:
            raw = mcp_client.jeles_web_search(query, sources=sources or None, limit=per_source)
            hits.extend(flatten_results(raw))
        except Exception as exc:
            log.warning("MCP mem_jeles_web_search failed for %r: %s", query, exc)
    return hits


def _institutional_direct(queries: list[str], sources: list[str], per_source: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if not _DIRECT_AVAILABLE:
        return hits
    for query in queries:
        try:
            raw = jeles_search(query, sources, per_source)
            hits.extend(flatten_results(raw))
        except Exception as exc:
            log.warning("direct jeles_search failed for %r: %s", query, exc)
    return hits


def _general_web_hits(question: str, query_class: QueryClass) -> list[dict[str, Any]]:
    if not _WEB_AVAILABLE:
        return []
    include_handoffs = query_class == QueryClass.NAVIGATIONAL
    if query_class == QueryClass.NAVIGATIONAL:
        max_results = 12
    elif query_class == QueryClass.GENERAL:
        max_results = 20
    else:
        max_results = 8
    try:
        return general_web.search_web(
            question,
            max_results=max_results,
            trusted_only=False,
            include_handoffs=include_handoffs,
        )
    except Exception as exc:
        log.warning("general web search failed: %s", exc)
        return []


def _local_kb_hits(question: str) -> list[dict[str, Any]]:
    if not _KB_AVAILABLE:
        return []
    try:
        return search_local_kb(question, limit=8)
    except Exception as exc:
        log.warning("local KB search failed: %s", exc)
        return []


def search_stacks(question: str, limit_per_source: int = 4) -> dict[str, Any]:
    """
    Search institutional stacks (via MCP when available) plus general web for Jeeves-style queries.
    """
    question = question.strip()
    query_class = classify(question)

    if not available():
        return {
            "hits": [],
            "sources_used": [],
            "query": question,
            "intent": "",
            "original_question": question,
            "corrected_question": "",
            "spell_confidence": 0.0,
            "query_class": query_class.value,
            "backend": "offline",
            "error": "search unavailable — check network or set WILLOW_ROOT",
        }

    corrected, original_question, spell_confidence = correct_query(question)
    search_question = corrected if spell_confidence >= 0.7 else question

    intent = search_question
    sources: list[str] = []
    queries = [search_question]

    if _DIRECT_AVAILABLE:
        try:
            if _use_llm_intent(search_question):
                intent = question_to_intent(search_question)
            else:
                intent = question_to_query(search_question) or search_question
            sources = _merge_sources(search_question, intent)
            queries = _search_queries(search_question, intent)
            if corrected.lower() != question.lower() and question.lower() not in {q.lower() for q in queries}:
                queries.append(question_to_query(question) or question)
        except Exception as exc:
            log.exception("routing failed")
            return {
                "hits": [],
                "sources_used": [],
                "query": question,
                "intent": "",
                "query_class": query_class.value,
                "error": str(exc),
            }

    lit_query = bool(_LIT_HINTS.search(search_question) or _LIT_HINTS.search(intent))
    space_query = bool(_SPACE_HINTS.search(f"{search_question} {intent}"))
    tokens = _tokens(search_question, intent, question, *queries)
    merged: dict[str, dict[str, Any]] = {}

    per_source = max(2, min(limit_per_source, 5))
    needs_institutional = query_class == QueryClass.RESEARCH
    use_mcp = needs_institutional and _MCP_IMPORT and mcp_client.ensure_started(timeout=20)
    backend = "web"

    kb_hits = _local_kb_hits(search_question)
    if kb_hits:
        backend = "kb+web"
    institutional: list[dict[str, Any]] = []
    if needs_institutional:
        if use_mcp:
            institutional = _institutional_via_mcp(queries, sources, per_source)
            if institutional:
                backend = "web+mcp"
        if not institutional:
            institutional = _institutional_direct(queries, sources, per_source)
            if institutional:
                backend = "web+direct"

    web_hits: list[dict[str, Any]] = []
    if query_class in (QueryClass.NAVIGATIONAL, QueryClass.GENERAL):
        web_hits = _general_web_hits(search_question, query_class)
    elif query_class == QueryClass.RESEARCH and len(tokens) <= 4:
        # Short topic searches still benefit from a few web hits (Jeeves knew everything)
        web_hits = _general_web_hits(search_question, QueryClass.GENERAL)[:4]

    # General and navigational searches are open-web first. Research searches keep
    # Special Collections as a primary drawer. Local KB always comes first.
    hit_stream = (
        kb_hits + web_hits + institutional
        if query_class != QueryClass.RESEARCH
        else kb_hits + institutional + web_hits
    )
    for hit in hit_stream:
        url = hit.get("url") or f"{hit.get('source_id')}:{hit.get('title')}"
        score = _rank_hit(hit, tokens, lit_query, space_query, query_class)
        prev = merged.get(url)
        if prev is None or score > prev["_score"]:
            hit["_score"] = score
            merged[url] = hit

    ranked = sorted(merged.values(), key=lambda h: h["_score"], reverse=True)
    strong = [h for h in ranked if h["_score"] >= _MIN_SCORE]
    hits = (strong or ranked)
    if query_class == QueryClass.GENERAL:
        kb_ranked = [h for h in hits if (h.get("source_id") or "").lower() in _LOCAL_SOURCES]
        web_ranked = [h for h in hits if (h.get("source_id") or "").lower() in _WEB_SOURCES or h.get("source_id") == "web"]
        other_ranked = [h for h in hits if h not in kb_ranked and h not in web_ranked]
        hits = kb_ranked + web_ranked + other_ranked
    hits = hits[:_MAX_HITS]

    for idx, hit in enumerate(hits, start=1):
        hit["n"] = idx
        hit.pop("_score", None)

    sources_used = [] if query_class in (QueryClass.GENERAL, QueryClass.NAVIGATIONAL) else list(sources)
    if web_hits:
        sources_used.insert(0, "open_web")
    if kb_hits:
        sources_used.insert(0, "local_kb")
    if query_class == QueryClass.NAVIGATIONAL:
        prefix = ["open_web", "maps"]
        if kb_hits:
            prefix.insert(0, "local_kb")
        sources_used = prefix + [s for s in sources_used if s not in ("local_kb", "open_web", "maps")]

    deduped_sources: list[str] = []
    for source in sources_used:
        if source and source not in deduped_sources:
            deduped_sources.append(source)

    return {
        "hits": hits,
        "sources_used": deduped_sources[:8],
        "query": queries[0],
        "intent": intent,
        "total": len(hits),
        "original_question": original_question,
        "corrected_question": corrected if corrected.lower() != original_question.lower() else "",
        "spell_confidence": spell_confidence,
        "query_class": query_class.value,
        "backend": backend,
        "error": "",
    }


def synthesize_answer(question: str) -> dict[str, Any]:
    """Optional Jeles Q&A from the same drawer as search."""
    query_class = classify(question)
    if query_class == QueryClass.RESEARCH and _MCP_IMPORT and mcp_client.ensure_started(timeout=15):
        try:
            payload = mcp_client.jeles_ask(question)
            return {
                "answer": payload.get("answer") or "",
                "citations": payload.get("citations") or [],
                "sources_used": payload.get("sources_used") or [],
                "backend": "mcp",
            }
        except Exception as exc:
            log.warning("MCP mem_jeles_ask failed: %s", exc)

    stacks = search_stacks(question, limit_per_source=3)
    hits = stacks.get("hits") or []
    if not hits:
        return {"answer": "Nothing in the stacks matched that query.", "citations": [], "backend": "local"}

    try:
        from core.llm_edge import respond as llm_respond
    except ImportError:
        return {
            "answer": "(LLM unavailable — pick a result and press Enter to open it.)",
            "citations": hits,
            "backend": "local",
        }

    if query_class == QueryClass.RESEARCH:
        system = (
            "You are Jeles, a trusted librarian. Answer using ONLY the numbered source "
            "excerpts below. Cite each fact with [N]. For lists, enumerate ALL items found. "
            "2-6 sentences or a bulleted list. "
            "NEVER use outside knowledge — if excerpts lack the answer, say exactly: "
            "'The trusted sources do not contain this answer.'"
        )
    else:
        system = (
            "You are Jeles, an Ask Jeeves-style research butler. Answer using ONLY the "
            "numbered search result excerpts below. Cite useful claims with [N]. "
            "For navigational queries, point the user at the best map or web result. "
            "Keep it concise, practical, and honest about what the snippets do not show."
        )
    try:
        answer = llm_respond(
            system,
            [],
            f"Question: {question}\n\nSources:\n{snippet_block(hits)}",
        )
    except Exception as exc:
        answer = f"(synthesis unavailable: {exc})"
    return {"answer": answer, "citations": hits, "backend": "local"}


def snippet_block(hits: list[dict[str, Any]], budget: int = 1500) -> str:
    lines: list[str] = []
    remaining = budget
    for hit in hits:
        line = f"[{hit['n']}] {hit['title']}"
        if hit.get("snippet"):
            line += f": {hit['snippet']}"
        line = line[:400]
        lines.append(line)
        remaining -= len(line)
        if remaining <= 0:
            break
    return "\n\n".join(lines)
