"""Differential: the browser engine must play the same game as the Python.

400 seeds, ~40 moves each, state compared after every single move. The move
scripts are generated once in Python and handed to node verbatim, so this
compares the two engines and not two different move sequences.

It compares state — documents held, surprise, dwell, refusal tier, resolution —
and not rendered prose. That used to be a real hole: engine.js carried a
hand-copy of the graph, so a wording divergence passed green. It no longer
does. Offices, documents, rules and prose are now generated from graph.py by
bureau/web/build.py, so there is one source and nothing to diverge.

**What this still cannot see:** the page's own rendering layer — labels, DOM,
CSS. Nothing in Python touches those, and a browser found the last bug there
(a class-level display beating the hidden attribute), not this suite.

Skips if node is absent rather than silently passing.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from bureau import graph as G
from bureau.play import NAPKIN_BLANK, NAPKIN_WORD, Session

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "diff_runner.js"
SEEDS = 400
MOVES = 40


def build_scripts() -> list[dict]:
    """Move scripts that actually reach the interesting states.

    Weighted toward Gerald and toward handing over napkins, because a walk that
    never gets a napkin never exercises the branch worth comparing.
    """
    ids = list(G.OFFICES)
    jobs = []
    for seed in range(SEEDS):
        rng = random.Random(seed ^ 0xBEEF)
        moves = []
        for _ in range(MOVES):
            roll = rng.random()
            if roll < 0.18:
                moves.append(["hand", rng.choice(["hanz", "records"])])
            elif roll < 0.55:
                moves.append(["go", "gerald"])
            else:
                moves.append(["go", rng.choice(ids)])
        jobs.append({"seed": seed, "moves": moves})
    return jobs


def python_trace(job: dict) -> list[dict]:
    s = Session(seed=job["seed"])
    trace = []
    for verb, arg in job["moves"]:
        s.visit(arg) if verb == "go" else s.hand(arg)
        trace.append(s.state())
    return trace


class TestBrowserPortMatchesPython(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_same_seed_same_game(self):
        jobs = build_scripts()
        proc = subprocess.run(
            ["node", str(RUNNER)],
            input=json.dumps(jobs),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        js = {r["seed"]: r["trace"] for r in json.loads(proc.stdout)}

        compared = 0
        for job in jobs:
            py = python_trace(job)
            other = js[job["seed"]]
            self.assertEqual(len(py), len(other))
            for i, (a, b) in enumerate(zip(py, other)):
                with self.subTest(seed=job["seed"], move=i):
                    self.assertEqual(a, b)
                compared += 1
        self.assertEqual(compared, SEEDS * MOVES)
        print(f"\n  differential: {compared:,} state comparisons across {SEEDS} seeds")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_differential_can_fail(self):
        """Perturb one engine; confirm the comparison notices.

        A differential that passes against a deliberately broken counterpart is
        measuring nothing. This mutates the Python side's starting surprise and
        asserts the traces stop matching.
        """
        import bureau.napkin as napkin

        job = {"seed": 3, "moves": [["go", "gerald"]] * MOVES}
        proc = subprocess.run(
            ["node", str(RUNNER)],
            input=json.dumps([job]),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reference = json.loads(proc.stdout)[0]["trace"]
        self.assertEqual(python_trace(job), reference, "sanity: unmutated must match")

        original = napkin.STARTING_SURPRISE
        try:
            napkin.STARTING_SURPRISE = original + 1
            mutated = Session(seed=3)
            mutated.goo.surprise = napkin.STARTING_SURPRISE
            trace = []
            for verb, arg in job["moves"]:
                mutated.visit(arg) if verb == "go" else mutated.hand(arg)
                trace.append(mutated.state())
            self.assertNotEqual(trace, reference, "mutation went undetected")
        finally:
            napkin.STARTING_SURPRISE = original


class TestNapkinsAreComparedState(unittest.TestCase):
    def test_napkins_appear_in_the_compared_state(self):
        """If napkins were filtered out, the differential would miss the payload."""
        s = Session(seed=0)
        s.held.add(NAPKIN_WORD)
        self.assertIn(NAPKIN_WORD, s.state()["held"])
        s.held.add(NAPKIN_BLANK)
        self.assertIn(NAPKIN_BLANK, s.state()["held"])


if __name__ == "__main__":
    unittest.main()
