"""The lane: a game's records stay in catgrid's collections, hold only inputs,
and play back to the same game; with no backend nothing is written, said."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from catgrid import soil
from catgrid.play import Game
from tests.test_extras import BANK, WORDS, egg_seed

MANIFEST = Path(__file__).resolve().parents[1] / "safe-app-manifest.json"


class Backend:
    def __init__(self):
        self.rows = {}

    def put(self, collection, record, *, record_id=""):
        self.rows[(collection, record_id)] = record
        return record

    def list(self, collection):
        return [r for (c, _), r in self.rows.items() if c == collection]

    def delete(self, collection, record_id):
        return self.rows.pop((collection, record_id), None) is not None


def played():
    g = Game.new(egg_seed(), 6, bank=BANK, words=WORDS)
    g.step(("x", g.egg[0]))
    g.step(("trivia",))
    g.step(("answer", g.question["right"]))
    g.step(("hint",))
    g.step(("hint",))
    return g


class TestTheLane(unittest.TestCase):
    def test_every_collection_is_inside_the_manifests_store_scope(self):
        scope = json.loads(MANIFEST.read_text())["store_scope"]
        self.assertEqual(sorted(scope), sorted(soil.COLLECTIONS))
        b = Backend()
        soil.write(played(), b)
        self.assertTrue({c for c, _ in b.rows} <= set(scope))

    def test_a_record_outside_the_lane_is_refused(self):
        b = Backend()
        g = played()
        real = soil.records
        soil.records = lambda game: real(game) + [("fleet_store", "x", {})]
        try:
            with self.assertRaises(ValueError):
                soil.write(g, b)
        finally:
            soil.records = real

    def test_one_record_of_each_kind(self):
        b = Backend()
        got = soil.write(played(), b)
        self.assertEqual(got["state"], "written")
        self.assertEqual(sorted(c for c, _ in b.rows),
                         ["catgrid_games", "catgrid_napkins", "catgrid_trivia"])

    def test_no_backend_writes_nothing_and_says_so(self):
        got = soil.write(played())
        self.assertEqual((got["state"], got["written"]), ("unavailable", 0))


class TestReplay(unittest.TestCase):
    def test_a_record_plays_back_to_the_same_game(self):
        g = played()
        (rec,) = [r for c, _, r in soil.records(g) if c == soil.GAMES]
        again = soil.replay(rec, bank=BANK, words=WORDS)
        self.assertEqual(again.state(), g.state())

    def test_a_record_holds_inputs_not_the_answer(self):
        (rec,) = [r for c, _, r in soil.records(played()) if c == soil.GAMES]
        self.assertEqual(set(rec), {"seed", "n", "board", "bank", "words", "moves",
                                    "status", "hearts"})

    def test_a_different_bank_or_board_is_refused(self):
        (rec,) = [r for c, _, r in soil.records(played()) if c == soil.GAMES]
        with self.assertRaisesRegex(ValueError, "bank"):
            soil.replay(rec, bank=BANK[:-1], words=WORDS)
        with self.assertRaisesRegex(ValueError, "napkin"):
            soil.replay(rec, bank=BANK, words=WORDS[:-1])
        with self.assertRaisesRegex(ValueError, "board"):
            soil.replay({**rec, "board": "0" * 64}, bank=BANK, words=WORDS)
