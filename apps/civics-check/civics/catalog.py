"""Load and query the compiled civics catalog."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"


class Catalog:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.version = raw.get("version", 1)
        self.lanes: list[dict] = raw.get("lanes", [])
        self.pavilions: list[dict] = raw.get("pavilions", [])
        self.activities: list[dict] = raw.get("activities", [])
        self.cards: list[dict] = raw.get("cards", [])
        self._cards_by_id = {c["id"]: c for c in self.cards}
        self._activities_by_id = {a["id"]: a for a in self.activities}
        self._pavilions_by_id = {p["id"]: p for p in self.pavilions}

    def activity(self, activity_id: str) -> dict | None:
        return self._activities_by_id.get(activity_id)

    def pavilion(self, pavilion_id: str) -> dict | None:
        return self._pavilions_by_id.get(pavilion_id)

    def card(self, card_id: str) -> dict | None:
        return self._cards_by_id.get(card_id)

    def cards_for(
        self,
        *,
        pavilion: str | None = None,
        lane: str | None = None,
        tier: str | None = None,
        kind: str | None = None,
        tag: str | None = None,
    ) -> list[dict]:
        out = self.cards
        if pavilion:
            out = [c for c in out if c.get("pavilion") == pavilion]
        if lane:
            out = [c for c in out if c.get("lane") == lane]
        if tier:
            out = [c for c in out if tier in c.get("tiers", [c.get("tier", "know")])]
        if kind:
            out = [c for c in out if c.get("kind") == kind]
        if tag:
            out = [c for c in out if tag in c.get("tags", [])]
        return out

    def pool_for_activity(self, activity_id: str) -> list[dict]:
        act = self.activity(activity_id)
        if not act:
            return []
        filt = act.get("pool_filter", {})
        return self.cards_for(
            pavilion=filt.get("pavilion"),
            lane=filt.get("lane"),
            tier=filt.get("tier"),
            kind=filt.get("kind"),
            tag=filt.get("tag"),
        )

    def today_events(self) -> list[str]:
        key = date.today().strftime("%m-%d")
        cal = self.raw.get("calendar", {})
        return list(cal.get(key, []))

    def fair_day(self) -> dict | None:
        days = self.raw.get("fair_schedule", [])
        if not days:
            return None
        today = date.today()
        for entry in days:
            if entry.get("month") == today.month and entry.get("day") == today.day:
                return entry
        # Freedom 250 window: June 25 – July 10, 2026 metaphor — cycle by day-of-year
        doy = today.timetuple().tm_yday
        return days[doy % len(days)]

    def legacy_naturalization_pool(self) -> list[dict]:
        """Shape expected by older CLI/TUI quiz loops."""
        pool = []
        for c in self.cards_for(pavilion="naturalization", kind="quiz"):
            pool.append(
                {
                    "id": c.get("legacy_id", c["id"]),
                    "category": c.get("category", ""),
                    "subcategory": c.get("subcategory", ""),
                    "question": c.get("prompt") or c.get("title", ""),
                    "answers": c.get("answers", []),
                    "context": c.get("context", ""),
                    "related_fact": c.get("body", ""),
                    "date": c.get("date", ""),
                    "card_id": c["id"],
                }
            )
        pool.sort(key=lambda q: int(q["id"]) if str(q["id"]).isdigit() else q["id"])
        return pool


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"Missing {CATALOG_PATH}. Run: python3 scripts/build_catalog.py"
        )
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return Catalog(json.load(f))


def reload_catalog() -> Catalog:
    get_catalog.cache_clear()
    return get_catalog()
