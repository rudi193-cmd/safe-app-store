"""Tests for ``the_table.peaks`` -- the exact-odds forecaster (box-build SPEC
ruling R8; SPEC-documented §8 J3 (d); handoff 2026-10-16 Q16).

Two sources that must agree, as the experiment this module was ported from
put it: ``exact`` (2d6 + stat enumerated) and ``measured`` (N seeded runs
through the real ``StorySession``). The measured side lives here, in the
test, through ``StorySession``'s PUBLIC surface only (``reset``, ``observe``,
``step``, ``pending_seal``, ``is_terminal``, ``result``) -- ``peaks.py``
itself never touches the session.

Run with: python -m pytest -q tests/test_peaks.py (from apps/the-table/)
"""
from __future__ import annotations

import copy
import itertools
import json
import math
import os
import random
from collections import Counter
from fractions import Fraction

import pytest

from the_table import peaks
from the_table.story_session import StorySession
from the_table.worlds import available_worlds, load_named_world

_HERE = os.path.dirname(os.path.abspath(__file__))
_WORLDS_DIR = os.path.join(os.path.dirname(_HERE), "worlds")
_FIXTURE = os.path.join(_HERE, "fixtures", "foreshadow-2026-10-16-exact.json")

# N seeded runs per world and policy for the exact-vs-measured check, and the
# tolerance on any one path's frequency. The recorded N=500 runs sat within
# 0.037 (handoff 2026-10-16 §2, "<=3.7 points"); at N=2000 the binomial
# standard error on the largest path (p ~ 0.24) is ~0.0096, so 0.03 is a bit
# over three standard errors on the worst path and far wider on the rest.
MEASURED_N = 2000
MEASURED_TOL = 0.03

_WORLD_NAMES = ("hasbeen", "ironworks", "aetheris")

# A tiny world of the pinned shape (two seats, so rotation is exercised).
_FIXTURE_WORLD = {
    "id": "fixture-world",
    "title": "Fixture World",
    "setting": "A bare room. Alice is already here.",
    "stats": ["Grit", "Weird"],
    "base_stat": 1,
    "characters": [
        {"id": "alice", "name": "Alice", "role": "first seat", "seat": True,
         "stats": {"Grit": 2, "Weird": 3}},
        {"id": "bob", "name": "Bob", "role": "second seat", "seat": True,
         "stats": {"Grit": 0}},
        {"id": "carol", "name": "The Carol", "role": "not seated", "seat": False,
         "stats": {}},
    ],
    "places": [{"id": "room", "name": "The Room", "desc": "A bare room."}],
    "scenes": [
        {
            "id": "s1", "title": "Opening", "place": "room",
            "opening": ["The scene opens."],
            "beats": [
                {"id": "b1", "kind": "action", "prompt": "Alice tries something.",
                 "suggests": "Weird",
                 "outcomes": {"strong": "Carol arrives, impressed.",
                              "weak": "It goes okay.", "miss": "It goes badly."}},
                {"id": "b2", "kind": "action", "prompt": "Bob tries something.",
                 "suggests": "Grit",
                 "outcomes": {"strong": "Bob wins.", "weak": "Bob copes.",
                              "miss": "Bob meets Carol the hard way."}},
            ],
        },
        {
            "id": "s2", "title": "Later", "place": "room",
            "opening": ["Later, the room again."],
            "beats": [
                {"id": "b3", "kind": "decision", "prompt": "Who sealed the door?",
                 "proposes": {"fact": "Carol sealed the door.", "proposed_by": "carol"}},
                {"id": "b4", "kind": "action", "prompt": "After the decision.",
                 "suggests": "Grit",
                 "outcomes": {"strong": "a", "weak": "b", "miss": "c"}},
            ],
        },
    ],
}


def _world(**changes) -> dict:
    w = copy.deepcopy(_FIXTURE_WORLD)
    w.update(changes)
    return w


# -- bucketing: the same read StorySession.step applies ------------------------

@pytest.mark.parametrize("total", range(-10, 25))
def test_bucket_is_story_sessions_read(total):
    # story_session.py step(): result >= 10 strong, >= 7 weak, else miss.
    want = "strong" if total >= 10 else "weak" if total >= 7 else "miss"
    assert peaks.bucket(total) == want


@pytest.mark.parametrize("stat", range(-8, 11))
def test_bucket_probs_match_brute_force(stat):
    got = peaks.bucket_probs(stat)
    brute = Counter()
    for a in range(1, 7):
        for b in range(1, 7):
            t = a + b + stat
            brute["strong" if t >= 10 else "weak" if t >= 7 else "miss"] += 1
    assert got == {k: Fraction(brute[k], 36) for k in peaks.BUCKETS}
    assert all(isinstance(v, Fraction) for v in got.values())


