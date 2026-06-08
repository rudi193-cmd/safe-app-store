"""Jeles Sovereign TUI Trivia Engine — quiz from your last search or literary deep cuts."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import sys
from typing import Any

log = logging.getLogger("jeles.trivia")

# --- ANSI Escapes for a Clean TUI Look ---
_NO_COLOR = bool(os.environ.get("NO_COLOR"))
CLEAR_SCREEN = "" if _NO_COLOR else "\033[2J\033[H"
RESET = "" if _NO_COLOR else "\033[0m"
BOLD = "" if _NO_COLOR else "\033[1m"
CYAN = "" if _NO_COLOR else "\033[36m"
GREEN = "" if _NO_COLOR else "\033[32m"
RED = "" if _NO_COLOR else "\033[31m"
YELLOW = "" if _NO_COLOR else "\033[33m"

LABELS = ["A", "B", "C", "D"]

# Literary deep cuts when no search context (--trivia standalone)
TRIVIA_BANK = [
    {
        "category": "PHILIP K. DICK DEEP CUTS",
        "question": "In the devastating final scene of 'A Scanner Darkly', Bob Arctor (under the identity 'Bruce') is sent to a rehabilitation farm where he discovers blue flowers hidden in the corn. What is the street name of the drug manufactured from these flowers?",
        "options": ["Substance D", "Blue Joy", "Can-D", "Slow Death"],
        "answer": "A",
        "explanation": "Substance D (also known as 'Death') is the central drug of the novel. Can-D is from 'The Three Stigmata of Palmer Eldritch'.",
    },
    {
        "category": "IRISH ABSURDISM",
        "question": "In Flann O'Brien's surrealist masterpiece 'The Third Policeman', the local police force is obsessed with a bizarre physical theory regarding what common mode of transport?",
        "options": ["Steam trains", "Bicycles", "Horse carriages", "Hot air balloons"],
        "answer": "B",
        "explanation": "The novel introduces the 'Atomic Theory', suggesting that people who ride bicycles too much exchange molecules with them.",
    },
    {
        "category": "REGIONAL AMERICAN LIT",
        "question": "E.P. O'Donnell's 1941 Delta novel 'The Great Big Doorstep' features the Crochet family, whose lives revolve around an architectural salvage piece found floating down which river?",
        "options": ["The Mississippi", "The Sabine", "The Colorado", "The Atchafalaya"],
        "answer": "A",
        "explanation": "They hauled a massive doorstep out of a Mississippi River flood and spent the book trying to afford a shack worthy of it.",
    },
    {
        "category": "REVISIONIST WESTERNS",
        "question": "Thomas Berger's 'Little Big Man' is framed as the recollections of which 111-year-old narrator, who claims to be the sole white survivor of the Battle of the Little Bighorn?",
        "options": ["Augustus McCrae", "Jack Crabb", "John Chisum", "Josey Wales"],
        "answer": "B",
        "explanation": "Jack Crabb narrates his life bouncing between white pioneer society and the Cheyenne Nation.",
    },
    {
        "category": "THEOLOGICAL INVERSIONS",
        "question": "Stoics viewed the universe as ordered by Logos. Which concept serves as the inverse of this total cosmic control?",
        "options": ["Ataraxia", "Chaos / Fortuna", "Apatheia", "Prosochê"],
        "answer": "B",
        "explanation": "Chaos or Fortuna represent unmanaged reality outside rational structure.",
    },
]

_TRIVIA_SYSTEM = (
    "You are Jeles, a librarian running a trivia quiz about the user's search topic. "
    "Use the provided topic brief as the study material. "
    "Generate 3 to 5 multiple-choice questions about the subject matter itself. "
    "Prefer why/how/relationship questions: causes, themes, contrasts, implications, chronology, "
    "definitions, and which concept best explains another concept. Facts are allowed only when "
    "they help understand the topic. "
    "Question text and answer options must read like a normal topic quiz, not a search-results quiz. "
    "Never ask about websites, domains, URLs, listings, used items, result titles, rankings, snippets, "
    "sources, or where information came from. "
    "Every correct answer must be supported by the topic brief. "
    "Return ONLY a JSON array with no markdown fences. Each object must have:\n"
    '  "category": short uppercase topic tag,\n'
    '  "question": string,\n'
    '  "options": array of exactly 4 distinct subject-matter answers,\n'
    '  "answer": one of "A", "B", "C", "D" (letter of the correct option),\n'
    '  "explanation": one sentence explaining the subject-matter reason.'
)

_BRIEF_SYSTEM = (
    "You are Jeles preparing study material for a trivia quiz. "
    "Convert the user's noisy search results into a compact topic brief about the subject itself. "
    "Ignore websites, domains, URLs, search rankings, snippets as artifacts, ecommerce listings, used-item "
    "marketplaces, buy/sell language, stock availability, prices, and calls to visit a site. "
    "If the results are commercial or navigational, infer the intended topic from the query and write "
    "stable encyclopedic background about that topic. "
    "Include 5-8 concise bullets covering definition, origin/history, design/function, cultural context, "
    "important distinctions, and common misconceptions when relevant. "
    "Do not mention that the brief came from search results."
)


def _rule(width: int = 60) -> str:
    return f"{BOLD}{CYAN}{'=' * width}{RESET}"


def _context_block(query: str, hits: list[dict[str, Any]], synthesis: str = "") -> str:
    lines = [
        f"Quiz topic: {query}",
        "",
        "Raw material to distill. Ignore website/listing/search artifacts; keep only subject-matter facts:",
    ]
    for idx, hit in enumerate(hits[:8], start=1):
        title = (hit.get("title") or "Untitled").strip()
        snippet = (hit.get("snippet") or "").strip()[:420]
        if snippet:
            lines.append(f"Note {idx}: {snippet}")
        elif title:
            lines.append(f"Note {idx}: {title}")
    if synthesis.strip():
        lines.append("")
        lines.append("Jeles synthesis from these results:")
        lines.append(synthesis.strip()[:900])
    return "\n".join(lines)


def _brief_context(query: str, hits: list[dict[str, Any]], synthesis: str = "") -> str:
    return _context_block(query, hits, synthesis)


def _build_topic_brief(query: str, hits: list[dict[str, Any]], synthesis: str = "") -> str:
    """Distill noisy search results into subject-matter study notes."""
    if synthesis.strip():
        return synthesis.strip()[:1600]
    try:
        from askjeles.willow_path import bootstrap

        bootstrap()
        from core.llm_edge import respond as llm_respond

        brief = llm_respond(_BRIEF_SYSTEM, [], _brief_context(query, hits, synthesis))
        brief = _scrub_search_surface(brief)
        if brief.strip():
            return brief.strip()[:1800]
    except Exception as exc:
        log.warning("LLM topic brief generation failed: %s", exc)
    return _fallback_topic_brief(query, hits)


def _scrub_search_surface(text: str) -> str:
    """Remove obvious web/listing artifacts before quiz generation."""
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"\b(?:www\.)?[A-Za-z0-9-]+\.(?:com|org|net|gov|edu|io|co)\b", "", text)
    blocked = re.compile(
        r"\b(?:buy|sale|used|pre-owned|inventory|listing|listings|price|prices|dealer|dealers|"
        r"shop|shopping|cart|checkout|shipping|finance|financing|stock|available|website|"
        r"official site|visit|click|domain|url)\b",
        re.I,
    )
    lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
    kept = [line for line in lines if not blocked.search(line)]
    return "\n".join(kept)


def _fallback_topic_brief(query: str, hits: list[dict[str, Any]]) -> str:
    """Build a rough subject brief when the LLM brief step is unavailable."""
    topic = (query or "the topic").strip()
    raw = " ".join(
        _scrub_search_surface(f"{h.get('snippet') or ''} {h.get('title') or ''}")
        for h in hits[:8]
    )
    words = []
    stop = {
        "about",
        "after",
        "available",
        "before",
        "dealer",
        "dealers",
        "find",
        "from",
        "have",
        "listing",
        "listings",
        "inventory",
        "official",
        "price",
        "prices",
        "financing",
        "sale",
        "search",
        "shop",
        "site",
        "their",
        "there",
        "these",
        "those",
        "used",
        "visit",
        "website",
        "which",
        "with",
    }
    for word in re.findall(r"[A-Za-z][A-Za-z-]{4,}", raw):
        w = word.lower().strip("-")
        if w not in stop and w not in words:
            words.append(w)
    signals = ", ".join(words[:10]) if words else topic
    return (
        f"- Topic: {topic}.\n"
        f"- Key subject signals from the search: {signals}.\n"
        f"- Build questions about what {topic} is, how it works, where it came from, "
        "what distinguishes it, and why it matters culturally or practically.\n"
        "- Avoid website, shopping, listing, and search-engine details."
    )


def _extract_json_array(text: str) -> list[Any]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            pass
    return []


def _normalize_question(raw: dict[str, Any], *, default_category: str) -> dict[str, Any] | None:
    question = str(raw.get("question") or "").strip()
    options = [str(o).strip() for o in (raw.get("options") or []) if str(o).strip()]
    answer = str(raw.get("answer") or "").strip().upper()
    if not question or len(options) < 2:
        return None
    literal_markers = (
        "which site hosts",
        "which term appears",
        "which word appears",
        "preview snippet",
        "result number",
        "which result",
        "what result",
        "which source",
        "which website",
        "which title",
        "search result",
        "study note",
        "according to note",
        "vespa.com",
        ".com",
        "used bike",
        "used bikes",
        "listing",
        "listings",
        "dealer",
        "price",
        "buy",
        "sell",
    )
    if any(marker in question.lower() for marker in literal_markers):
        return None
    while len(options) < 4:
        options.append(f"(none of the above {len(options)})")
    options = options[:4]
    if answer not in LABELS:
        # Accept numeric index or full option text
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            answer = LABELS[int(answer) - 1]
        else:
            for i, opt in enumerate(options):
                if opt.lower() == answer.lower():
                    answer = LABELS[i]
                    break
            else:
                answer = "A"
    return {
        "category": str(raw.get("category") or default_category).strip() or default_category,
        "question": question,
        "options": options,
        "answer": answer,
        "explanation": str(raw.get("explanation") or "See your search results.").strip(),
    }


def _fallback_from_hits(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Semantic-ish template questions when LLM is unavailable."""
    bank: list[dict[str, Any]] = []
    usable = [h for h in hits if (h.get("title") or h.get("snippet"))]
    if len(usable) < 2:
        return bank

    stopwords = {
        "about",
        "after",
        "again",
        "their",
        "there",
        "these",
        "those",
        "which",
        "would",
        "could",
        "should",
        "search",
        "result",
        "results",
        "according",
        "retrieved",
        "official",
        "website",
        "source",
        "archive",
        "catalog",
        "database",
        "homepage",
        "information",
        "lists",
        "page",
        "pages",
        "dealer",
        "dealers",
        "price",
        "prices",
        "shopping",
        "inventory",
        "listing",
        "listings",
        "available",
        "pre-owned",
        "finance",
        "financing",
    }

    def keywords(hit: dict[str, Any]) -> list[str]:
        text = (hit.get("snippet") or hit.get("title") or "")
        words = []
        for word in re.findall(r"[A-Za-z][A-Za-z-]{4,}", text):
            w = word.lower().strip("-")
            if w not in stopwords and w not in words:
                words.append(w)
        return words

    def concept_phrase(kws: list[str]) -> str:
        if not kws:
            return "the broader topic"
        if len(kws) == 1:
            return kws[0].replace("-", " ")
        return " / ".join(w.replace("-", " ") for w in kws[:3])

    keyed = [(hit, keywords(hit)) for hit in usable]
    concepts = []
    for _, kws in keyed:
        if not kws:
            continue
        phrase = concept_phrase(kws)
        if phrase not in concepts:
            concepts.append(phrase)
    if len(concepts) < 2:
        return bank

    templates = [
        'Which idea is most central to understanding "{query}"?',
        'Which concept best explains one major angle of "{query}"?',
        'Which theme would help someone reason about "{query}" instead of just naming facts?',
    ]
    for idx, correct in enumerate(concepts[:3]):
        distractors = [c for c in concepts if c != correct][:3]
        while len(distractors) < 3:
            distractors.append(f"another angle on {query[:30] or 'the topic'}")
        options = [correct] + distractors[:3]
        random.shuffle(options)
        answer = LABELS[options.index(correct)]
        bank.append(
            {
                "category": f"SEMANTIC SEARCH: {query[:32]}",
                "question": templates[idx % len(templates)].format(query=query[:60]),
                "options": options,
                "answer": answer,
                "explanation": (
                    "This concept is the strongest topical signal in the available study notes."
                ),
            }
        )

    if len(concepts) >= 4:
        correct = concepts[0]
        options = concepts[:4]
        random.shuffle(options)
        bank.append(
            {
                "category": f"SEMANTIC SEARCH: {query[:32]}",
                "question": (
                    f"Which concept would be the best starting point for explaining the broader topic of "
                    f"\"{query[:60]}\"?"
                ),
                "options": options,
                "answer": LABELS[options.index(correct)],
                "explanation": (
                    "It is the most prominent concept available for building an explanation of the topic."
                ),
            }
        )
    return bank[:5]


