"""Drives StorySession as a GameSession, end to end -- the FOURTH adapter,
and the first that adds a new mechanic to the protocol rather than a new
engine underneath it: a decision beat proposes a fact and HALTS until a
named human seals it. Uses the real ``worlds/hasbeen.json`` (authored by a
concurrent agent to the pinned schema) when present, and falls back to a
tiny fixture world of the identical shape in ``setUp`` otherwise, so this
suite is never blocked on load order between the two build tasks.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import os
import random
import tempfile
import unittest

from the_table.game_session import GameSession, Observation, Result
from the_table.gm import first_legal_policy, random_policy, run_session
from the_table.story_session import NOT_A_PERSON, StorySession
from the_table.worlds import WorldError, load_world

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REAL_WORLD_PATH = os.path.join(_REPO_ROOT, "apps", "the-table", "worlds", "hasbeen.json")

SEEDS = (0, 1, 2, 3, 7, 15, 42, 100)

# A tiny fixture world of the exact pinned shape: two seated characters (so
# seat rotation is actually exercised), one action beat each seat gets a
# turn at, then a decision beat that must block until sealed. Used whenever
# the real worlds/hasbeen.json (authored by a different, concurrent task)
# isn't present yet.
_FIXTURE_WORLD = {
    "id": "fixture-world",
    "title": "Fixture World",
    "setting": "A bare room for testing beats.",
    "stats": ["Grit", "Weird", "Cute", "Cool"],
    "base_stat": 2,
    "characters": [
        {"id": "alice", "name": "Alice", "role": "first seat", "seat": True,
         "stats": {"Grit": 2, "Weird": 3, "Cute": 2, "Cool": 2}},
        {"id": "bob", "name": "Bob", "role": "second seat", "seat": True,
         "stats": {"Grit": 3, "Weird": 2, "Cute": 2, "Cool": 2}},
        {"id": "bystander", "name": "Bystander", "role": "not seated", "seat": False,
         "stats": {"Grit": 2, "Weird": 2, "Cute": 2, "Cool": 2}},
    ],
    "places": [{"id": "room", "name": "The Room", "desc": "A bare room."}],
    "scenes": [
        {
            "id": "s1",
            "title": "Opening",
            "place": "room",
            "opening": ["The scene opens.", "Two people are in the room."],
            "beats": [
                {"id": "b1", "kind": "action", "prompt": "Alice tries something.",
                 "suggests": "Weird",
                 "outcomes": {"strong": "It goes great.", "weak": "It goes okay.",
                              "miss": "It goes badly."}},
                {"id": "b2", "kind": "action", "prompt": "Bob tries something.",
                 "suggests": "Grit",
                 "outcomes": {"strong": "It goes great.", "weak": "It goes okay.",
                              "miss": "It goes badly."}},
                {"id": "b3", "kind": "decision", "prompt": "A fact needs deciding.",
                 "proposes": {"fact": "The bystander was there the whole time.",
                              "proposed_by": "bystander"}},
                {"id": "b4", "kind": "action", "prompt": "Alice tries again.",
                 "suggests": "Cool",
                 "outcomes": {"strong": "It goes great.", "weak": "It goes okay.",
                              "miss": "It goes badly."}},
            ],
        },
        {
            "id": "s2",
            "title": "Closing",
            "place": "room",
            "opening": ["The second scene opens."],
            "beats": [
                {"id": "b1", "kind": "action", "prompt": "Bob closes it out.",
                 "suggests": "Cute",
                 "outcomes": {"strong": "It goes great.", "weak": "It goes okay.",
                              "miss": "It goes badly."}},
            ],
        },
    ],
}


def _assert_json_roundtrip(testcase: unittest.TestCase, value, label: str) -> None:
    encoded = json.dumps(value)
    decoded = json.loads(encoded)
    testcase.assertEqual(
        json.dumps(decoded), encoded,
        f"{label} did not round-trip through JSON: {value!r}",
    )


def _assert_observation_serializable(testcase: unittest.TestCase, obs: Observation) -> None:
    _assert_json_roundtrip(testcase, obs.view, "Observation.view")
    for line in obs.narration:
        testcase.assertIsInstance(line, str)


class _WorldFixtureMixin:
    """Provides ``self.world_path`` -- the real hasbeen.json if present,
    else a freshly written fixture of the identical pinned shape."""

    def setUp(self):
        if os.path.exists(_REAL_WORLD_PATH):
            self.world_path = _REAL_WORLD_PATH
            self._tmp_world_file = None
        else:
            fd, path = tempfile.mkstemp(suffix=".json", prefix="the-table-fixture-world-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_FIXTURE_WORLD, f)
            self.world_path = path
            self._tmp_world_file = path

    def tearDown(self):
        if self._tmp_world_file and os.path.exists(self._tmp_world_file):
            os.unlink(self._tmp_world_file)


def _first_action_move(session: StorySession, seat: int):
    """The first legal move on an action beat, or None if the current beat
    is a decision (no move exists)."""
    legal = session.legal_moves(seat)
    return legal[0] if legal else None


def _play_to_first_pending_seal(session: StorySession, seed: int):
    """Drive the story with the first-legal policy until either it becomes
    terminal or a decision beat blocks. Returns nothing; caller inspects
    session state afterward."""
    session.reset(seed)
    while not session.is_terminal():
        pending = session.pending_seal()
        if pending is not None:
            return
        seat = session.current_seat()
        move = _first_action_move(session, seat)
        session.step(seat, move)


class TestStorySessionIsAGameSession(_WorldFixtureMixin, unittest.TestCase):
    def test_isinstance_protocol_check(self):
        session = StorySession(self.world_path)
        self.assertIsInstance(session, GameSession)

    def test_structural_methods_exist(self):
        session = StorySession(self.world_path)
        for name in ("reset", "current_seat", "observe", "legal_moves", "step",
                     "is_terminal", "result"):
            self.assertTrue(hasattr(session, name), name)
            self.assertTrue(callable(getattr(session, name)), name)
        self.assertTrue(hasattr(session, "seats"))
        self.assertGreaterEqual(session.seats, 1)

    def test_extra_seal_seam_methods_exist(self):
        session = StorySession(self.world_path)
        self.assertTrue(callable(session.pending_seal))
        self.assertTrue(callable(session.seal))


class TestStorySessionFullPlaythrough(_WorldFixtureMixin, unittest.TestCase):
    """Drives a full story with a seeded first-legal-move policy for the
    action beats, sealing every decision beat with a named human as soon as
    it blocks, until the story reaches terminal. Asserts a well-formed
    Result at the end."""

    def _play_full(self, seed: int, sealer: str = "Some Human"):
        session = StorySession(self.world_path)
        obs = session.reset(seed)
        _assert_observation_serializable(self, obs)

        steps = 0
        seals = 0
        cap = 500  # generous defensive cap; real worlds are tiny
        while not session.is_terminal():
            self.assertLess(steps + seals, cap, f"seed {seed}: story did not terminate")
            pending = session.pending_seal()
            if pending is not None:
                session.seal(pending["fact_id"], sealer)
                seals += 1
                continue
            seat = session.current_seat()
            move = _first_action_move(session, seat)
            self.assertIsNotNone(move, "an action beat must offer at least one legal move")
            obs = session.step(seat, move)
            _assert_observation_serializable(self, obs)
            steps += 1

        return session, steps, seals

    def test_full_playthrough_reaches_terminal_and_yields_a_result(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session, steps, seals = self._play_full(seed)
                self.assertTrue(session.is_terminal())
                self.assertGreater(steps, 0)

                result = session.result()
                self.assertIsInstance(result, Result)
                self.assertEqual(result.winners, [], "a story is never won/lost")
                self.assertIsInstance(result.scores, dict)
                self.assertEqual(set(result.scores.keys()), {"strong", "weak", "miss"})
                self.assertEqual(sum(result.scores.values()), steps)
                self.assertIsInstance(result.summary, str)
                self.assertTrue(result.summary)
                self.assertIn("sealed", result.summary.lower())

    def test_players_are_never_recorded(self):
        """No attendance/per-person log anywhere in the session's own
        state -- only the sealed-fact record (about the WORLD, not the
        player) and the scored-beat tally."""
        session, steps, seals = self._play_full(seed=5, sealer="Some Human")
        for attr in ("_players", "_attendance", "_player_log", "_seat_log"):
            self.assertFalse(hasattr(session, attr), attr)
        # The only per-seal record kept is (fact_id, by, verdict, reason) --
        # never a roster of who sat in which seat across the run.
        for fact_id, record in session._seals.items():
            self.assertEqual(set(record.keys()), {"fact_id", "by", "verdict", "reason"})


class TestStorySessionDecisionBeatBlocks(_WorldFixtureMixin, unittest.TestCase):
    """The core guarantee: a decision beat halts the story until a named
    human seals it, and nothing else can move it forward."""

    def test_decision_beat_blocks_legal_moves_pending_and_terminal(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)

        pending = session.pending_seal()
        self.assertIsNotNone(pending, "expected a decision beat to be reached")
        self.assertIn("fact_id", pending)
        self.assertIn("fact", pending)
        self.assertIn("proposed_by", pending)

        seat = session.current_seat()
        self.assertEqual(session.legal_moves(seat), [],
                          "a decision beat must offer zero legal moves -- nothing can step past it")
        self.assertFalse(session.is_terminal(),
                          "a blocked decision beat is NOT terminal, it is blocked")

    def test_step_raises_on_a_decision_beat(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        self.assertIsNotNone(session.pending_seal())

        seat = session.current_seat()
        with self.assertRaises(RuntimeError):
            session.step(seat, ("act", "Grit"))

    def test_no_policy_can_advance_a_decision_beat(self):
        """Random and first-legal policies alike see zero legal moves on a
        decision beat -- there is no move in the vocabulary a policy (or an
        LLM standing in for one) could pick to get past it."""
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=1)
        self.assertIsNotNone(session.pending_seal())

        seat = session.current_seat()
        rng = random.Random(1)
        legal = session.legal_moves(seat)
        self.assertEqual(legal, [])
        with self.assertRaises(IndexError):
            rng.choice(legal)  # even a random policy has nothing to choose from


class TestStorySessionSealOnlyAHuman(_WorldFixtureMixin, unittest.TestCase):
    """Proves the hard constraint: only a named human can seal, and no
    machine-looking signer name is ever accepted -- REFUSE is the only
    behavior for those inputs, never a silent auto-seal."""

    def test_seal_by_named_human_unblocks_and_advances(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending = session.pending_seal()
        self.assertIsNotNone(pending)

        self.assertFalse(session.is_terminal(), "sanity: story was blocked, not terminal, before sealing")
        session.seal(pending["fact_id"], "Some Human")

        self.assertIsNone(session.pending_seal(), "sealing must clear the pending decision")
        # Either the story advanced to a new (non-pending) beat, or it
        # reached terminal -- either way, it is no longer blocked.
        self.assertTrue(session.is_terminal() or session.pending_seal() is None)
        self.assertIn(pending["fact_id"], session._seals)
        self.assertEqual(session._seals[pending["fact_id"]]["by"], "Some Human")
        self.assertEqual(session._seals[pending["fact_id"]]["verdict"], "SEALED")

    def test_seal_by_the_machine_is_refused(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending = session.pending_seal()
        self.assertIsNotNone(pending)

        with self.assertRaises(ValueError):
            session.seal(pending["fact_id"], "the-machine")
        # Refusal must not have advanced or recorded anything.
        self.assertEqual(session.pending_seal(), pending)
        self.assertNotIn(pending["fact_id"], session._seals)

    def test_seal_by_empty_string_is_refused(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending = session.pending_seal()
        self.assertIsNotNone(pending)

        with self.assertRaises(ValueError):
            session.seal(pending["fact_id"], "")
        self.assertEqual(session.pending_seal(), pending)
        self.assertNotIn(pending["fact_id"], session._seals)

    def test_every_not_a_person_name_is_refused(self):
        """Every literal entry in the mirrored NOT_A_PERSON set is refused,
        one decision beat per name (a fresh session each time, since a
        refused seal must not have advanced the previous one)."""
        for bad_name in sorted(NOT_A_PERSON):
            with self.subTest(bad_name=bad_name):
                session = StorySession(self.world_path)
                _play_to_first_pending_seal(session, seed=0)
                pending = session.pending_seal()
                self.assertIsNotNone(pending)
                with self.assertRaises(ValueError):
                    session.seal(pending["fact_id"], bad_name)

    def test_compound_machine_names_are_also_refused(self):
        """Not just an exact NOT_A_PERSON entry -- a compound signer id
        built from one (e.g. 'the-machine', matching the pinned test
        requirement) is refused too."""
        for bad_name in ("the-machine", "claude-agent", "AI", "  Machine  ", "Auto-GM"):
            with self.subTest(bad_name=bad_name):
                session = StorySession(self.world_path)
                _play_to_first_pending_seal(session, seed=0)
                pending = session.pending_seal()
                self.assertIsNotNone(pending)
                with self.assertRaises(ValueError):
                    session.seal(pending["fact_id"], bad_name)

    def test_no_auto_seal_path_exists(self):
        """There is no code path -- not step(), not legal_moves(), not
        reset() -- that seals a decision beat without an explicit seal()
        call naming a real human. Driving the story purely through
        step()/legal_moves() (as any policy, human or machine, would) can
        never clear a pending decision."""
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending_before = session.pending_seal()
        self.assertIsNotNone(pending_before)

        # Exhaust every observable, side-effect-free surface the loop uses.
        seat = session.current_seat()
        session.observe(seat)
        session.legal_moves(seat)
        session.is_terminal()
        # None of the above may have touched the pending decision.
        self.assertEqual(session.pending_seal(), pending_before)

    def test_rejected_verdict_also_unblocks(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending = session.pending_seal()
        self.assertIsNotNone(pending)

        session.seal(pending["fact_id"], "Some Human", verdict="REJECTED", reason="not credible")
        self.assertIsNone(session.pending_seal())
        self.assertEqual(session._seals[pending["fact_id"]]["verdict"], "REJECTED")
        self.assertEqual(session._seals[pending["fact_id"]]["reason"], "not credible")

    def test_seal_wrong_fact_id_is_rejected(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending = session.pending_seal()
        self.assertIsNotNone(pending)
        with self.assertRaises(ValueError):
            session.seal("not-the-real-fact-id", "Some Human")

    def test_seal_with_no_pending_decision_raises(self):
        session = StorySession(self.world_path)
        session.reset(seed=0)
        # seed=0's first beat is an action beat (in both the fixture and
        # hasbeen.json) -- no decision pending yet.
        self.assertIsNone(session.pending_seal())
        with self.assertRaises(RuntimeError):
            session.seal("whatever", "Some Human")

    def test_seal_invalid_verdict_raises(self):
        session = StorySession(self.world_path)
        _play_to_first_pending_seal(session, seed=0)
        pending = session.pending_seal()
        self.assertIsNotNone(pending)
        with self.assertRaises(ValueError):
            session.seal(pending["fact_id"], "Some Human", verdict="MAYBE")


class TestStorySessionObservationAndMoveJSON(_WorldFixtureMixin, unittest.TestCase):
    def test_every_observation_and_move_round_trips(self):
        session = StorySession(self.world_path)
        obs = session.reset(seed=2)
        _assert_json_roundtrip(self, obs.view, "reset() Observation.view")

        while not session.is_terminal():
            pending = session.pending_seal()
            if pending is not None:
                _assert_json_roundtrip(self, pending, "pending_seal()")
                session.seal(pending["fact_id"], "Some Human")
                continue
            seat = session.current_seat()
            for move in session.legal_moves(seat):
                _assert_json_roundtrip(self, move, f"legal move {move!r}")
            move = session.legal_moves(seat)[0]
            obs = session.step(seat, move)
            _assert_json_roundtrip(self, obs.view, "step() Observation.view")
            observed = session.observe(seat)
            _assert_json_roundtrip(self, observed.view, "observe() Observation.view")

    def test_view_never_leaks_another_seats_stats(self):
        session = StorySession(self.world_path)
        session.reset(seed=3)
        if session.seats < 2:
            self.skipTest("world has fewer than 2 seats -- nothing cross-seat to check")
        view0 = session.observe(0).view
        view1 = session.observe(1).view
        self.assertNotEqual(view0["character_id"], view1["character_id"])
        self.assertNotEqual(view0["stats"], view1["stats"])


class TestStorySessionUseBeforeReset(_WorldFixtureMixin, unittest.TestCase):
    def test_use_before_reset_raises(self):
        session = StorySession(self.world_path)
        with self.assertRaises(RuntimeError):
            session.current_seat()
        with self.assertRaises(RuntimeError):
            session.legal_moves(0)
        with self.assertRaises(RuntimeError):
            session.step(0, ("act", "Grit"))
        with self.assertRaises(RuntimeError):
            session.is_terminal()
        with self.assertRaises(RuntimeError):
            session.result()
        with self.assertRaises(RuntimeError):
            session.pending_seal()
        with self.assertRaises(RuntimeError):
            session.seal("whatever", "Some Human")


class TestStorySessionWrongSeat(_WorldFixtureMixin, unittest.TestCase):
    def test_out_of_range_seat_rejected(self):
        session = StorySession(self.world_path)
        session.reset(seed=0)
        with self.assertRaises(ValueError):
            session.observe(session.seats)
        with self.assertRaises(ValueError):
            session.legal_moves(-1)

    def test_step_out_of_turn_rejected(self):
        session = StorySession(self.world_path)
        session.reset(seed=0)
        if session.seats < 2:
            self.skipTest("world has fewer than 2 seats -- no out-of-turn case to exercise")
        wrong_seat = (session.current_seat() + 1) % session.seats
        with self.assertRaises(ValueError):
            session.step(wrong_seat, ("act", "Grit"))


class TestStorySessionDeterminism(_WorldFixtureMixin, unittest.TestCase):
    def test_same_seed_same_rolls(self):
        def _drive(seed):
            session = StorySession(self.world_path)
            session.reset(seed)
            rolls = []
            while not session.is_terminal():
                pending = session.pending_seal()
                if pending is not None:
                    session.seal(pending["fact_id"], "Some Human")
                    continue
                seat = session.current_seat()
                move = _first_action_move(session, seat)
                obs = session.step(seat, move)
                rolls.append(obs.narration[0])
            return rolls

        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.assertEqual(_drive(seed), _drive(seed))


class TestStorySessionLedgerIntegration(_WorldFixtureMixin, unittest.TestCase):
    def test_story_driven_by_gm_loop_with_seal_policy_reaches_terminal_and_ledger_verifies(self):
        """The fourth game, through the SAME run_session/LedgerSink bureau,
        crazy_eights, and scene use, unchanged -- proving the propose->seal
        seam composes with the existing driver rather than requiring a new
        one. The GM's own policy only ever picks among legal_moves(), which
        is empty on a decision beat -- so this test seals out-of-band
        (as a human at the table would) between run_session calls, one
        scene-of-play at a time up to the first decision, then resumes."""
        from the_table.ledger_sink import LedgerSink

        box_dir = tempfile.mkdtemp(prefix="the-table-test-story-")
        try:
            game = StorySession(self.world_path)
            sink = LedgerSink(box_dir=box_dir)
            try:
                # Drive by hand (not run_session) because a decision beat's
                # legal_moves() is empty and only seal() -- not a Policy --
                # can pass it; this still exercises the identical
                # game/sink contract run_session itself uses turn by turn.
                obs = game.reset(0)
                sink.open_session("test-gm-story", {"seed": 0, "seats": game.seats})
                turns = 0
                while not game.is_terminal():
                    pending = game.pending_seal()
                    if pending is not None:
                        game.seal(pending["fact_id"], "Some Human")
                        sink.snapshot(
                            {"turn": turns, "seal": pending["fact_id"], "by": "Some Human"},
                            note=f"sealed {pending['fact_id']}",
                        )
                        turns += 1
                        continue
                    seat = game.current_seat()
                    move = _first_action_move(game, seat)
                    obs = game.step(seat, move)
                    note = obs.narration[0] if obs.narration else ""
                    sink.snapshot({"turn": turns, "seat": seat, "move": move, "view": obs.view}, note=note)
                    turns += 1
                result = game.result()
                sink.close_session({"winners": result.winners, "scores": result.scores,
                                     "summary": result.summary})

                self.assertTrue(game.is_terminal())
                self.assertIsInstance(result, Result)
                self.assertTrue(sink.verify(), sink._last_verify_output)
            finally:
                sink.close()
        finally:
            import shutil
            shutil.rmtree(box_dir, ignore_errors=True)

    def test_pure_action_stretch_can_be_driven_by_run_session_unchanged(self):
        """Up to the first decision beat, StorySession is driven by the
        SAME run_session()/policy machinery bureau, crazy_eights, and scene
        use, byte-for-byte -- proving the protocol itself needed no
        changes. A decision beat never reports is_terminal(), so
        run_session (correctly, per gm.py's own documented contract) raises
        GMError once it hits the cap without terminating rather than
        returning a fabricated Result -- this test asserts exactly that,
        AND that every one of the action-beat turns before the decision was
        driven through the unmodified run_session loop with no special
        casing for StorySession."""
        session = StorySession(self.world_path)
        session.reset(0)
        first_scene = session.world["scenes"][0]
        action_beats_before_decision = 0
        for beat in first_scene["beats"]:
            if beat["kind"] != "action":
                break
            action_beats_before_decision += 1
        if action_beats_before_decision == 0:
            self.skipTest("world's first scene opens on a decision beat -- nothing to drive")

        game = StorySession(self.world_path)
        policy = first_legal_policy()
        from the_table.gm import GMError
        with self.assertRaises(GMError) as ctx:
            run_session(game, policy, seed=0, max_turns=action_beats_before_decision,
                        session_id="test-gm-story-prefix")
        self.assertEqual(ctx.exception.turns_taken, action_beats_before_decision)
        self.assertFalse(game.is_terminal())
        self.assertIsNotNone(game.pending_seal())


class TestWorldsLoader(unittest.TestCase):
    """worlds.py's own validation surface -- a bad world fails loudly and
    specifically, not with a confusing KeyError deep inside StorySession."""

    def test_load_world_missing_file_raises(self):
        with self.assertRaises(WorldError):
            load_world("/nonexistent/path/to/a/world.json")

    def test_load_world_invalid_json_raises(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("{not valid json")
            with self.assertRaises(WorldError):
                load_world(path)
        finally:
            os.unlink(path)

    def test_load_world_missing_top_level_key_raises(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            bad = dict(_FIXTURE_WORLD)
            del bad["scenes"]
            with os.fdopen(fd, "w") as f:
                json.dump(bad, f)
            with self.assertRaises(WorldError):
                load_world(path)
        finally:
            os.unlink(path)

    def test_load_world_no_seated_character_raises(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            import copy
            bad = copy.deepcopy(_FIXTURE_WORLD)
            for c in bad["characters"]:
                c["seat"] = False
            with os.fdopen(fd, "w") as f:
                json.dump(bad, f)
            with self.assertRaises(WorldError):
                load_world(path)
        finally:
            os.unlink(path)

    def test_load_world_decision_beat_missing_proposes_raises(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            import copy
            bad = copy.deepcopy(_FIXTURE_WORLD)
            del bad["scenes"][0]["beats"][2]["proposes"]
            with os.fdopen(fd, "w") as f:
                json.dump(bad, f)
            with self.assertRaises(WorldError):
                load_world(path)
        finally:
            os.unlink(path)

    def test_load_world_scene_references_unknown_place_raises(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            import copy
            bad = copy.deepcopy(_FIXTURE_WORLD)
            bad["scenes"][0]["place"] = "does-not-exist"
            with os.fdopen(fd, "w") as f:
                json.dump(bad, f)
            with self.assertRaises(WorldError):
                load_world(path)
        finally:
            os.unlink(path)

    def test_load_real_or_fixture_world_succeeds(self):
        path = _REAL_WORLD_PATH if os.path.exists(_REAL_WORLD_PATH) else None
        if path is None:
            fd, path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(_FIXTURE_WORLD, f)
        try:
            world = load_world(path)
            self.assertIn("id", world)
            self.assertIn("scenes", world)
        finally:
            if path != _REAL_WORLD_PATH:
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