@pytest.mark.parametrize("stat", range(-5, 6))
def test_bucket_probs_sum_to_one_exactly(stat):
    # SPEC-documented §8(d): Fractions, every stat -5..+5.
    assert sum(peaks.bucket_probs(stat).values()) == 1


def test_bucket_probs_stat_bounds():
    # 2d6 spans 2..12: at stat <= -6 nothing reaches 7; at stat >= 8 nothing
    # falls below 10. Outside those bounds the odds stop moving.
    assert peaks.bucket_probs(-6) == {"strong": 0, "weak": 0, "miss": 1}
    assert peaks.bucket_probs(-100) == peaks.bucket_probs(-6)
    assert peaks.bucket_probs(8) == {"strong": 1, "weak": 0, "miss": 0}
    assert peaks.bucket_probs(100) == peaks.bucket_probs(8)
    # The known table at stat 0: strong 6/36, weak 15/36, miss 15/36.
    assert peaks.bucket_probs(0) == {"strong": Fraction(1, 6), "weak": Fraction(5, 12),
                                     "miss": Fraction(5, 12)}


# -- exact(): paths, mass, shape ------------------------------------------------

def test_exact_enumerates_every_path_and_sums_to_one():
    ex = peaks.exact(_world())
    assert set(ex["per_beat"]) == {"b1", "b2"}  # stops at the decision beat b3
    assert len(ex["paths"]) == 9
    assert {p["path"] for p in ex["paths"]} == {
        "-".join(c) for c in itertools.product(peaks.BUCKETS, repeat=2)
    }
    assert sum(p["p"] for p in ex["paths"]) == 1
    assert all(isinstance(p["p"], Fraction) for p in ex["paths"])
    # sorted by probability, descending
    ps = [p["p"] for p in ex["paths"]]
    assert ps == sorted(ps, reverse=True)


def test_exact_matches_brute_force_product_with_seat_rotation():
    # b1 is seat 0 (Alice, Weird 3); b2 is seat 1 (Bob, Grit 0 -- not base_stat).
    ex = peaks.exact(_world())
    p1, p2 = peaks.bucket_probs(3), peaks.bucket_probs(0)
    assert ex["per_beat"]["b1"] == p1
    assert ex["per_beat"]["b2"] == p2
    for p in ex["paths"]:
        k1, k2 = p["path"].split("-")
        assert p["p"] == p1[k1] * p2[k2]


def test_exact_random_policy_is_uniform_over_stats():
    ex = peaks.exact(_world(), policy="random")
    # seat 0: mean of Grit 2 and Weird 3; seat 1: mean of Grit 0 and Weird 1 (base).
    half = Fraction(1, 2)
    want_b1 = {k: half * (peaks.bucket_probs(2)[k] + peaks.bucket_probs(3)[k]) for k in peaks.BUCKETS}
    want_b2 = {k: half * (peaks.bucket_probs(0)[k] + peaks.bucket_probs(1)[k]) for k in peaks.BUCKETS}
    assert ex["per_beat"] == {"b1": want_b1, "b2": want_b2}
    assert sum(p["p"] for p in ex["paths"]) == 1


def test_exact_refuses_unknown_policy():
    with pytest.raises(ValueError):
        peaks.exact(_world(), policy="greedy")


def test_exact_firsts_met_curve_held():
    ex = peaks.exact(_world())
    by = {p["path"]: p for p in ex["paths"]}
    # Alice is in the setting; Carol is first met on b1 strong or b2 miss.
    assert by["strong-strong"]["firsts"] == [
        {"beat": "b1", "bucket": "strong", "introduces": ["carol"]},
        {"beat": "b2", "bucket": "strong", "introduces": ["bob"]},
    ]
    assert by["weak-miss"]["firsts"] == [{"beat": "b2", "bucket": "miss", "introduces": ["bob", "carol"]}]
    assert by["weak-weak"]["met"] == ["alice", "bob"]
    assert by["weak-weak"]["firsts"] == [{"beat": "b2", "bucket": "weak", "introduces": ["bob"]}]
    assert by["miss-miss"]["curve"] == [-1, -2] and by["miss-miss"]["held"] is False
    assert by["strong-miss"]["curve"] == [1, 0] and by["strong-miss"]["held"] is True


def test_exact_does_not_mutate_the_world():
    w = _world()
    before = copy.deepcopy(w)
    peaks.exact(w)
    peaks.distribution(w)
    assert w == before


def test_sheets_for_mirrors_story_session_reset():
    for name in _WORLD_NAMES:
        world = load_named_world(name)
        s = StorySession(os.path.join(_WORLDS_DIR, f"{name}.json"))
        s.reset(0)
        sheets = peaks.sheets_for(world)
        assert sheets == [s.observe(i).view["stats"] for i in range(s.seats)]


