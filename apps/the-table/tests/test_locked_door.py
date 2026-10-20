"""The locked door: a catgrid board as a story beat. The seat solves it with
("grid", ...) moves; how it ends picks the outcome; hearts and earned hints
carry door to door. Each rule by the move or world it forbids.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest

from the_table import catgrid_adapter  # noqa: F401  (its path shim puts catgrid in reach)
from the_table.story_session import DOOR_HEARTS, StorySession, door_seed
from the_table.worlds import WorldError, available_worlds, load_world

from ._seal import human_seal

# Not in worlds/: the worlds index is pinned by a frozen, dated record
# (tests/fixtures/foreshadow-2026-10-16-exact.json, test_peaks), so a campaign
# with a door lives beside it, in campaigns/, and is played by path.
DOOR_WORLD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "campaigns", "locked-door.json")

from catgrid.board import address as at  # noqa: E402  (after the shim, on purpose)

BANK = [{"id": f"t:{i}", "question": f"Q{i}?", "answer": f"A{i}."} for i in range(6)]
WORDS = ["Filed."]


def address(i, n):
    """catgrid's own address: the row is the letter, the column the number."""
    return at(*divmod(i, n))


class Door(unittest.TestCase):
    def setUp(self):
        self.s = StorySession(DOOR_WORLD, door_bank=BANK, door_words=WORDS)
        self.s.reset(0)
        self.s.step(0, ("act", "Cool"))  # the stair; the door is next

    def door(self):
        return self.s._door  # the test's privileged look, to play right and wrong on purpose

    def answer(self):
        b = self.door().board
        return [address(i, b.n) for i in sorted(b.cats())]

    def wrong(self):
        b = self.door().board
        return next(address(i, b.n) for i in range(b.n * b.n) if i not in b.cats()
                    and self.door().cells[address(i, b.n)] == "")

    def solve(self):
        for a in self.answer():
            if self.door().cells[a] != "cat":
                obs = self.s.step(0, ("grid", "cat", a))
        return obs

    def lose(self):
        for _ in range(DOOR_HEARTS):
            if self.door() is None or self.door().hearts == 0:
                break
            obs = self.s.step(0, ("grid", "cat", self.wrong()))
        return obs


class TestAtTheDoor(Door):
    def test_only_grid_moves_are_legal_at_a_door(self):
        legal = self.s.legal_moves(0)
        self.assertTrue(legal)
        self.assertTrue(all(m[0] == "grid" for m in legal))

    def test_an_approach_is_refused_at_a_door(self):
        with self.assertRaisesRegex(ValueError, "a door takes"):
            self.s.step(0, ("act", "Grit"))

    def test_a_refused_grid_move_leaves_the_door_as_it_was(self):
        before = copy.deepcopy(self.door().state())
        with self.assertRaises(ValueError):
            self.s.step(0, ("grid", "cat", "Z9"))
        self.assertEqual(self.door().state(), before)

    def test_the_view_shows_the_door_and_carry_never_the_answer(self):
        view = self.s.observe(0).view
        self.assertEqual(view["beat_kind"], "puzzle")
        self.assertEqual(view["carry"], {"hearts": DOOR_HEARTS, "earned": 0})
        self.assertNotIn("solution", json.dumps(view))
        self.assertEqual(json.loads(json.dumps(view)), view)

    def test_the_door_is_dealt_from_the_seed_and_the_fact_id(self):
        self.assertEqual(self.door().seed, door_seed(0, "s1::door"))
        self.assertNotEqual(door_seed(0, "s1::door"), door_seed(0, "s2::door"))
        self.assertNotEqual(door_seed(0, "s1::door"), door_seed(1, "s1::door"))
        again = StorySession(DOOR_WORLD, door_bank=BANK, door_words=WORDS)
        again.reset(0)
        again.step(0, ("act", "Weird"))
        self.assertEqual(again._door.board.digest(), self.door().board.digest())

    def test_the_turn_stays_with_the_seat_until_the_door_ends(self):
        self.s.step(0, ("grid", "x", self.wrong()))
        self.assertEqual(self.s.observe(0).view["beat_id"], "door")


