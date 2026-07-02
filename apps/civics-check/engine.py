"""Civics-check engine — catalog-backed facade for CLI and TUI."""

from __future__ import annotations

import json
import random
from datetime import date
from functools import lru_cache
from civics.paths import data_dir

from civics.catalog import get_catalog, reload_catalog
from civics.scoring import answer_matches, pick_items, score_pass_fail
from civics.session import ActivitySession

import bell

KIND_ORDER = ("quiz", "pick", "match", "sort", "states", "duel", "browse", "debate")

__all__ = [
    "KIND_ORDER",
    "get_catalog",
    "reload_catalog",
    "ActivitySession",
    "load_naturalization_questions",
    "load_colonies",
    "load_amendments",
    "load_quotes",
    "load_on_this_day",
    "load_timeline_events",
    "load_signers",
    "load_states",
    "load_debate",
    "load_source_links",
    "resolve_source",
    "today_events",
    "fair_day",
    "pavilions",
    "pavilion",
    "activities",
    "lanes_for_fair",
    "pavilions_for_lane",
    "activities_for_pavilion",
    "primary_activity_id",
    "pavilion_activity_menu",
    "activity_lane_pavilion",
    "fair_playbill",
    "normalize",
    "answer_matches",
    "pick_questions",
    "question_key",
    "score_pass_fail",
]

normalize = __import__("civics.scoring", fromlist=["normalize"]).normalize


def _cat():
    return get_catalog()


def load_naturalization_questions():
    return _cat().legacy_naturalization_pool()


def load_colonies():
    return [
        {
            "name": c["title"],
            "founded": c.get("meta", {}).get("founded"),
            "founder": c.get("meta", {}).get("founder", ""),
            "fact": c.get("body", ""),
            "context": c.get("context", ""),
            "source": c.get("source", ""),
        }
        for c in _cat().cards_for(pavilion="colonies", kind="browse")
    ]


def load_signers():
    return [
        {
            "name": c["title"],
            "state": c.get("subtitle", ""),
            "fact": c.get("body", ""),
            "context": c.get("context", ""),
            "source": c.get("source", ""),
        }
        for c in _cat().cards_for(pavilion="signers", kind="browse")
    ]


def load_amendments():
    return [
        {
            "number": c.get("meta", {}).get("number"),
            "year": c.get("meta", {}).get("year"),
            "summary": c.get("body", ""),
            "context": c.get("context", ""),
            "source": c.get("source", ""),
        }
        for c in _cat().cards_for(pavilion="amendments", kind="browse")
    ]


def load_quotes():
    return [
        {
            "quote": c.get("prompt") or c.get("body"),
            "person": c.get("answer"),
            "distractors": c.get("distractors", []),
            "context": c.get("context", ""),
        }
        for c in _cat().cards_for(pavilion="quotes", kind="match")
    ]


def load_states():
    return [
        {
            "name": c["title"],
            "capital": c.get("meta", {}).get("capital", ""),
            "order": c.get("meta", {}).get("order"),
            "admitted": c.get("meta", {}).get("admitted", ""),
            "fact": c.get("body", ""),
        }
        for c in _cat().cards_for(pavilion="states", kind="states")
    ]


def load_timeline_events():
    return [
        {"year": c.get("meta", {}).get("year"), "event": c.get("body", "")}
        for c in _cat().cards_for(pavilion="timeline", kind="sort")
    ]


def load_on_this_day():
    return _cat().raw.get("calendar", {})


def load_debate():
    topics = {}
    for c in _cat().cards_for(pavilion="debate"):
        if c.get("kind") == "browse" and c["title"].startswith("CONSTITUTIONAL DEBATE:"):
            topic_name = c["title"].replace("CONSTITUTIONAL DEBATE: ", "")
            topics[topic_name] = {"topic": topic_name, "exchanges": []}
    for c in _cat().cards_for(pavilion="debate", kind="debate"):
        topic = c.get("meta", {}).get("topic")
        if not topic:
            continue
        if topic not in topics:
            topics[topic] = {"topic": topic, "exchanges": []}
        topics[topic]["exchanges"].append(
            {
                "speaker": c["title"],
                "quote": c.get("body", "").strip('"'),
                "occasion": c.get("subtitle", "").split(" — ")[0] if " — " in c.get("subtitle", "") else c.get("subtitle", ""),
                "date": c.get("subtitle", "").split(" — ")[-1] if " — " in c.get("subtitle", "") else "",
                "citation": c.get("source", ""),
            }
        )
    return list(topics.values())


@lru_cache(maxsize=1)
def load_source_links() -> dict:
    """links.json: 'resolvers' map citation strings to URLs; 'more' feeds the Record Room."""
    path = data_dir() / "sources" / "links.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"resolvers": [], "more": []}