def _fallback_from_brief(query: str, brief: str) -> list[dict[str, Any]]:
    """Topic-only fallback from the distilled brief."""
    text = f"{query} {brief}".lower()
    stop = {
        "about",
        "angle",
        "avoid",
        "brief",
        "build",
        "came",
        "covering",
        "details",
        "explaining",
        "listing",
        "matter",
        "notes",
        "price",
        "query",
        "search",
        "shopping",
        "signals",
        "site",
        "subject",
        "topic",
        "used",
        "website",
    }
    words = []
    for word in re.findall(r"[A-Za-z][A-Za-z-]{4,}", text):
        w = word.lower().strip("-")
        if w not in stop and w not in words:
            words.append(w)
    concepts = []
    for idx in range(0, min(len(words), 15), 3):
        phrase = " / ".join(words[idx : idx + 3])
        if phrase and phrase not in concepts:
            concepts.append(phrase)
    questions = [
        f'Which concept is most central to understanding "{query}"?',
        f'Which idea best explains one major angle of "{query}"?',
        f'Which theme would help someone reason about "{query}" instead of just naming facts?',
    ]

    if len(concepts) < 4:
        concepts += [
            f"the broad definition of {query}",
            f"the history of {query}",
            f"the practical use of {query}",
            f"the cultural meaning of {query}",
        ]

    bank: list[dict[str, Any]] = []
    for idx, question in enumerate(questions[:3]):
        correct = concepts[idx]
        distractors = [c for c in concepts if c != correct][:3]
        options = [correct] + distractors
        random.shuffle(options)
        bank.append(
            {
                "category": f"TOPIC QUIZ: {query[:32]}",
                "question": question,
                "options": options,
                "answer": LABELS[options.index(correct)],
                "explanation": f'This answer focuses on the subject matter of "{query}", not the search surface.',
            }
        )
    return bank


