"""Trivia from Jeles's SOIL collection: only rows Jeles lets answer join the
bank, each carries its own label, and an unreadable store is said, not guessed."""
from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

from catgrid import trivia
from catgrid.play import Game


def row(i, **kw):
    r = {"id": f"s{i}", "question": f"What is {i}?", "answer": f"It is {i}. More.",
         "sources": [f"https://www.nasa.gov/{i}"], "verified_by": "public record: NASA",
         "verification_kind": "human", "status": "verified", "visibility": "serve"}
    r.update(kw)
    return r


class Store:
    def __init__(self, rows):
        self.rows, self.asked = rows, []

    def list(self, collection):
        self.asked.append(collection)
        return list(self.rows)


GOOD = [row(i) for i in range(5)]


class TestWhatJoinsTheBank(unittest.TestCase):
    def test_it_reads_jeless_collection_and_nothing_else(self):
        s = Store(GOOD)
        bank, why = trivia.load_jeles(s)
        self.assertEqual((s.asked, why, len(bank)), (["ask_jeles_corpus"], "", 5))

    def test_only_rows_that_may_answer(self):
        bad = [row(10, verification_kind="asserted", status="asserted"),
               row(11, visibility="internal"), row(12, visibility=None),
               row(13, verification_kind=None), row(14, question="Not a question"),
               row(15, sources=[]), row(16, sources=["  "]), row(17, answer=""),
               row(18, question=None)]
        bank, _ = trivia.load_jeles(Store(GOOD + bad))
        self.assertEqual(sorted(b["id"] for b in bank), [f"s{i}" for i in range(5)])

    def test_public_and_machine_rows_answer(self):
        rows = GOOD[:3] + [row(20, visibility="public"), row(21, verification_kind="machine",
                                                              status="corroborated")]
        bank, _ = trivia.load_jeles(Store(rows))
        self.assertEqual(len(bank), 5)

    def test_each_question_carries_its_own_label(self):
        rows = GOOD[:4] + [row(30, verified_by="", status="corroborated", verification_kind="machine")]
        bank, _ = trivia.load_jeles(Store(rows))
        by = {b["id"]: b["source"] for b in bank}
        self.assertEqual(by["s0"], "Jeles, verified: public record: NASA")
        self.assertEqual(by["s30"], "Jeles, corroborated")
        q = trivia.ask(bank, 1, 0)
        self.assertEqual(q["source"], by[q["id"]])

    def test_the_view_shows_the_waiting_questions_label(self):
        bank, _ = trivia.load_jeles(Store(GOOD))
        g = Game.new(3, 6, bank=bank)
        g.step(("trivia",))
        self.assertEqual(g.state()["trivia"]["source"], "Jeles, verified: public record: NASA")
        self.assertEqual(Game.new(3, 6, bank=bank).state()["trivia"]["source"], trivia.SOURCE)


class TestWhenJelesCantBeRead(unittest.TestCase):
    def test_too_few_answering_rows_is_no_bank(self):
        bank, why = trivia.load_jeles(Store(GOOD[:3] + [row(9, visibility="internal")]))
        self.assertEqual(bank, [])
        self.assertIn("too few", why)

    def test_a_failing_store_is_said(self):
        class Down:
            def list(self, c):
                raise OSError("gone")
        bank, why = trivia.load_jeles(Down())
        self.assertEqual(bank, [])
        self.assertIn("could not be read", why)

    def test_no_seam_installed(self):
        with mock.patch.dict(sys.modules, {"storage_backend": None}):
            self.assertIn("isn't installed", trivia.load_jeles()[1])

    def test_no_backend_configured(self):
        seam = types.SimpleNamespace(available=lambda: False, list_records=lambda c: GOOD)
        with mock.patch.dict(sys.modules, {"storage_backend": seam}):
            self.assertIn("no SOIL backend", trivia.load_jeles()[1])

    def test_the_seams_own_backend_is_read(self):
        seen = []
        seam = types.SimpleNamespace(available=lambda: True,
                                     list_records=lambda c: seen.append(c) or GOOD)
        with mock.patch.dict(sys.modules, {"storage_backend": seam}):
            bank, why = trivia.load_jeles()
        self.assertEqual((seen, why, len(bank)), (["ask_jeles_corpus"], "", 5))


class TestTheManifest(unittest.TestCase):
    def test_jeles_is_in_scope_and_never_written(self):
        import json
        from pathlib import Path

        from catgrid import soil

        m = json.loads((Path(__file__).resolve().parents[1] / "safe-app-manifest.json").read_text())
        self.assertIn("ask_jeles_corpus", m["store_scope"])
        self.assertNotIn("store_write", m["permissions"])
        self.assertNotIn("ask_jeles_corpus", soil.COLLECTIONS)  # the write wall


if __name__ == "__main__":
    unittest.main()
