"""
Shared consultation prompt + LLM routing for UTETY Textual TUI and Ratatui campus.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import tui_llm

try:
    from personas import PERSONAS, UTETY_CONTEXT
except ImportError:
    PERSONAS = {}
    UTETY_CONTEXT = ""

GERALD_MAX_CHARS = 300
_CATALOG_PATH = Path(__file__).parent / "campus" / "catalog" / "catalog.json"


def _load_catalog() -> dict:
    if not _CATALOG_PATH.is_file():
        return {}
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def course_context(course_code: str | None) -> str:
    """Course teaching context from catalog (title + description)."""
    if not course_code:
        return ""
    for course in _load_catalog().get("courses", []):
        if course.get("code") == course_code:
            title = course.get("title", "")
            desc = course.get("desc", "")
            instructor = course.get("instructor", "")
            return (
                f"### Course context ({course_code}: {title})\n"
                f"Instructor: {instructor}\n{desc}\n"
            )
    return ""


def faculty_context(professor: str) -> str:
    """Compact faculty context for fast terminal consultations."""
    for faculty in _load_catalog().get("faculty", []):
        if faculty.get("name") == professor:
            parts = [
                f"You are Professor {professor} of UTETY.",
                f"Department: {faculty.get('dept', '')}.",
                f"Office: {faculty.get('location', '')}.",
                faculty.get("bio", ""),
                f"Signature course: {faculty.get('course', '')}.",
            ]
            return "\n".join(p for p in parts if p.strip())
    return f"You are Professor {professor} of UTETY."


def compact_utety_context() -> str:
    """Small campus context; full seed prompts are too slow for small local models."""
    catalog = _load_catalog()
    meta = catalog.get("meta", {})
    title = meta.get("title", "University of Technical Entropy, Thank You")
    motto = ", ".join(meta.get("mottos", [])[:2])
    return (
        f"{title} is a strange, sincere university-terminal artifact. "
        f"Motto: {motto}. Answer as the selected professor, warmly and directly. "
        "Keep responses concise unless the student asks for depth."
    )


def build_prompt(
    professor: str,
    history: list[dict],
    *,
    course_code: str | None = None,
    compact: bool = False,
    professor_memory: str = "",
    willow_context: str = "",
) -> str:
    """Build LLM prompt: persona + UTETY context + optional extras + history.

    Args:
        professor_memory: Pre-seeded stable background for this professor
            (e.g. from data/professors/<name>_context.md).
        willow_context: Per-query RAG atoms fetched from Willow knowledge graph.
            Injected after professor_memory, before history.
    """
    if compact:
        persona_prompt = faculty_context("Hanz" if professor == "Copenhagen" else professor)
        context = compact_utety_context()
    else:
        persona_key = "Hanz" if professor == "Copenhagen" else professor
        persona_prompt = PERSONAS.get(persona_key, PERSONAS.get("Willow", ""))
        context = UTETY_CONTEXT

    if professor == "Copenhagen":
        persona_prompt = (
            "You are Hanz Christain Anderthon, translating for Copenhagen (an orange who does not speak).\n"
            "Hanz translates what the orange seems to mean — sincerely, with Danish warmth.\n"
            "Begin responses with 'Hello, friend.' Refer to Copenhagen naturally. The orange is present.\n\n"
        ) + persona_prompt

    parts = [persona_prompt, "", context]
    ctx = course_context(course_code)
    if ctx:
        parts.extend(["", ctx])
    if professor_memory:
        parts.extend(["", f"### {professor}'s Memory:", professor_memory])
    if willow_context:
        parts.extend(["", willow_context])
    parts.extend(["", "### Conversation History:"])

    recent_limit = 4 if compact else 10
    recent = history[-recent_limit:] if len(history) > recent_limit else history
    for msg in recent:
        role_label = "User" if msg["role"] == "user" else professor
        content = str(msg["content"])
        if compact and len(content) > 800:
            content = content[:800].rstrip() + "..."
        parts.append(f"{role_label}: {content}")

    speaker = "Hanz" if professor == "Copenhagen" else professor
    parts.append(f"{speaker}:")
    return "\n".join(parts)


def format_response_plain(professor: str, content: str, category: str = "") -> str:
    """Plain-text faculty rendering for the Ratatui consultation chamber."""
    text = content.strip()
    if not text:
        return ""

    if professor == "Gerald":
        if len(text) > GERALD_MAX_CHARS:
            text = text[:GERALD_MAX_CHARS].rstrip() + " *confetti*"
        width = max(20, min(len(text), 40))
        bar = "═" * width
        lines = [f"╔══ napkin {bar}╗"]
        lines.extend(f"  {line}" for line in text.split("\n"))
        lines.append(f"╚{'═' * (width + 10)}╝")
        lines.append("— G.")
        return "\n".join(lines)

    if professor == "Copenhagen":
        return f"        🍊\nHanz translates:\n{text}"

    if professor == "Steve":
        import random

        dog_num = random.randint(1, 10)
        dogs = "🌭" * 10
        return f"{dogs}\n[Dog {dog_num} of 10]: {text}"

    if professor == "Oakenscroll":
        return re.sub(r"\*([^*]+)\*", r"\1", text)

    if professor == "Riggs":
        return re.sub(r"\*([^*]+)\*", r"[\1]", text)

    if professor == "Ofshield":
        return f"*noted*\n{text}"

    if professor == "Binder":
        label = category or "general correspondence"
        return f"{text}\n[Filed under: {label}]"

    if professor == "Pigeon":
        return f"🐦 PIGEON: {text}"

    return text


def consult(
    *,
    professor: str,
    message: str,
    history: list[dict] | None = None,
    course_code: str | None = None,
    compact: bool = False,
) -> dict:
    """Run one consultation turn. Returns {ok, text, provider, tier, error}."""
    history = list(history or [])
    history.append({"role": "user", "content": message})
    prompt = build_prompt(professor, history, course_code=course_code, compact=compact)
    result = tui_llm.ask(prompt, professor=professor)
    if not result.get("ok"):
        return result

    category = ""
    if professor == "Binder":
        category = tui_llm.categorize_for_binder(message)
    text = format_response_plain(professor, result.get("text", ""), category)
    if not text:
        return {"ok": False, "error": "empty response", "tier": result.get("tier", "ollama")}
    return {
        "ok": True,
        "text": text,
        "provider": result.get("provider", ""),
        "tier": result.get("tier", ""),
    }