class TestHowTheDoorEnds(Door):
    def test_clean_is_strong_and_carries_full_hearts(self):
        before = self.s.result().scores["strong"]
        obs = self.solve()
        self.assertEqual(self.s.result().scores["strong"], before + 1)
        self.assertIn("without a sound", " ".join(obs.narration))
        self.assertEqual(obs.view["scene_id"], "s2")

    def test_a_heart_lost_is_weak_and_the_next_door_starts_with_what_is_left(self):
        self.s.step(0, ("grid", "cat", self.wrong()))
        obs = self.solve()
        self.assertIn("grudgingly", " ".join(obs.narration))
        human_seal(self.s)
        self.assertEqual(self.door().hearts, DOOR_HEARTS - 1)
        self.assertEqual(self.s.observe(0).view["carry"]["hearts"], DOOR_HEARTS - 1)

    def test_a_lost_door_is_a_miss_the_story_goes_on_and_one_heart_is_left(self):
        obs = self.lose()
        self.assertIn("tiles go dark", " ".join(obs.narration))
        self.assertEqual(obs.view["scene_id"], "s2")
        human_seal(self.s)
        self.assertEqual(self.door().hearts, 1)

    def test_an_earned_hint_carries_and_the_free_one_is_each_boards(self):
        self.s.step(0, ("grid", "trivia"))
        right = self.door().question["right"]
        self.s.step(0, ("grid", "hint"))  # spends the free one, not the earned
        self.s.step(0, ("grid", "answer", right))
        self.assertEqual(self.door().hints, {"free": 0, "earned": 1})
        self.solve()
        human_seal(self.s)
        self.assertEqual(self.door().hints, {"free": 1, "earned": 1})

    def test_the_decision_between_doors_still_blocks(self):
        self.solve()
        self.assertEqual(self.s.legal_moves(0), [])
        self.assertIsNone(self.door())
        human_seal(self.s)
        self.assertIsNotNone(self.door())


class TestTheCampaign(unittest.TestCase):
    def test_it_is_not_in_the_worlds_index(self):
        self.assertNotIn("locked-door", available_worlds())

    def test_it_plays_to_terminal_and_its_ledger_verifies(self):
        import shutil

        from ._record import RecordedSink

        box = tempfile.mkdtemp(prefix="the-table-door-")
        self.addCleanup(shutil.rmtree, box, True)
        game = StorySession(DOOR_WORLD, door_bank=BANK, door_words=WORDS)
        sink = RecordedSink(box_dir=box)
        try:
            game.reset(0)
            sink.open_session("locked-door", {"seed": 0, "seats": game.seats})
            for turn in range(500):
                if game.is_terminal():
                    break
                pending = game.pending_seal()
                if pending is not None:
                    human_seal(game)
                    sink.snapshot({"seal": pending["fact_id"], "by": "Some Human"})
                    continue
                move = game.legal_moves(0)[0]
                obs = game.step(0, move)
                sink.snapshot({"turn": turn, "move": list(move), "view": obs.view})
            self.assertTrue(game.is_terminal())
            r = game.result()
            sink.close_session({"winners": r.winners, "scores": r.scores, "summary": r.summary})
            self.assertTrue(sink.verify(), sink._last_verify_output)
        finally:
            sink.close()


class TestPuzzleBeatsValidate(unittest.TestCase):
    def world(self, puzzle):
        w = load_world(DOOR_WORLD)
        w["scenes"][0]["beats"][1]["puzzle"] = puzzle
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(w, f)
        self.addCleanup(os.remove, path)
        return path

    def test_a_puzzle_needs_its_size(self):
        with self.assertRaisesRegex(WorldError, "puzzle"):
            load_world(self.world({}))

    def test_sizes_are_positive_ints(self):
        for bad in ({"n": 0}, {"n": True}, {"n": "6"}, {"n": 9, "k": 0}):
            with self.assertRaisesRegex(WorldError, "positive int", msg=bad):
                load_world(self.world(bad))

    def test_the_shipped_world_validates(self):
        self.assertIn(6, [b["puzzle"]["n"] for sc in load_world(DOOR_WORLD)["scenes"]
                          for b in sc["beats"] if b["kind"] == "puzzle"])


if __name__ == "__main__":
    unittest.main()
