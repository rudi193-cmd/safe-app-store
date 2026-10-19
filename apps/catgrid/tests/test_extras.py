"""Hints, trivia and napkins (play.py R9-R12), each by the move it forbids, on a
fixed bank and word list so the tests read nothing outside the app; then the
same against the real Jeles corpus and napkin file when they sit beside it."""
from __future__ import annotations

import copy
import json
import unittest

from catgrid import eggs, trivia
from catgrid.board import address
from catgrid.play import FREE_HINTS, HEARTS, Game, Refused

BANK = sorted(
    ({"id": f"t:{i}", "question": f"Question {i}?", "answer": f"Answer {i}."} for i in range(8)),
    key=lambda b: b["id"],
)
WORDS = ["Copenhagen.", "Filed.", "Sieve"]


def egg_seed(n=6):
    """A seed whose board hides a napkin, found by looking, not assumed."""
    return next(s for s in range(200) if Game.new(s, n, words=WORDS).egg)


class Base(unittest.TestCase):
    def setUp(self):
        self.g = Game.new(7, 6, bank=BANK, words=WORDS)

    def refused(self, move):
        before = copy.deepcopy(self.g.state())
        with self.assertRaises(Refused):
            self.g.step(move)
        self.assertEqual(self.g.state(), before)

    def right(self):
        self.g.step(("trivia",))
        return self.g.question["right"]


class TestHints(Base):
    def test_R9_the_free_hint_places_a_sure_cat_and_costs_nothing(self):
        self.g.step(("hint",))
        cats = [a for a, v in self.g.cells.items() if v == "cat"]
        self.assertEqual(cats, [address(0, self.g.board.solution[0])])
        self.assertEqual((self.g.hearts, self.g.hints), (HEARTS, {"free": 0, "earned": 0}))

    def test_R9_no_hint_to_spend_is_refused(self):
        for _ in range(FREE_HINTS):
            self.g.step(("hint",))
        self.refused(("hint",))

    def test_R9_a_hint_lifts_a_wrong_mark_on_the_answer(self):
        a = address(0, self.g.board.solution[0])
        self.g.step(("x", a))
        self.g.step(("hint",))
        self.assertEqual(self.g.cells[a], "cat")

    def test_hints_alone_solve_the_board(self):
        g = Game.new(3, 5, bank=BANK)
        while g.status == "playing":
            if not g.hints["free"] + g.hints["earned"]:
                g.step(("trivia",))
                g.step(("answer", g.question["right"]))
            g.step(("hint",))
        self.assertEqual((g.status, g.hearts), ("won", HEARTS))


class TestTrivia(Base):
    def test_R10_a_question_from_the_bank_with_four_options(self):
        self.g.step(("trivia",))
        q = self.g.state()["trivia"]
        self.assertEqual((q["state"], len(q["options"])), ("waiting", 4))
        self.assertIn(q["question"], {b["question"] for b in BANK})
        self.assertEqual(q["source"], trivia.SOURCE)

    def test_R10_one_question_at_a_time(self):
        self.g.step(("trivia",))
        self.refused(("trivia",))

    def test_R10_no_bank_no_trivia_and_it_says_why(self):
        g = Game.new(7, 6)
        self.assertEqual(g.state()["trivia"]["state"], "unavailable")
        with self.assertRaises(Refused):
            g.step(("trivia",))
        self.assertNotIn(("trivia",), g.legal_moves())

    def test_R11_right_earns_a_hint(self):
        self.g.step(("answer", self.right()))
        self.assertEqual(self.g.hints["earned"], 1)

    def test_R11_wrong_costs_nothing(self):
        right = self.right()
        wrong = next(x for x in trivia.LABELS if x != right)
        before = (self.g.hearts, dict(self.g.hints))
        self.g.step(("answer", wrong))
        self.assertEqual((self.g.hearts, self.g.hints), before)
        self.assertEqual(self.g.asked[-1]["right"], False)

    def test_R11_no_question_no_answer(self):
        self.refused(("answer", "A"))
        self.g.step(("trivia",))
        self.refused(("answer", "E"))

    def test_the_answer_key_is_never_in_the_view(self):
        self.g.step(("trivia",))
        self.assertNotIn("right", json.dumps(self.g.state()))

    def test_the_same_seed_asks_the_same_questions(self):
        a = [trivia.ask(BANK, 9, k) for k in range(5)]
        self.assertEqual(a, [trivia.ask(BANK, 9, k) for k in range(5)])
        self.assertNotEqual(a, [trivia.ask(BANK, 10, k) for k in range(5)])


class TestNapkins(unittest.TestCase):
    def test_R12_marking_the_napkins_cell_finds_it_once(self):
        g = Game.new(egg_seed(), 6, words=WORDS)
        cell, word = g.egg
        view = g.state()  # never shown before it's found: not its cell, not its word
        self.assertEqual(view["napkins"], {"state": "none found"})
        self.assertNotIn(word, json.dumps(view))
        said = g.step(("x", cell))
        self.assertIn(word, said[-1])
        g.step(("clear", cell))
        g.step(("x", cell))
        self.assertEqual(g.state()["napkins"], {"state": "found",
                                                "found": [{"cell": cell, "word": word}]})

    def test_marking_any_other_cell_finds_nothing(self):
        g = Game.new(egg_seed(), 6, words=WORDS)
        for a in g.board.addresses():
            if a != g.egg[0] and not g._answer(a):
                g.step(("x", a))
        self.assertEqual(g.state()["napkins"], {"state": "none found"})

    def test_hide_picks_only_from_the_cells_it_is_given(self):
        empties = ["B2", "C3", "D4"]
        for s in range(500):
            got = eggs.hide(s, WORDS, empties)
            if got:
                self.assertIn(got[0], empties, s)
                self.assertIn(got[1], WORDS, s)

    def test_a_napkin_never_sits_under_a_cat(self):
        for s in range(60):
            g = Game.new(s, 6, words=WORDS)
            if g.egg:
                self.assertFalse(g._answer(g.egg[0]), s)

    def test_the_same_seed_hides_the_same_napkin(self):
        s = egg_seed()
        self.assertEqual(Game.new(s, 6, words=WORDS).egg, Game.new(s, 6, words=WORDS).egg)

    def test_only_some_boards_have_one(self):
        have = sum(bool(Game.new(s, 5, words=WORDS).egg) for s in range(60))
        self.assertTrue(5 < have < 40, have)

    def test_no_words_no_napkins_and_it_says_why(self):
        self.assertEqual(Game.new(7, 6).state()["napkins"]["state"], "unavailable")


class TestTheRealSources(unittest.TestCase):
    def test_jeles_corpus(self):
        bank, why = trivia.load_jeles()
        if not bank:
            self.skipTest(why)
        self.assertGreater(len(bank), 100)
        self.assertTrue(all(b["question"].endswith("?") for b in bank))
        q = trivia.ask(bank, 1, 0)
        self.assertEqual(len(set(q["options"].values())), 4)

    def test_geralds_napkins(self):
        words, why = eggs.load_napkins()
        if not words:
            self.skipTest(why)
        self.assertTrue(all(w and not any(c.isspace() for c in w) for w in words))
        self.assertIn("Copenhagen.", words)
