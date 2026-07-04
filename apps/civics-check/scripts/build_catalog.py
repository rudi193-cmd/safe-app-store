#!/usr/bin/env python3
"""Compile data/sources + legacy JSON into data/catalog.json."""

from __future__ import annotations

import json
import re
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCES = DATA / "sources"
OUT = DATA / "catalog.json"

LANES = {
    "schoolhouse": {"id": "schoolhouse", "label": "Schoolhouse Lane", "order": 1},
    "constitution_hall": {"id": "constitution_hall", "label": "Constitution Hall", "order": 2},
    "citizenship_court": {"id": "citizenship_court", "label": "Citizenship Court", "order": 3},
    "statehouse": {"id": "statehouse", "label": "States' Rights & Duties", "order": 4},
    "underground": {"id": "underground", "label": "Underground", "order": 5, "hidden": True},
}


def load(name: str):
    path = DATA / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    path = SOURCES / name
    return json.loads(path.read_text(encoding="utf-8"))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def card(
    cid: str,
    *,
    pavilion: str,
    lane: str,
    kind: str,
    tiers: list[str],
    title: str,
    body: str = "",
    subtitle: str = "",
    prompt: str = "",
    context: str = "",
    source: str = "",
    answers: list | None = None,
    choices: list | None = None,
    answer: str = "",
    distractors: list | None = None,
    tags: list | None = None,
    meta: dict | None = None,
    legacy_id: int | str | None = None,
    category: str = "",
    subcategory: str = "",
    date: str = "",
):
    c = {
        "id": cid,
        "pavilion": pavilion,
        "lane": lane,
        "kind": kind,
        "tiers": tiers,
        "title": title,
        "body": body,
        "subtitle": subtitle,
        "prompt": prompt or title,
        "context": context,
        "source": source,
        "tags": tags or [],
        "meta": meta or {},
    }
    if answers is not None:
        c["answers"] = answers
    if choices is not None:
        c["choices"] = choices
    if answer:
        c["answer"] = answer
    if distractors:
        c["distractors"] = distractors
    if legacy_id is not None:
        c["legacy_id"] = legacy_id
    if category:
        c["category"] = category
    if subcategory:
        c["subcategory"] = subcategory
    if date:
        c["date"] = date
    return c