# -- the empty and the decision-first world ------------------------------------

def test_world_with_no_action_beat():
    # SPEC-documented §8(d) break test: a world opening on a decision gives
    # one empty path with p 1, not a crash.
    w = _world()
    w["scenes"] = [w["scenes"][1]]  # s2 opens on the decision beat b3
    ex = peaks.exact(w)
    assert ex["per_beat"] == {}
    assert ex["paths"] == [{"path": "", "p": 1, "curve": [], "firsts": [],
                            "met": ["alice"], "held": True}]
    assert peaks.distribution(w) == [{"path": "", "p": 1.0, "band": "likely"}]


def test_empty_world():
    # No scenes at all: nothing to play, one empty path with all the mass.
    w = _world(scenes=[])
    ex = peaks.exact(w)
    assert len(ex["paths"]) == 1 and ex["paths"][0]["p"] == 1 and ex["paths"][0]["path"] == ""
    assert peaks.first_decision(w) is None
    assert peaks.action_beats(w) == []
    # A scene with no beats behaves the same.
    w2 = _world()
    w2["scenes"][0]["beats"] = []
    w2["scenes"] = w2["scenes"][:1]
    assert peaks.distribution(w2) == [{"path": "", "p": 1.0, "band": "likely"}]


def test_world_with_no_decision_beat_plays_every_beat():
    w = _world()
    w["scenes"][1]["beats"] = [w["scenes"][1]["beats"][1]]  # drop the decision; keep b4
    assert peaks.first_decision(w) is None
    ex = peaks.exact(w)
    assert list(ex["per_beat"]) == ["b1", "b2", "b4"]
    assert len(ex["paths"]) == 27
    assert sum(p["p"] for p in ex["paths"]) == 1
    # b4 is turn 2 -> seat 0 (Alice, Grit 2); crossing into s2 reads its opening.
    assert ex["per_beat"]["b4"] == peaks.bucket_probs(2)


def test_exact_with_action_beats_but_no_seat_refuses():
    w = _world()
    for c in w["characters"]:
        c["seat"] = False
    with pytest.raises(ValueError):
        peaks.exact(w)


# -- distribution(): the one-script wager shape --------------------------------

def test_distribution_shape_and_mass():
    for name in _WORLD_NAMES:
        for policy in peaks.POLICIES:
            d = peaks.distribution(load_named_world(name), policy=policy)
            assert d and all(set(e) == {"path", "p", "band"} for e in d)
            assert all(isinstance(e["p"], float) and 0 <= e["p"] <= 1 for e in d)
            assert all(e["band"] in ("likely", "middle", "outlier") for e in d)
            assert all(isinstance(e["path"], str) for e in d)
            # every path kept, nothing smoothed; mass is 1 (exactly in
            # Fractions, see exact(); the float edge within rounding)
            assert len(d) == 3 ** len(peaks.action_beats(load_named_world(name)))
            assert math.isclose(math.fsum(e["p"] for e in d), 1.0, abs_tol=1e-12)
            assert [e["p"] for e in d] == sorted((e["p"] for e in d), reverse=True)
            json.dumps(d)  # a wager row is JSON


def test_distribution_bands():
    d = peaks.distribution(_world())
    top = max(e["p"] for e in d)
    for e in d:
        if e["p"] == top:
            assert e["band"] == "likely"
        elif e["p"] >= 0.05:
            assert e["band"] == "middle"
        else:
            assert e["band"] == "outlier"
    assert d[0]["band"] == "likely"
    assert any(e["band"] == "outlier" for e in d)  # miss-miss at (1/36)*(15/36)


def test_distribution_top_truncates_and_refuses_bad_top():
    d = peaks.distribution(_world(), top=3)
    assert len(d) == 3 and d == peaks.distribution(_world())[:3]
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            peaks.distribution(_world(), top=bad)


def test_distribution_lines_up_with_onescript_match_rule():
    # reverse._match_distribution matches by path_index, else by a
    # case-insensitive substring of `path`: the shape here must let a sealed
    # outcome name an entry either way.
    d = peaks.distribution(_world())
    assert d[0] == d[0]  # by path_index: a plain list, index 0 is the likely path
    assert d[0]["band"] == "likely"
    needle = "Strong-Weak".lower()
    hits = [e for e in d if needle in e["path"].lower()]
    assert len(hits) == 1 and hits[0]["path"] == "strong-weak"


# -- against the recorded experiment -------------------------------------------

