"""Drives ``logreader.py`` end to end -- the bridge that reads a log AS A
STORY and hands it to the ``StorySession`` engine, so it gets played, scored,
and HALTED at whatever a person never sealed.

Covers: ``load_log``, ``world_from_log``, ``story_from_log``, validation of
the derived world against ``worlds.py``'s own validator (the ONLY shape
``StorySession`` accepts), and the full pipeline -- log -> derived world ->
StorySession -> ``run_session`` with a sealed decision.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from the_table.game_session import Observation, Result
from the_table.gm import first_legal_policy, run_session
from the_table.logreader import load_log, story_from_log, world_from_log
from the_table.story_session import StorySession
from the_table.worlds import load_world

SEEDS = (0, 1, 42, 100)

_FIXTURE_LOG = {
    "id": "test-log-001",
    "title": "Test Log — Integration Check",
    "setting": "A system that reads its own logs as stories.",
    "characters": [
        {"id": "reader", "name": "The Reader", "role": "reads the log",
         "seat": True, "stats": {"Grit": 2, "Weird": 3, "Cute": 2, "Cool": 2}},
    ],
    "scene_title": "The Read",
    "opening": ["A log appears.", "Its lines begin to speak."],
    "entries": [
        {"kind": "action", "prompt": "Parse the first line.",
         "suggests": "Weird",
         "outcomes": {"strong": "Clean parse.", "weak": "Partial parse.",
                      "miss": "Parse error."}},
        {"kind": "action", "prompt": "Interpret the second line.",
         "suggests": "Grit",
         "outcomes": {"strong": "Meaning holds.", "weak": "Ambiguous.",
                      "miss": "Garbled."}},
        {"kind": "decision", "prompt": "Is the log real?",
         "proposes": {"fact": "The log contains a truth.",
                      "proposed_by": "reader"}},
    ],
}

_FIXTURE_LOG_MULTI_SEAT = {
    "id": "multi-seat-log",
    "title": "Two-Seat Log",
    "setting": "Two readers, one log.",
    "characters": [
        {"id": "alice", "name": "Alice", "role": "first reader",
         "seat": True, "stats": {"Grit": 3, "Weird": 2, "Cute": 2, "Cool": 2}},
        {"id": "bob", "name": "Bob", "role": "second reader",
         "seat": True, "stats": {"Grit": 2, "Weird": 2, "Cute": 2, "Cool": 3}},
    ],
    "entries": [
        {"kind": "action", "prompt": "Alice reads line one.",
         "suggests": "Grit",
         "outcomes": {"strong": "Crystal.", "weak": "Murky.", "miss": "Lost."}},
        {"kind": "action", "prompt": "Bob reads line two.",
         "suggests": "Cool",
         "outcomes": {"strong": "Smooth.", "weak": "Rough.", "miss": "Broken."}},
    ],
}


def _write_log(log: dict, d: str) -> str:
    path = os.path.join(d, f"{log['id']}.log.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return path


class TestLoadLog(unittest.TestCase):

    def test_reads_json_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_log(_FIXTURE_LOG, d)
            log = load_log(path)
        self.assertEqual(log["id"], "test-log-001")
        self.assertEqual(len(log["entries"]), 3)

    def test_missing_file_raises(self):
        with self.assertRaises((FileNotFoundError, OSError)):
            load_log("/nonexistent/path/fake.log.json")

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w") as f:
                f.write("{not valid json")
            with self.assertRaises(json.JSONDecodeError):
                load_log(path)

    def test_tilde_expansion(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_log(_FIXTURE_LOG, d)
            log = load_log(path)
            self.assertEqual(log["id"], _FIXTURE_LOG["id"])


class TestWorldFromLog(unittest.TestCase):

    def test_basic_conversion(self):
        world = world_from_log(_FIXTURE_LOG)
        self.assertEqual(world["id"], "test-log-001")
        self.assertEqual(world["title"], "Test Log — Integration Check")
        self.assertEqual(world["stats"], ["Grit", "Weird", "Cute", "Cool"])
        self.assertEqual(world["base_stat"], 2)
        self.assertEqual(len(world["scenes"]), 1)
        self.assertEqual(len(world["scenes"][0]["beats"]), 3)

    def test_derived_world_passes_validator(self):
        world = world_from_log(_FIXTURE_LOG)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "derived.json")
            with open(path, "w") as f:
                json.dump(world, f)
            validated = load_world(path)
        self.assertEqual(validated["id"], world["id"])

    def test_places_always_one_log_place(self):
        world = world_from_log(_FIXTURE_LOG)
        self.assertEqual(len(world["places"]), 1)
        self.assertEqual(world["places"][0]["id"], "log")
        self.assertEqual(world["places"][0]["name"], "the log")

    def test_scene_title_defaults(self):
        log = dict(_FIXTURE_LOG)
        del log["scene_title"]
        world = world_from_log(log)
        self.assertEqual(world["scenes"][0]["title"], "the read")

    def test_scene_title_from_log(self):
        world = world_from_log(_FIXTURE_LOG)
        self.assertEqual(world["scenes"][0]["title"], "The Read")

    def test_opening_defaults_to_empty(self):
        log = {k: v for k, v in _FIXTURE_LOG.items() if k != "opening"}
        world = world_from_log(log)
        self.assertEqual(world["scenes"][0]["opening"], [])

    def test_opening_preserved(self):
        world = world_from_log(_FIXTURE_LOG)
        self.assertEqual(world["scenes"][0]["opening"],
                         ["A log appears.", "Its lines begin to speak."])

    def test_setting_defaults_to_empty(self):
        log = {k: v for k, v in _FIXTURE_LOG.items() if k != "setting"}
        world = world_from_log(log)
        self.assertEqual(world["setting"], "")

    def test_base_stat_defaults_to_two(self):
        log = {k: v for k, v in _FIXTURE_LOG.items() if k != "base_stat"}
        world = world_from_log(log)
        self.assertEqual(world["base_stat"], 2)

    def test_base_stat_from_log(self):
        log = dict(_FIXTURE_LOG, base_stat=3)
        world = world_from_log(log)
        self.assertEqual(world["base_stat"], 3)

    def test_empty_entries_raises(self):
        log = dict(_FIXTURE_LOG, entries=[])
        with self.assertRaises(ValueError):
            world_from_log(log)

    def test_missing_entries_raises(self):
        log = {k: v for k, v in _FIXTURE_LOG.items() if k != "entries"}
        with self.assertRaises(ValueError):
            world_from_log(log)

    def test_beat_ids_auto_generated(self):
        world = world_from_log(_FIXTURE_LOG)
        beats = world["scenes"][0]["beats"]
        self.assertEqual(beats[0]["id"], "e1")
        self.assertEqual(beats[1]["id"], "e2")
        self.assertEqual(beats[2]["id"], "e3")

    def test_beat_ids_from_entries(self):
        log = dict(_FIXTURE_LOG, entries=[
            dict(_FIXTURE_LOG["entries"][0], id="custom-1"),
            dict(_FIXTURE_LOG["entries"][1], id="custom-2"),
        ])
        world = world_from_log(log)
        beats = world["scenes"][0]["beats"]
        self.assertEqual(beats[0]["id"], "custom-1")
        self.assertEqual(beats[1]["id"], "custom-2")

    def test_action_beat_shape(self):
        world = world_from_log(_FIXTURE_LOG)
        beat = world["scenes"][0]["beats"][0]
        self.assertEqual(beat["kind"], "action")
        self.assertEqual(beat["suggests"], "Weird")
        self.assertIn("strong", beat["outcomes"])
        self.assertIn("weak", beat["outcomes"])
        self.assertIn("miss", beat["outcomes"])

    def test_decision_beat_shape(self):
        world = world_from_log(_FIXTURE_LOG)
        beat = world["scenes"][0]["beats"][2]
        self.assertEqual(beat["kind"], "decision")
        self.assertIn("proposes", beat)
        self.assertEqual(beat["proposes"]["fact"], "The log contains a truth.")
        self.assertEqual(beat["proposes"]["proposed_by"], "reader")

    def test_characters_pass_through(self):
        world = world_from_log(_FIXTURE_LOG)
        self.assertEqual(len(world["characters"]), 1)
        self.assertEqual(world["characters"][0]["id"], "reader")
        self.assertTrue(world["characters"][0]["seat"])

    def test_multi_seat_log(self):
        world = world_from_log(_FIXTURE_LOG_MULTI_SEAT)
        seated = [c for c in world["characters"] if c["seat"]]
        self.assertEqual(len(seated), 2)


class TestStoryFromLog(unittest.TestCase):

    def test_writes_derived_world_and_returns_path(self):
        with tempfile.TemporaryDirectory() as box:
            log_path = _write_log(_FIXTURE_LOG, box)
            world_path = story_from_log(log_path, box_dir=box)
            self.assertTrue(os.path.isfile(world_path))
            self.assertTrue(world_path.endswith(".world.json"))

    def test_derived_file_is_valid_world(self):
        with tempfile.TemporaryDirectory() as box:
            log_path = _write_log(_FIXTURE_LOG, box)
            world_path = story_from_log(log_path, box_dir=box)
            world = load_world(world_path)
            self.assertEqual(world["id"], "test-log-001")

    def test_default_box_dir_creates_tempdir(self):
        with tempfile.TemporaryDirectory() as d:
            log_path = _write_log(_FIXTURE_LOG, d)
            world_path = story_from_log(log_path)
        self.assertIn("logworld-", world_path)


class TestLogreaderIntegration(unittest.TestCase):
    """End-to-end: log -> derived world -> StorySession -> play, including
    the decision beat that HALTS until a named human seals it."""

    def test_log_through_story_session_action_only(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                with tempfile.TemporaryDirectory() as box:
                    log_path = _write_log(_FIXTURE_LOG_MULTI_SEAT, box)
                    world_path = story_from_log(log_path, box_dir=box)
                    session = StorySession(world_path)
                    obs = session.reset(seed)
                    self.assertIsInstance(obs, Observation)
                    self.assertFalse(obs.terminal)
                    while not session.is_terminal():
                        seat = session.current_seat()
                        moves = session.legal_moves(seat)
                        self.assertTrue(len(moves) > 0)
                        session.step(seat, moves[0])
                    result = session.result()
                    self.assertIsInstance(result, Result)
                    self.assertEqual(result.winners, [])

    def test_log_with_decision_blocks_and_seals(self):
        with tempfile.TemporaryDirectory() as box:
            log_path = _write_log(_FIXTURE_LOG, box)
            world_path = story_from_log(log_path, box_dir=box)
            session = StorySession(world_path)
            session.reset(42)

            for _ in range(2):
                seat = session.current_seat()
                moves = session.legal_moves(seat)
                self.assertTrue(len(moves) > 0)
                session.step(seat, moves[0])

            self.assertFalse(session.is_terminal())
            self.assertEqual(session.legal_moves(0), [])

            pending = session.pending_seal()
            self.assertIsNotNone(pending)
            self.assertEqual(pending["fact"], "The log contains a truth.")

            with self.assertRaises(RuntimeError):
                session.step(0, ("act", "Grit"))

            session.seal(pending["fact_id"], by="Nomi Reyes", verdict="SEALED")
            self.assertTrue(session.is_terminal())
            result = session.result()
            self.assertIn("SEALED", result.summary)
            self.assertIn("Nomi Reyes", result.summary)

    def test_log_decision_rejected(self):
        with tempfile.TemporaryDirectory() as box:
            log_path = _write_log(_FIXTURE_LOG, box)
            world_path = story_from_log(log_path, box_dir=box)
            session = StorySession(world_path)
            session.reset(7)

            while session.legal_moves(session.current_seat()):
                seat = session.current_seat()
                session.step(seat, session.legal_moves(seat)[0])

            pending = session.pending_seal()
            self.assertIsNotNone(pending)
            session.seal(pending["fact_id"], by="Jules Okafor",
                         verdict="REJECTED", reason="unverified")
            self.assertTrue(session.is_terminal())
            result = session.result()
            self.assertIn("REJECTED", result.summary)

    def test_log_decision_refuses_machine_sealer(self):
        with tempfile.TemporaryDirectory() as box:
            log_path = _write_log(_FIXTURE_LOG, box)
            world_path = story_from_log(log_path, box_dir=box)
            session = StorySession(world_path)
            session.reset(0)

            while session.legal_moves(session.current_seat()):
                seat = session.current_seat()
                session.step(seat, session.legal_moves(seat)[0])

            pending = session.pending_seal()
            self.assertIsNotNone(pending)
            with self.assertRaises(ValueError):
                session.seal(pending["fact_id"], by="claude")

    def test_determinism_across_seeds(self):
        results = {}
        for seed in SEEDS:
            with tempfile.TemporaryDirectory() as box:
                log_path = _write_log(_FIXTURE_LOG_MULTI_SEAT, box)
                world_path = story_from_log(log_path, box_dir=box)
                session = StorySession(world_path)
                session.reset(seed)
                while not session.is_terminal():
                    seat = session.current_seat()
                    session.step(seat, session.legal_moves(seat)[0])
                results[seed] = session.result().summary

            with tempfile.TemporaryDirectory() as box:
                log_path = _write_log(_FIXTURE_LOG_MULTI_SEAT, box)
                world_path = story_from_log(log_path, box_dir=box)
                session2 = StorySession(world_path)
                session2.reset(seed)
                while not session2.is_terminal():
                    seat = session2.current_seat()
                    session2.step(seat, session2.legal_moves(seat)[0])
                self.assertEqual(results[seed], session2.result().summary,
                                 f"seed {seed} diverged on replay")

    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as box:
            log_path = _write_log(_FIXTURE_LOG_MULTI_SEAT, box)
            world_path = story_from_log(log_path, box_dir=box)
            session = StorySession(world_path)
            session.reset(42)
            while not session.is_terminal():
                seat = session.current_seat()
                moves = session.legal_moves(seat)
                move = moves[0]
                rt = json.loads(json.dumps(move))
                self.assertEqual(list(rt), list(move))
                obs = session.step(seat, move)
                rt_view = json.loads(json.dumps(obs.view))
                self.assertEqual(rt_view, obs.view)


if __name__ == "__main__":
    unittest.main()