def build_cards() -> list[dict]:
    cards: list[dict] = []
    officials = load("current_officials.json")
    official_nat_answers = {
        28: [officials["president"]["name"], *officials["president"].get("aliases", [])],
        29: [officials["vice_president"]["name"], *officials["vice_president"].get("aliases", [])],
        46: list(officials["president_party"]["answers"]),
        47: [officials["speaker"]["name"], *officials["speaker"].get("aliases", [])],
    }

    # ── Naturalization (USCIS bank) ─────────────────────────────────────────
    for q in load("naturalization_questions.json"):
        tiers = ["show", "know"]
        if q["id"] <= 20:
            tiers = ["tap", "show", "know"]
        answers = official_nat_answers.get(q["id"], q["answers"])
        cards.append(
            card(
                f"nat-{q['id']:03d}",
                pavilion="naturalization",
                lane="citizenship_court",
                kind="quiz",
                tiers=tiers,
                title=q["question"],
                prompt=q["question"],
                body=q.get("related_fact", ""),
                context=q.get("context", ""),
                answers=answers,
                category=q.get("category", ""),
                subcategory=q.get("subcategory", ""),
                date=q.get("date", ""),
                tags=["uscis", "naturalization"],
                legacy_id=q["id"],
                meta={"current_officials_as_of": officials.get("as_of", "")} if q["id"] in official_nat_answers else {},
            )
        )

    # ── Colonies ────────────────────────────────────────────────────────────
    for c in load("colonies.json"):
        cards.append(
            card(
                f"colony-{slug(c['name'])}",
                pavilion="colonies",
                lane="constitution_hall",
                kind="browse",
                tiers=["tap", "show", "know"],
                title=c["name"],
                subtitle=f"founded {c['founded']} by {c['founder']}",
                body=c["fact"],
                context=c.get("context", ""),
                source=c.get("source", ""),
                tags=["founding", "colonies"],
                meta={"founded": c["founded"], "founder": c["founder"]},
            )
        )

    # ── Signers ─────────────────────────────────────────────────────────────
    for s in load("signers.json"):
        cards.append(
            card(
                f"signer-{slug(s['name'])}",
                pavilion="signers",
                lane="constitution_hall",
                kind="browse",
                tiers=["show", "know"],
                title=s["name"],
                subtitle=s["state"],
                body=s["fact"],
                context=s.get("context", ""),
                source=s.get("source", ""),
                tags=["founding", "signers"],
            )
        )

    # ── Amendments ──────────────────────────────────────────────────────────
    for a in load("amendments.json"):
        tiers = ["tap", "show", "know"] if a["number"] <= 10 else ["show", "know"]
        cards.append(
            card(
                f"amendment-{a['number']:02d}",
                pavilion="amendments",
                lane="constitution_hall",
                kind="browse",
                tiers=tiers,
                title=f"Amendment {a['number']}",
                subtitle=str(a["year"]),
                body=a["summary"],
                context=a.get("context", ""),
                source=a.get("source", ""),
                tags=["amendments", "bill_of_rights" if a["number"] <= 10 else "landmark"],
                meta={"number": a["number"], "year": a["year"]},
            )
        )
        cards.append(
            card(
                f"amendment-quiz-{a['number']:02d}",
                pavilion="amendments",
                lane="constitution_hall",
                kind="quiz",
                tiers=["show", "know"],
                title=f"Amendment {a['number']}",
                prompt=f'Which amendment: "{a["summary"]}"',
                body=a["summary"],
                context=a.get("context", ""),
                source=a.get("source", ""),
                answers=[str(a["number"])],
                tags=["amendments", "quiz"],
                meta={"number": a["number"], "year": a["year"]},
            )
        )

    # ── Quotes ──────────────────────────────────────────────────────────────
    for i, q in enumerate(load("quotes.json"), 1):
        cards.append(
            card(
                f"quote-{i:03d}",
                pavilion="quotes",
                lane="constitution_hall",
                kind="match",
                tiers=["show", "know"],
                title=q["person"],
                prompt=q["quote"],
                body=q["quote"],
                context=q.get("context", ""),
                answer=q["person"],
                distractors=q.get("distractors", []),
                tags=["quotes", "founding"],
            )
        )

    # ── States ──────────────────────────────────────────────────────────────
    all_states = load("states.json")
    all_capitals = [s["capital"] for s in all_states]

    for s in all_states:
        cards.append(
            card(
                f"state-{slug(s['name'])}",
                pavilion="states",
                lane="citizenship_court",
                kind="states",
                tiers=["show", "know"],
                title=s["name"],
                body=s["fact"],
                context=f"Capital: {s['capital']}. Admitted #{s['order']} ({s['admitted']}).",
                tags=["states"],
                meta={"capital": s["capital"], "order": s["order"], "admitted": s["admitted"]},
            )
        )
        distractors = [c for c in all_capitals if c != s["capital"]]
        import random

        # str hash() is salted per-process; crc32 keeps rebuilds deterministic
        random.seed(zlib.crc32(s["name"].encode("utf-8")))
        pick = random.sample(distractors, min(3, len(distractors)))
        choices = [s["capital"]] + pick
        cards.append(
            card(
                f"state-pick-{slug(s['name'])}",
                pavilion="state_stars",
                lane="schoolhouse",
                kind="pick",
                tiers=["tap", "show"],
                title=s["name"],
                prompt=f"What is the capital of {s['name']}?",
                body=s["fact"],
                choices=choices,
                answer=s["capital"],
                tags=["states", "kid"],
                meta={"order": s["order"]},
            )
        )

    # ── Timeline ────────────────────────────────────────────────────────────
    for i, e in enumerate(load("timeline_events.json"), 1):
        cards.append(
            card(
                f"timeline-{i:03d}",
                pavilion="timeline",
                lane="constitution_hall",
                kind="sort",
                tiers=["tap", "show", "know"],
                title=str(e["year"]),
                body=e["event"],
                meta={"year": e["year"]},
                tags=["timeline"],
            )
        )

    # ── On this day (calendar entries, not cards) ───────────────────────────

    # ── Debate ──────────────────────────────────────────────────────────────
    for ti, topic in enumerate(load("debate.json"), 1):
        cards.append(
            card(
                f"debate-topic-{ti}",
                pavilion="debate",
                lane="underground",
                kind="browse",
                tiers=["know"],
                title=f"CONSTITUTIONAL DEBATE: {topic['topic']}",
                subtitle="real quotes, real dates, no editorializing",
                body="",
                tags=["debate", "easter_egg"],
            )
        )
        for ei, ex in enumerate(topic.get("exchanges", []), 1):
            cards.append(
                card(
                    f"debate-{ti}-{ei}",
                    pavilion="debate",
                    lane="underground",
                    kind="debate",
                    tiers=["know"],
                    title=ex["speaker"],
                    subtitle=f"{ex['occasion']} — {ex['date']}",
                    body=f'"{ex["quote"]}"',
                    source=ex.get("citation", ""),
                    tags=["debate", "easter_egg", slug(ex["speaker"])],
                    meta={"topic": topic["topic"]},
                )
            )

    # ── New source packs ────────────────────────────────────────────────────
    for b in load("branches.json"):
        cards.append(
            card(
                f"branch-{b['id']}",
                pavilion="branches",
                lane="schoolhouse",
                kind="pick",
                tiers=["tap", "show"],
                title=b["title"],
                prompt=b["prompt"],
                body=b["body"],
                context=b.get("context", ""),
                source=b.get("source", ""),
                choices=b["choices"],
                answer=b["answer"],
                tags=["branches", "kid"],
            )
        )

    for sym in load("symbols.json"):
        cards.append(
            card(
                f"symbol-{sym['id']}",
                pavilion="symbols",
                lane="schoolhouse",
                kind="pick",
                tiers=["tap"],
                title=sym["title"],
                prompt=sym["prompt"],
                body=sym["body"],
                context=sym.get("context", ""),
                source=sym.get("source", ""),
                choices=sym["choices"],
                answer=sym["answer"],
                tags=["symbols", "kid"],
            )
        )

    for step in load("bill_law.json"):
        cards.append(
            card(
                f"bill-law-{step['step']}",
                pavilion="bill_law",
                lane="constitution_hall",
                kind="browse",
                tiers=["tap", "show", "know"],
                title=f"Step {step['step']}: {step['title']}",
                body=step["body"],
                source=step.get("source", ""),
                tags=["legislative_process"],
                meta={"step": step["step"]},
            )
        )

    for ec in load("electoral.json"):
        cid = f"electoral-{ec['id']}"
        if ec.get("choices"):
            cards.append(
                card(
                    cid,
                    pavilion="electoral",
                    lane="constitution_hall",
                    kind="pick",
                    tiers=["show", "know"],
                    title=ec["title"],
                    prompt=ec.get("prompt", ec["title"]),
                    body=ec["body"],
                    context=ec.get("context", ""),
                    source=ec.get("source", ""),
                    choices=ec["choices"],
                    answer=ec["answer"],
                    tags=["electoral_college"],
                )
            )
        else:
            cards.append(
                card(
                    cid,
                    pavilion="electoral",
                    lane="constitution_hall",
                    kind="browse",
                    tiers=["show", "know"],
                    title=ec["title"],
                    body=ec["body"],
                    context=ec.get("context", ""),
                    source=ec.get("source", ""),
                    tags=["electoral_college"],
                )
            )

    # ── The Hall of Presidents (a forgotten Disney favorite) ────────────────
    def ordinal(n: int) -> str:
        if 10 <= n % 100 <= 13:
            return f"{n}th"
        return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"

    STAGE_DIRECTIONS = [
        "The animatronic nods.",
        "The animatronic rises and pauses for applause.",
        "The animatronic adjusts its coat.",
        "The animatronic gazes into the middle distance.",
        "The animatronic nods to the animatronic beside it.",
    ]
    for pres in load("presidents.json"):
        n = pres["n"]
        body = pres["fact"]
        if pres.get("reckoning"):
            body += f"\n\nThe record: {pres['reckoning']}"
        cards.append(
            card(
                f"potus-{n:02d}",
                pavilion="hall_of_presidents",
                lane="constitution_hall",
                kind="browse",
                tiers=["tap", "show", "know"],
                title=f"{n}. {pres['name']}",
                subtitle=pres["years"],
                body=body,
                context=STAGE_DIRECTIONS[n % len(STAGE_DIRECTIONS)],
                source="https://www.whitehouse.gov/about-the-white-house/presidents/",
                tags=["presidents", "hall"],
                meta={"number": n},
            )
        )
        cards.append(
            card(
                f"potus-quiz-{n:02d}",
                pavilion="hall_of_presidents",
                lane="constitution_hall",
                kind="quiz",
                tiers=["show", "know"],
                title=pres["name"],
                prompt=f"Who was the {ordinal(n)} President of the United States?",
                body=pres["fact"],
                source="https://www.whitehouse.gov/about-the-white-house/presidents/",
                answers=[pres["name"]] + pres.get("aliases", []),
                tags=["presidents", "quiz"],
                meta={"number": n},
            )
        )

    # ── By the Numbers: American numerology ─────────────────────────────────
    for n in load("numbers.json"):
        nid = slug(n["number"])
        cards.append(
            card(
                f"number-{nid}",
                pavilion="numbers",
                lane="schoolhouse",
                kind="browse",
                tiers=["tap", "show", "know"],
                title=n["title"],
                body=n["body"],
                source=n.get("source", ""),
                tags=["numbers", "numerology"],
            )
        )
        cards.append(
            card(
                f"number-quiz-{nid}",
                pavilion="numbers",
                lane="schoolhouse",
                kind="quiz",
                tiers=["show", "know"],
                title=n["title"],
                prompt=n["prompt"],
                body=n["body"],
                source=n.get("source", ""),
                answers=n["answers"],
                tags=["numbers", "quiz"],
            )
        )

    # ── Statehouse: federalism pack ─────────────────────────────────────────
    federalism = load("federalism.json")
    for p in federalism["powers"]:
        cards.append(
            card(
                f"power-{p['id']}",
                pavilion="power_split",
                lane="statehouse",
                kind="pick",
                tiers=["show", "know"],
                title=p["title"],
                prompt=p["prompt"],
                body=p["body"],
                source=p.get("source", ""),
                choices=["Federal", "State", "Both"],
                answer=p["answer"],
                tags=["federalism", "powers"],
            )
        )
    for d in federalism["duties"]:
        cards.append(
            card(
                f"duty-{d['id']}",
                pavilion="duty_roll",
                lane="statehouse",
                kind="quiz",
                tiers=["show", "know"],
                title=d["prompt"],
                prompt=d["prompt"],
                body=d["body"],
                source=d.get("source", ""),
                answers=d["answers"],
                tags=["federalism", "responsibilities"],
            )
        )
    for r in federalism["reading"]:
        cards.append(
            card(
                f"reserved-{r['id']}",
                pavilion="reserved_room",
                lane="statehouse",
                kind="browse",
                tiers=["show", "know"],
                title=r["title"],
                body=r["body"],
                source=r.get("source", ""),
                tags=["federalism", "reading"],
            )
        )

    # Bill of Rights bingo — one pick card per BoR amendment summary
    for a in load("amendments.json"):
        if a["number"] > 10:
            continue
        others = [x for x in load("amendments.json") if x["number"] <= 10 and x["number"] != a["number"]]
        import random as rnd

        rnd.seed(a["number"] * 97)
        distractors = rnd.sample(others, min(3, len(others)))
        choices = [f"Amendment {a['number']}"] + [f"Amendment {d['number']}" for d in distractors]
        cards.append(
            card(
                f"bor-bingo-{a['number']:02d}",
                pavilion="rights_bingo",
                lane="schoolhouse",
                kind="pick",
                tiers=["tap", "show"],
                title=f"Amendment {a['number']}",
                prompt=f"Which amendment: {a['summary']}",
                body=a["summary"],
                choices=choices,
                answer=f"Amendment {a['number']}",
                context=a.get("context", ""),
                source=a.get("source", ""),
                tags=["bill_of_rights", "kid"],
                meta={"number": a["number"]},
            )
        )

    return cards