def resolve_source(source: str) -> dict | None:
    """Turn a card/citation source string into {label, url}, or None if unlinkable."""
    s = (source or "").strip()
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return {"label": urlparse(s).netloc, "url": s}
    low = s.lower()
    for r in load_source_links().get("resolvers", []):
        if r.get("match", "").lower() in low:
            return {"label": r["label"], "url": r["url"]}
    return None


def today_events():
    return _cat().today_events()


def fair_day():
    return _cat().fair_day()


def pavilions(lane: str | None = None, hidden: bool = False):
    pavs = _cat().pavilions
    if lane:
        pavs = [p for p in pavs if p.get("lane") == lane]
    if not hidden:
        pavs = [p for p in pavs if not p.get("hidden")]
    return pavs


def activities():
    return _cat().activities


def pavilion(pavilion_id: str) -> dict | None:
    return _cat().pavilion(pavilion_id)


def lanes_for_fair() -> list[dict]:
    """Visible fair lanes plus synthetic Record Room row (matches TUI fair map)."""
    visible = [ln for ln in _cat().lanes if not ln.get("hidden")]
    visible.append({"id": "_record_room", "label": "Record Room", "order": 99})
    return sorted(visible, key=lambda x: x.get("order", 99))


def pavilions_for_lane(lane_id: str) -> list[dict]:
    if lane_id == "_record_room":
        return [
            {
                "id": "_sources",
                "label": "Sources & further reading",
                "subtitle": "The Record Room",
                "default_tier": "show",
            }
        ]
    return [p for p in pavilions(hidden=False) if p.get("lane") == lane_id]


def activities_for_pavilion(pavilion_id: str) -> list[dict]:
    return [a for a in _cat().activities if a.get("pavilion") == pavilion_id]


def primary_activity_id(pavilion_id: str) -> str | None:
    acts = activities_for_pavilion(pavilion_id)
    if not acts:
        return None
    for act in acts:
        if act.get("primary"):
            return act["id"]
    for kind in KIND_ORDER:
        for act in acts:
            if act.get("kind") == kind:
                return act["id"]
    return acts[0]["id"]


def pavilion_activity_menu(pavilion_id: str) -> list[tuple[str, str, str]]:
    """(activity_id, label, kind) for pavilion sub-menus."""
    rows: list[tuple[str, str, str]] = []
    labels = {
        "amendment-quiz": "Amendment Quiz",
        "presidents-quiz": "Presidents Quiz",
        "numbers-quiz": "By the Numbers Quiz",
        "timeline-tap": "Timeline Sort (short)",
    }
    for act in activities_for_pavilion(pavilion_id):
        label = labels.get(act["id"], act["id"].replace("-", " ").title())
        rows.append((act["id"], label, act.get("kind", "")))
    return rows


def activity_lane_pavilion(activity_id: str) -> tuple[str, str]:
    act = _cat().activity(activity_id)
    if not act:
        return "", ""
    pavilion_id = act.get("pool_filter", {}).get("pavilion", act.get("pavilion", ""))
    pav = _cat().pavilion(pavilion_id)
    lane_id = pav.get("lane", "") if pav else ""
    return lane_id, pavilion_id


def fair_playbill() -> dict[str, str]:
    """Hero-band context for CLI banner — mirrors tui_art HeroContext fields."""
    import tui_art

    lines: dict[str, str] = {}
    day = fair_day()
    if day:
        title = day.get("title", "")
        exhibit = day.get("exhibit", "")
        theme = day.get("theme", "")
        lines["fair_day"] = f"{title} — {exhibit}" if exhibit else title
        num = tui_art.FAIR_DAY_NUMBERS.get(theme)
        if num:
            lines["number_line"] = f"{num[0]} · {num[1]}"
    lines["motto"] = random.choice(tui_art.MOTTOS)
    events = today_events()
    if events:
        lines["on_this_day"] = events[0]
    quotes = load_quotes()
    if quotes:
        lines["ticker"] = bell.ticker_plain(quotes)
    return lines


def pick_questions(pool, count, weighted_ids=None):
    """Legacy adapter — pool items use 'id' or 'card_id'."""
    key = "card_id" if pool and "card_id" in pool[0] else "id"
    if weighted_ids and pool and isinstance(weighted_ids[0], int):
        # legacy missed question ints → map to card ids
        weighted_ids = [f"nat-{i:03d}" for i in weighted_ids]
    return pick_items(pool, count, weighted_ids, id_key=key)


def question_key(q: dict) -> int | str:
    """Stable miss-tracking id for a quiz pool item."""
    return q.get("card_id", q["id"])
