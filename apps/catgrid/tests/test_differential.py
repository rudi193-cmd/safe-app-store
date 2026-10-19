"""Differential: the browser engine must make the same boards and play the
same games as the Python (bureau's pattern, apps/bureau/tests/test_differential.py).

Boards: every 1-cat size over many seeds, the 2- and 3-cat levels over a few,
and the sizes that refuse; regions and answer compared cell for cell. Games:
move scripts drawn once in Python (legal moves, and junk that must be refused)
and handed to node verbatim, so this compares two engines, not two move
sequences; state and narration compared after every move.

What it cannot see: the page's rendering (labels, DOM, CSS). Skips if node is
absent rather than passing silently.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from catgrid import play
from catgrid.board import NoBoard, address, generate
from catgrid.play import Game, Refused

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "diff_runner.js"
NODE = shutil.which("node") or ("/opt/node22/bin/node" if os.path.exists("/opt/node22/bin/node") else None)
BANK = [{"id": f"t:{i}", "question": f"Q{i}?", "answer": f"A{i}."} for i in range(7)]
WORDS = ["Filed.", "Sieve", "Gerald"]
JUNK = [("cat", "Z99"), ("cat",), ("x", 5), ("stroke", "A1"), ("answer", "E"), ("answer", "A"),
        ("trivia",), ("hint",)]

BOARDS = ([{"seed": s, "n": n, "k": 1} for n in (1, 4, 5, 6, 7, 8, 9) for s in range(40)]
          + [{"seed": s, "n": n, "k": 2} for n in (8, 9, 10) for s in range(6)]
          + [{"seed": s, "n": n, "k": 3} for n in (12, 13) for s in range(2)]
          + [{"seed": 1, "n": n, "k": k} for n, k in ((2, 1), (3, 1), (7, 2), (11, 3), (14, 3), (0, 1))])


def node(jobs: dict) -> dict:
    proc = subprocess.run([NODE, str(RUNNER)], input=json.dumps(jobs), capture_output=True,
                          text=True, timeout=600)
    if proc.returncode:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


def py_board(job: dict) -> dict:
    try:
        b = generate(job["seed"], job["n"], k=job["k"])
    except NoBoard:
        return {"error": "NoBoard"}
    return json.loads(json.dumps({"regions": b.regions, "solution": b.solution}))


def scripts(count: int = 150, length: int = 60) -> list:
    jobs = []
    for seed in range(count):
        rng = random.Random(seed ^ 0xCA7)
        n = (5, 6, 7, 8)[seed % 4]
        g = Game.new(seed, n, bank=BANK, words=WORDS)
        moves = []
        right = sorted(address(*divmod(i, n)) for i in g.board.cats())
        for _ in range(length):
            legal = g.legal_moves()
            roll = rng.random()
            # weighted so games are won and lost, napkins found and hints earned:
            # the script may use the answer; it is input to both engines alike
            if not legal or roll < 0.08:
                move = rng.choice(JUNK)
            elif roll < 0.30:
                move = ("cat", rng.choice(right))
            elif roll < 0.55:
                move = ("x", rng.choice(g.board.addresses()))
            elif roll < 0.65 and g.question:
                move = ("answer", rng.choice([g.question["right"], "A", "B"]))
            elif roll < 0.72:
                move = ("trivia",)
            else:
                move = rng.choice(legal)
            moves.append(list(move))
            try:
                g.step(tuple(move))
            except Refused:
                pass
        jobs.append({"seed": seed, "n": n, "k": 1, "bank": BANK, "words": WORDS, "moves": moves})
    return jobs


def py_trace(job: dict) -> list:
    g = Game.new(job["seed"], job["n"], job["k"], bank=job["bank"], words=job["words"])
    out = []
    for move in job["moves"]:
        try:
            out.append({"said": g.step(tuple(move)), "state": g.state()})
        except Refused:
            out.append({"refused": True, "state": g.state()})
    return json.loads(json.dumps(out))


@unittest.skipUnless(NODE, "node not available")
class TestTheBrowserEngineMatchesThePython(unittest.TestCase):
    def test_same_seed_same_board(self):
        got = node({"boards": BOARDS})["boards"]
        self.assertEqual(len(got), len(BOARDS))
        for job, js in zip(BOARDS, got):
            with self.subTest(**job):
                self.assertEqual(js, py_board(job))
        self.assertIn({"error": "NoBoard"}, got)

    def test_same_moves_same_game(self):
        jobs = scripts()
        got = node({"games": jobs})["games"]
        compared = 0
        for job, js in zip(jobs, got):
            py = py_trace(job)
            self.assertEqual(len(js), len(py))
            for i, (a, b) in enumerate(zip(py, js)):
                if a != b:
                    self.fail(f"seed {job['seed']} move {i} {job['moves'][i]}: {a} != {b}")
                compared += 1
        self.assertEqual(compared, 150 * 60)
        kinds = {m[0] for job in jobs for m in job["moves"]}
        self.assertLessEqual({"cat", "x", "clear", "hint", "trivia", "answer"}, kinds)

    def test_same_day_same_round_and_seed(self):
        from catgrid import daily

        rng = random.Random(19)
        jobs = [{"day": f"{y}-{m:02d}-{d:02d}", "randomness": "%064x" % rng.getrandbits(256)}
                for y in (2020, 2024, 2026, 2031) for m in (1, 2, 7, 12) for d in (1, 15, 28)
                if (y, m) >= (2020, 8)]
        got = node({"daily": jobs})["daily"]
        self.assertEqual(len(got), len(jobs))
        for job, js in zip(jobs, got):
            self.assertEqual(js, {"round": daily.round_for(job["day"]),
                                  "seed": daily.seed_of(job["randomness"])}, job)

    def test_the_differential_can_fail(self):
        """A differential that passes against a broken counterpart measures
        nothing: perturb the Python's hearts and the traces must part."""
        job = scripts(4, 60)[1]
        js = node({"games": [job]})["games"][0]
        self.assertEqual(py_trace(job), js, "sanity: unperturbed must match")
        with mock.patch.object(play, "HEARTS", play.HEARTS + 1):
            self.assertNotEqual(py_trace(job), js, "a perturbation went unnoticed")


if __name__ == "__main__":
    unittest.main()