def build_pavilions() -> list[dict]:
    return [
        {"id": "symbols", "lane": "schoolhouse", "label": "Symbol Safari", "subtitle": "Flag, eagle, bell, anthem", "kinds": ["pick"], "default_tier": "tap"},
        {"id": "branches", "lane": "schoolhouse", "label": "Three Branches", "subtitle": "Who makes laws?", "kinds": ["pick"], "default_tier": "tap"},
        {"id": "rights_bingo", "lane": "schoolhouse", "label": "Bill of Rights Bingo", "subtitle": "Match the right", "kinds": ["pick"], "default_tier": "tap"},
        {"id": "state_stars", "lane": "schoolhouse", "label": "State Star", "subtitle": "Pick the capital", "kinds": ["pick"], "default_tier": "tap"},
        {"id": "on_this_day", "lane": "schoolhouse", "label": "On This Day", "subtitle": "Today in the founding era", "kinds": ["browse"], "default_tier": "tap"},
        {"id": "numbers", "lane": "schoolhouse", "label": "By the Numbers", "subtitle": "American numerology, certified", "kinds": ["quiz", "browse"], "default_tier": "show"},
        {"id": "colonies", "lane": "constitution_hall", "label": "13 Colonies", "subtitle": "Founding to founding", "kinds": ["browse"], "default_tier": "show"},
        {"id": "signers", "lane": "constitution_hall", "label": "Signers Hall", "subtitle": "Declaration lives", "kinds": ["browse"], "default_tier": "show"},
        {"id": "amendments", "lane": "constitution_hall", "label": "Amendment Explorer", "subtitle": "Browse or quiz all 27", "kinds": ["browse", "quiz"], "default_tier": "show"},
        {"id": "hall_of_presidents", "lane": "constitution_hall", "label": "The Hall of Presidents", "subtitle": "They're all here. They nod.", "kinds": ["browse", "quiz"], "default_tier": "show"},
        {"id": "quotes", "lane": "constitution_hall", "label": "Quote Match", "subtitle": "Who said it?", "kinds": ["match"], "default_tier": "show"},
        {"id": "timeline", "lane": "constitution_hall", "label": "Timeline Sort", "subtitle": "Order the years", "kinds": ["sort"], "default_tier": "show"},
        {"id": "bill_law", "lane": "constitution_hall", "label": "How a Bill Becomes Law", "subtitle": "Six steps", "kinds": ["browse"], "default_tier": "show"},
        {"id": "electoral", "lane": "constitution_hall", "label": "Electoral College", "subtitle": "270 to win", "kinds": ["browse", "pick"], "default_tier": "show"},
        {"id": "naturalization", "lane": "citizenship_court", "label": "Naturalization Quiz", "subtitle": "10 questions, need 6", "kinds": ["quiz"], "default_tier": "know"},
        {"id": "missed", "lane": "citizenship_court", "label": "Missed Review", "subtitle": "Resurface wrong answers", "kinds": ["quiz"], "default_tier": "know"},
        {"id": "speed", "lane": "citizenship_court", "label": "Speed Round", "subtitle": "60 seconds", "kinds": ["quiz"], "default_tier": "know"},
        {"id": "states", "lane": "citizenship_court", "label": "State Matchup", "subtitle": "Capitals and admission order", "kinds": ["states"], "default_tier": "know"},
        {"id": "duel", "lane": "citizenship_court", "label": "Pass-the-Keyboard Duel", "subtitle": "Two players", "kinds": ["duel"], "default_tier": "know"},
        {"id": "power_split", "lane": "statehouse", "label": "Who Holds the Power?", "subtitle": "Federal, State, or Both", "kinds": ["pick"], "default_tier": "show"},
        {"id": "duty_roll", "lane": "statehouse", "label": "Duty Roll", "subtitle": "Rights and responsibilities", "kinds": ["quiz"], "default_tier": "show"},
        {"id": "reserved_room", "lane": "statehouse", "label": "Reserved Powers Reading Room", "subtitle": "The Tenth Amendment shelf", "kinds": ["browse"], "default_tier": "show"},
        {"id": "debate", "lane": "underground", "label": "Constitutional Debate", "subtitle": "Hidden — real quotes", "kinds": ["debate", "browse"], "default_tier": "know", "hidden": True},
    ]