def generate_from_search(
    query: str,
    hits: list[dict[str, Any]],
    *,
    synthesis: str = "",
) -> list[dict[str, Any]]:
    """Build a trivia bank from the user's last search results."""
    query = (query or "").strip()
    hits = [h for h in (hits or []) if h.get("title") or h.get("snippet")]
    if not query or not hits:
        return []

    category = f"TOPIC QUIZ: {query[:42]}"
    topic_brief = _build_topic_brief(query, hits, synthesis=synthesis)
    try:
        from askjeles.willow_path import bootstrap

        bootstrap()
        from core.llm_edge import respond as llm_respond

        raw = llm_respond(
            _TRIVIA_SYSTEM,
            [],
            f"Quiz topic: {query}\n\nTopic brief:\n{topic_brief}",
        )
        parsed = []
        for item in _extract_json_array(raw):
            if isinstance(item, dict):
                norm = _normalize_question(item, default_category=category)
                if norm:
                    parsed.append(norm)
        if parsed:
            log.info("generated %d trivia questions for %r", len(parsed), query)
            return parsed[:5]
    except Exception as exc:
        log.warning("LLM trivia generation failed: %s", exc)

    fallback = _fallback_from_brief(query, topic_brief)
    if not fallback:
        fallback = _fallback_from_hits(query, hits)
    if fallback:
        log.info("using fallback trivia for %r (%d questions)", query, len(fallback))
    return fallback


