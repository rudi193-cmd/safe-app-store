"""ActivitySession edge cases — stable prompts, timeout grading, speed-round totals."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from civics.catalog import Catalog
from civics.session import ActivitySession


def _mini_catalog(**extra: object) -> Catalog:
    base = {
        "activities": [
            {
                "id": "states-test",
                "kind": "states",
                "count": 1,
                "pool_filter": {"kind": "states"},
            },
            {
                "id": "speed-test",
                "kind": "quiz",
                "count": 5,
                "time_limit": 60,
                "pool_filter": {"kind": "quiz"},
            },
        ],
        "cards": [
            {
                "id": "st-tx",
                "kind": "states",
                "title": "Texas",
                "meta": {"capital": "Austin", "order": 28},
                "body": "Lone Star State",
            },
            {"id": "q1", "kind": "quiz", "prompt": "One?", "answers": ["one"]},
            {"id": "q2", "kind": "quiz", "prompt": "Two?", "answers": ["two"]},
            {"id": "q3", "kind": "quiz", "prompt": "Three?", "answers": ["three"]},
            {"id": "q4", "kind": "quiz", "prompt": "Four?", "answers": ["four"]},
            {"id": "q5", "kind": "quiz", "prompt": "Five?", "answers": ["five"]},
        ],
    }
    base.update(extra)
    return Catalog(base)


class SessionTests(unittest.TestCase):
    def test_states_prompt_stable_across_current_calls(self):
        catalog = _mini_catalog()
        session = ActivitySession("states-test", catalog=catalog)
        session._mode = "order"
        session._current = session._pool[0]
        first = session.current()
        second = session.current()
        self.assertEqual(first["prompt"], second["prompt"])
        self.assertIn("__th state", first["prompt"])

    def test_states_grade_matches_displayed_mode(self):
        catalog = _mini_catalog()
        session = ActivitySession("states-test", catalog=catalog)
        session._mode = "capital"
        session._current = session._pool[0]
        session.current()
        result = session.submit("Austin")
        self.assertTrue(result["correct"])

    def test_submit_after_timeout_does_not_crash(self):
        catalog = _mini_catalog()
        session = ActivitySession("speed-test", catalog=catalog)
        session.start_time = time.time() - 3600
        result = session.submit("one")
        self.assertTrue(result.get("timed_out"))
        self.assertTrue(result.get("done"))
        self.assertFalse(result.get("correct", True))

    def test_resolved_total_stops_at_attempted_on_timeout(self):
        catalog = _mini_catalog()
        session = ActivitySession("speed-test", catalog=catalog)
        session.score = 2
        session.index = 4
        session.start_time = time.time() - 3600
        self.assertEqual(session.resolved_total(), 4)
        summary = session.summary()
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["score"], 2)


if __name__ == "__main__":
    unittest.main()