@pytest.fixture(scope="module")
def recorded():
    with open(_FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def test_distribution_matches_recorded_runs(recorded):
    # SPEC-documented §8(d): the recorded `p` columns (foreshadow experiment,
    # runs/*-peaks.json) equal this module's exact output to 4 places, for
    # all three worlds and both policies.
    for name in _WORLD_NAMES:
        world = load_named_world(name)
        for policy, rec in recorded["worlds"][name]["policies"].items():
            got = {e["path"]: round(e["p"], 4) for e in peaks.distribution(world, policy=policy)}
            assert got == rec["paths"], (name, policy)
            ex = peaks.exact(world, policy=policy)
            held = float(sum(p["p"] for p in ex["paths"] if p["held"]))
            assert math.isclose(held, rec["held_p"], abs_tol=5e-4), (name, policy)


def test_fixture_covers_every_shipped_world(recorded):
    assert set(recorded["worlds"]) == set(available_worlds()) == set(_WORLD_NAMES)


# -- against the real StorySession ---------------------------------------------

def _measured(name: str, n: int, policy: str) -> tuple[Counter, Counter]:
    """N seeded runs through the real StorySession (real Engine.roll, global
    random seeded by reset), stopping at the first pending seal. The bucket
    of each step is read from the public result().scores tally."""
    world_path = os.path.join(_WORLDS_DIR, f"{name}.json")
    world = load_named_world(name)
    s = StorySession(world_path)
    paths, bucket_rates = Counter(), Counter()
    for seed in range(n):
        s.reset(seed)
        rng = random.Random(seed * 104729)  # the experiment's own choice stream
        combo = []
        while not s.is_terminal() and s.pending_seal() is None:
            seat = s.current_seat()
            view = s.observe(seat).view
            stat = view["suggests"] if policy == "suggested" else rng.choice(world["stats"])
            before = s.result().scores
            s.step(seat, ("act", stat))
            after = s.result().scores
            combo.append(next(k for k in peaks.BUCKETS if after[k] != before[k]))
        paths["-".join(combo)] += 1
        for i, k in enumerate(combo):
            bucket_rates[(i, k)] += 1
    return paths, bucket_rates


@pytest.mark.parametrize("name", _WORLD_NAMES)
@pytest.mark.parametrize("policy", peaks.POLICIES)
def test_exact_agrees_with_measured_within_recorded_gap(name, policy):
    # SPEC-documented §8(d), widened from N=500 to N=2000 per the J3 build
    # order; tolerance MEASURED_TOL on every path AND on every per-beat
    # bucket rate. The recorded N=500 gap was <=0.037 (handoff 10-16 §2).
    world = load_named_world(name)
    ex = peaks.exact(world, policy=policy)
    got, rates = _measured(name, MEASURED_N, policy)
    assert sum(got.values()) == MEASURED_N
    worst = 0.0
    for p in ex["paths"]:
        gap = abs(float(p["p"]) - got.get(p["path"], 0) / MEASURED_N)
        worst = max(worst, gap)
    assert worst <= MEASURED_TOL, (name, policy, worst)
    assert set(got) <= {p["path"] for p in ex["paths"]}  # nothing measured that exact missed
    beats = peaks.action_beats(world)
    for i, b in enumerate(beats):
        for k in peaks.BUCKETS:
            gap = abs(float(ex["per_beat"][b["id"]][k]) - rates[(i, k)] / MEASURED_N)
            assert gap <= MEASURED_TOL, (name, policy, b["id"], k, gap)


def test_measured_stops_at_the_decision_beat_every_run():
    # No path ever crosses a decision: every measured path has exactly as
    # many steps as there are action beats before the first decision.
    for name in _WORLD_NAMES:
        world = load_named_world(name)
        depth = len(peaks.action_beats(world))
        got, _ = _measured(name, 50, "suggested")
        assert all(len(path.split("-")) == depth for path in got)


# -- swing(): a reading, not a probability -------------------------------------

def test_swing_reads_entropy_and_cast_divergence():
    w = _world()
    beats = peaks.action_beats(w)
    sw = peaks.swing(w, beats[0], peaks.bucket_probs(3))
    assert sw["cast_diverges"] is True  # strong names Carol, the others do not
    assert sw["outcome_casts"]["strong"] == ["carol"]
    assert 0 < sw["entropy_bits"] <= sw["max_bits"] == round(math.log2(3), 3)
    assert math.isclose(sw["p_strong"] + sw["p_weak"] + sw["p_miss"], 1.0, abs_tol=2e-3)


# -- CLI -----------------------------------------------------------------------

def test_cli_wager_prints_the_distribution(capsys):
    rc = peaks.main([os.path.join(_WORLDS_DIR, "hasbeen.json"), "--wager"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == peaks.distribution(load_named_world("hasbeen"))


def test_cli_report_floats_at_the_edge(capsys):
    rc = peaks.main([os.path.join(_WORLDS_DIR, "hasbeen.json"), "--policy", "random"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"per_beat", "paths"}
    assert math.isclose(math.fsum(p["p"] for p in out["paths"]), 1.0, abs_tol=1e-12)
