"""Run pavilion activities against the catalog."""

from __future__ import annotations

import random
import time
from typing import Any

from civics.catalog import Catalog, get_catalog
from civics.scoring import answer_matches, pick_choice, pick_items, score_pass_fail


class ActivitySession:
    """State machine for one run of an activity (quiz, pick round, sort, browse)."""

    def __init__(self, activity_id: str, catalog: Catalog | None = None):
        self.catalog = catalog or get_catalog()
        self.activity = self.catalog.activity(activity_id)
        if not self.activity:
            raise ValueError(f"Unknown activity: {activity_id}")
        self.activity_id = activity_id
        self.kind = self.activity["kind"]
        self.score = 0
        self.total = 0
        self.index = 0
        self.start_time = time.time()
        self.time_limit = self.activity.get("time_limit")
        self.pass_ratio = self.activity.get("pass_ratio", 0.6)
        self._pool: list[dict] = []
        self._current: dict | None = None
        self._shuffled: list[dict] = []
        self._mode: str | None = None  # states: capital | order
        self._options: list[str] = []
        self._browse_items: list[tuple] = []
        self._duel_players: list[str] = []
        self._duel_scores: dict[str, int] = {}
        self._reset_pool()

    def _reset_pool(self):
        act = self.activity
        pool = self.catalog.pool_for_activity(self.activity_id)
        count = act.get("count")
        weighted = None
        if act.get("weighted_misses"):
            import db

            weighted = db.missed_card_ids(limit=count or 10)
            if not weighted:
                weighted = [f"nat-{i:03d}" for i in db.missed_question_ids(limit=count or 10)]
        if self.kind in ("quiz", "pick", "match"):
            n = count if count else len(pool)
            self._pool = pick_items(pool, n, weighted_ids=weighted)
            self.total = len(self._pool)
        elif self.kind == "sort":
            n = count or 8
            sample = pick_items(pool, min(n, len(pool)))
            self._shuffled = sample[:]
            random.shuffle(self._shuffled)
            self.total = len(self._shuffled)
            self._pool = sample
        elif self.kind == "browse":
            self._browse_items = [
                (
                    c.get("title", ""),
                    c.get("subtitle", ""),
                    c.get("body", ""),
                    c.get("context", ""),
                    c.get("source", ""),
                )
                for c in pool
            ]
            self.total = len(self._browse_items)
        elif self.kind == "duel":
            n = count or 10
            legacy = self.catalog.legacy_naturalization_pool()
            self._pool = pick_items(legacy, n, id_key="card_id")
            self.total = len(self._pool)
        elif self.kind == "states":
            states = pool or self.catalog.cards_for(pavilion="states", kind="states")
            random.shuffle(states)
            self._pool = states[: act.get("count", 8)]
            self.total = len(self._pool)
        else:
            self._pool = pool
            self.total = len(pool)

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def timed_out(self) -> bool:
        return bool(self.time_limit and self.elapsed() > self.time_limit)

    def setup_duel(self, player1: str, player2: str) -> None:
        self._duel_players = [player1, player2]
        self._duel_scores = {player1: 0, player2: 0}

    def duel_player(self) -> str | None:
        if not self._duel_players:
            return None
        return self._duel_players[self.index % 2]

    # ── stepping ─────────────────────────────────────────────────────────────

    def current(self) -> dict[str, Any] | None:
        if self.kind == "browse":
            if self.index >= len(self._browse_items):
                return None
            t, sub, body, ctx, src = self._browse_items[self.index]
            return {"title": t, "subtitle": sub, "body": body, "context": ctx, "source": src}
        if self.index >= len(self._pool):
            return None
        if self.timed_out():
            return None
        card = self._pool[self.index]
        self._current = card
        if self.kind == "states":
            if self._current is not card:
                self._mode = random.choice(["capital", "order"])
            self._current = card
            return self._format_states_prompt(card)
        if self.kind == "pick":
            self._options = list(card.get("choices", []))
            random.shuffle(self._options)
            return {
                "prompt": card.get("prompt") or card.get("title"),
                "options": self._options,
                "card_id": card["id"],
            }
        if self.kind == "match":
            opts = [card["answer"]] + list(card.get("distractors", []))
            self._options = opts[:]
            random.shuffle(self._options)
            return {
                "quote": card.get("prompt") or card.get("body"),
                "options": self._options,
                "card_id": card["id"],
            }
        if self.kind in ("quiz", "duel"):
            if "legacy_id" in card:
                return {
                    "question": card.get("question", card.get("prompt")),
                    "answers": card.get("answers", []),
                    "category": card.get("category", ""),
                    "subcategory": card.get("subcategory", ""),
                    "card_id": card.get("card_id", card.get("id")),
                    "legacy_id": card.get("legacy_id"),
                }
            return {
                "question": card.get("prompt") or card.get("title"),
                "answers": card.get("answers", []),
                "category": card.get("category", ""),
                "subcategory": card.get("subcategory", ""),
                "card_id": card["id"],
            }
        if self.kind == "sort":
            return {
                "items": [(i + 1, e.get("body") or e.get("title")) for i, e in enumerate(self._shuffled)],
                "card_ids": [e["id"] for e in self._shuffled],
            }
        return card

    def _format_states_prompt(self, card: dict) -> dict:
        name = card.get("title") or card.get("name", "")
        if self._mode == "capital":
            capital = card.get("meta", {}).get("capital") or card.get("capital", "")
            return {
                "prompt": f"What is the capital of {name}?",
                "answers": [capital],
                "card_id": card["id"],
                "fact": card.get("body", card.get("fact", "")),
            }
        order = card.get("meta", {}).get("order") or card.get("order")
        return {
            "prompt": f"{name} was admitted as the __th state. (number)",
            "answers": [str(order)],
            "card_id": card["id"],
            "fact": card.get("body", card.get("fact", "")),
        }

    def submit(self, raw: str) -> dict[str, Any]:
        """Submit an answer for the current step. Returns result dict."""
        if self.kind == "browse":
            self.index += 1
            return {"advanced": True, "done": self.index >= self.total}
        if self.kind == "sort":
            return self._grade_sort(raw)
        if self.kind in ("pick", "match"):
            return self._grade_choice(raw)
        if self.kind in ("quiz", "duel", "states"):
            return self._grade_typed(raw)
        return {"error": "unsupported"}

    def _grade_typed(self, raw: str) -> dict:
        if self.timed_out():
            return {"correct": False, "done": True, "timed_out": True}
        if self.index >= len(self._pool):
            return {"correct": False, "done": True}
        card = self._pool[self.index]
        if self.kind == "states":
            expected = self._format_states_prompt(card).get("answers", [])
        else:
            expected = card.get("answers", [])
        correct = answer_matches(raw, expected)
        if correct:
            self.score += 1
            if self.kind == "duel" and self._duel_players:
                self._duel_scores[self.duel_player()] += 1
        self.index += 1
        return {
            "correct": correct,
            "expected": expected,
            "fact": card.get("body") or card.get("fact", ""),
            "card_id": card.get("card_id", card.get("id")),
            "done": self.index >= self.total or self.timed_out(),
        }

    def _grade_choice(self, raw: str) -> dict:
        card = self._pool[self.index]
        pick = pick_choice(raw, self._options)
        if self.kind == "match":
            correct = pick == card.get("answer")
        else:
            correct = pick == card.get("answer") or pick in card.get("answers", [])
        if correct:
            self.score += 1
        self.index += 1
        return {
            "correct": correct,
            "expected": card.get("answer") or card.get("answers"),
            "person": card.get("answer"),
            "card_id": card["id"],
            "done": self.index >= self.total,
        }

    def _grade_sort(self, raw: str) -> dict:
        correct_order = sorted(
            range(len(self._shuffled)),
            key=lambda i: self._shuffled[i].get("meta", {}).get("year", self._shuffled[i].get("year", 0)),
        )
        try:
            user_order = [int(x) - 1 for x in raw.split()]
        except ValueError:
            user_order = []
        self.score = sum(1 for a, b in zip(user_order, correct_order) if a == b)
        self.total = len(self._shuffled)
        self.index = self.total
        ordered = [
            {
                "year": self._shuffled[i].get("meta", {}).get("year", self._shuffled[i].get("year")),
                "event": self._shuffled[i].get("body") or self._shuffled[i].get("title"),
            }
            for i in correct_order
        ]
        return {
            "correct": self.score == self.total,
            "score": self.score,
            "total": self.total,
            "ordered": ordered,
            "done": True,
        }

    def resolved_total(self) -> int:
        """Questions that count toward pass/fail (speed round stops early on timeout)."""
        if self.timed_out():
            return min(self.index, len(self._pool))
        return self.total

    def passed(self) -> bool:
        total = self.resolved_total()
        if not total:
            return False
        return score_pass_fail(self.score, total, self.pass_ratio)

    def summary(self) -> dict:
        total = self.resolved_total()
        return {
            "activity_id": self.activity_id,
            "kind": self.kind,
            "score": self.score,
            "total": total,
            "elapsed_s": self.elapsed(),
            "passed": self.passed(),
            "duel_scores": dict(self._duel_scores) if self._duel_scores else None,
        }