def build_activities() -> list[dict]:
    return [
        {"id": "naturalization", "pavilion": "naturalization", "kind": "quiz", "tier": "know", "count": 10, "pass_ratio": 0.6, "pool_filter": {"pavilion": "naturalization", "kind": "quiz"}},
        {"id": "missed", "pavilion": "missed", "kind": "quiz", "tier": "know", "count": 10, "pass_ratio": 0.6, "pool_filter": {"pavilion": "naturalization", "kind": "quiz"}, "weighted_misses": True},
        {"id": "speed", "pavilion": "speed", "kind": "quiz", "tier": "know", "count": 100, "time_limit": 60, "pool_filter": {"pavilion": "naturalization", "kind": "quiz"}},
        {"id": "states", "pavilion": "states", "kind": "states", "tier": "know", "count": 8, "pool_filter": {"pavilion": "states", "kind": "states"}},
        {"id": "timeline", "pavilion": "timeline", "kind": "sort", "tier": "show", "count": 8, "pool_filter": {"pavilion": "timeline", "kind": "sort"}},
        {"id": "timeline-tap", "pavilion": "timeline", "kind": "sort", "tier": "tap", "count": 4, "pool_filter": {"pavilion": "timeline", "kind": "sort"}},
        {"id": "quotes", "pavilion": "quotes", "kind": "match", "tier": "show", "count": 6, "pool_filter": {"pavilion": "quotes", "kind": "match"}},
        {"id": "colonies", "pavilion": "colonies", "kind": "browse", "tier": "show", "pool_filter": {"pavilion": "colonies", "kind": "browse"}},
        {"id": "signers", "pavilion": "signers", "kind": "browse", "tier": "show", "pool_filter": {"pavilion": "signers", "kind": "browse"}},
        {"id": "amendments", "pavilion": "amendments", "kind": "browse", "tier": "show", "pool_filter": {"pavilion": "amendments", "kind": "browse"}},
        {"id": "amendment-quiz", "pavilion": "amendments", "kind": "quiz", "tier": "know", "count": 5, "pool_filter": {"pavilion": "amendments", "kind": "quiz"}},
        {"id": "on_this_day", "pavilion": "on_this_day", "kind": "browse", "tier": "tap", "pool_filter": {"tag": "on_this_day"}},
        {"id": "branches", "pavilion": "branches", "kind": "pick", "tier": "tap", "count": 3, "pool_filter": {"pavilion": "branches", "kind": "pick"}},
        {"id": "symbols", "pavilion": "symbols", "kind": "pick", "tier": "tap", "count": 5, "pool_filter": {"pavilion": "symbols", "kind": "pick"}},
        {"id": "rights_bingo", "pavilion": "rights_bingo", "kind": "pick", "tier": "tap", "count": 10, "pool_filter": {"pavilion": "rights_bingo", "kind": "pick"}},
        {"id": "state_stars", "pavilion": "state_stars", "kind": "pick", "tier": "tap", "count": 8, "pool_filter": {"pavilion": "state_stars", "kind": "pick"}},
        {"id": "bill_law", "pavilion": "bill_law", "kind": "browse", "tier": "show", "pool_filter": {"pavilion": "bill_law", "kind": "browse"}},
        {"id": "electoral", "pavilion": "electoral", "kind": "pick", "tier": "show", "count": 4, "pool_filter": {"pavilion": "electoral", "kind": "pick"}},
        {"id": "hall_of_presidents", "pavilion": "hall_of_presidents", "kind": "browse", "tier": "show", "primary": True, "pool_filter": {"pavilion": "hall_of_presidents", "kind": "browse"}},
        {"id": "presidents-quiz", "pavilion": "hall_of_presidents", "kind": "quiz", "tier": "know", "count": 10, "pool_filter": {"pavilion": "hall_of_presidents", "kind": "quiz"}},
        {"id": "numbers-quiz", "pavilion": "numbers", "kind": "quiz", "tier": "show", "count": 10, "pool_filter": {"pavilion": "numbers", "kind": "quiz"}},
        {"id": "numbers", "pavilion": "numbers", "kind": "browse", "tier": "show", "pool_filter": {"pavilion": "numbers", "kind": "browse"}},
        {"id": "power_split", "pavilion": "power_split", "kind": "pick", "tier": "show", "count": 8, "pool_filter": {"pavilion": "power_split", "kind": "pick"}},
        {"id": "duty_roll", "pavilion": "duty_roll", "kind": "quiz", "tier": "show", "count": 8, "pass_ratio": 0.6, "pool_filter": {"pavilion": "duty_roll", "kind": "quiz"}},
        {"id": "reserved_room", "pavilion": "reserved_room", "kind": "browse", "tier": "show", "pool_filter": {"pavilion": "reserved_room", "kind": "browse"}},
        {"id": "debate", "pavilion": "debate", "kind": "browse", "tier": "know", "pool_filter": {"pavilion": "debate"}},
        {"id": "duel", "pavilion": "duel", "kind": "duel", "tier": "know", "count": 10},
    ]