def render_header(score: int, current: int, total: int, subtitle: str = "") -> None:
    print(CLEAR_SCREEN, end="")
    print(_rule())
    print("  JELES // SOVEREIGN TUI TRIVIA ENGINE v1.0")
    if subtitle:
        print(f"  {subtitle[:58]}")
    print(_rule())
    print(f"  [Progress: {current}/{total}]   [Current Score: {score}/{total * 10}]")
    print("-" * 60)


def run_jeles(
    bank: list[dict[str, Any]] | None = None,
    *,
    embedded: bool = False,
    subtitle: str = "",
) -> None:
    questions = bank or TRIVIA_BANK
    if not questions:
        print(f"{RED}No trivia questions could be built from that search.{RESET}")
        if embedded:
            input(f"{YELLOW}Press Enter to return to Jeles…{RESET}")
        return

    score = 0
    total_q = len(questions)

    for idx, q in enumerate(questions):
        render_header(score, idx + 1, total_q, subtitle=subtitle)

        print(f"\n{BOLD}{YELLOW}CATEGORY: {q['category']}{RESET}\n")
        print(f"{q['question']}\n")

        options = q.get("options") or []
        for i, opt in enumerate(options[:4]):
            print(f"  {BOLD}{CYAN}[{LABELS[i]}]{RESET} {opt}")
        print("\n" + "-" * 60)
        back_hint = "return to Jeles" if embedded else "exit"
        print(f"  {YELLOW}A-D answer  |  q quit ({back_hint}){RESET}")

        while True:
            choice = input(f"\n{BOLD}Your Answer (A-D) -> {RESET}").strip().upper()
            if choice == "Q":
                return
            if choice in LABELS[: len(options)]:
                break
            print(f"{RED}Invalid node track. Input A, B, C, or D.{RESET}")

        if choice == q["answer"]:
            print(f"\n{GREEN}{BOLD}CORRECT.{RESET} +10 Data Units.")
            score += 10
        else:
            print(f"\n{RED}{BOLD}SYSTEM MISMATCH.{RESET} Expected [{q['answer']}].")

        print(f"\n{BOLD}Log Entry:{RESET} {q.get('explanation', '')}")
        print(f"\n{YELLOW}Press Enter to cycle to the next memory ring...{RESET}")
        input()

    print(CLEAR_SCREEN, end="")
    print(_rule())
    print("  RUN COMPLETE: JELES COGNITIVE DISSONANCE BENCHMARK")
    print(_rule())
    print(f"\n  Final System Integrity: {score} / {total_q * 10} points.")
    percentage = (score / (total_q * 10)) * 100 if total_q else 0
    print(f"  Accuracy Rating: {percentage:.1f}%")

    if percentage >= 80:
        print(f"\n  {GREEN}Status: High Sovereignty. Reality matrices aligned.{RESET}\n")
    else:
        print(f"\n  {RED}Status: High Entropy. Reality slipping into a PKD third-act twist.{RESET}\n")

    if embedded:
        input(f"{YELLOW}Press Enter to return to Jeles…{RESET}")


def main(
    *,
    embedded: bool = False,
    query: str = "",
    hits: list[dict[str, Any]] | None = None,
    synthesis: str = "",
) -> None:
    """
    Run trivia. When launched from the Textual TUI (embedded=True), returns to Jeles
    instead of exiting the process. With query+hits, questions come from that search.
    """
    bank: list[dict[str, Any]] | None = None
    subtitle = ""

    if query.strip() and hits:
        print(f"{CYAN}Jeles is drafting trivia from your search…{RESET}\n")
        bank = generate_from_search(query, hits, synthesis=synthesis)
        subtitle = f"Quiz: {query[:50]}"
    elif not embedded:
        bank = TRIVIA_BANK

    try:
        run_jeles(bank, embedded=embedded, subtitle=subtitle)
    except KeyboardInterrupt:
        print(f"\n\n{RED}Trivia interrupted.{RESET}")
        if embedded:
            return
        sys.exit(0)


if __name__ == "__main__":
    main()