def build_calendar() -> dict:
    cal = load("on_this_day.json")
    # Also tag on_this_day browse cards dynamically at runtime — store calendar only
    return cal


def _validate_cards(cards: list[dict]) -> None:
    bad: list[str] = []
    for c in cards:
        for ans in c.get("answers") or []:
            low = str(ans).lower()
            if "varies" in low and "check" in low and "officeholder" in low:
                bad.append(f"{c['id']}: placeholder answer {ans!r}")
    if bad:
        raise SystemExit("catalog build failed — unresolved current-office answers:\n  " + "\n  ".join(bad))


def main():
    cards = build_cards()
    # on_this_day dynamic cards from calendar
    cal = build_calendar()
    for key, events in cal.items():
        for i, text in enumerate(events):
            cards.append(
                card(
                    f"otd-{key}-{i}",
                    pavilion="on_this_day",
                    lane="schoolhouse",
                    kind="browse",
                    tiers=["tap", "show"],
                    title="On this day",
                    body=text,
                    tags=["on_this_day", "calendar"],
                    meta={"date_key": key},
                )
            )

    _validate_cards(cards)

    catalog = {
        "version": 2,
        "meta": {
            "built_by": "scripts/build_catalog.py",
            "card_count": len(cards),
            "kb_hub": "CVRAMERICA01",
            "textual_hub": "TXR04B11D4B8D",
        },
        "lanes": list(LANES.values()),
        "pavilions": build_pavilions(),
        "activities": build_activities(),
        "cards": cards,
        "calendar": cal,
        "fair_schedule": load("fair_schedule.json"),
    }
    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} — {len(cards)} cards, {len(catalog['pavilions'])} pavilions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
