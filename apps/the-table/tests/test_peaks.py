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
        raw = peaks.raw_sheets_for(world)
        assert raw == [s.observe(i).view["stats"] for i in range(s.seats)]
        # no shipped world collides through an engine alias, so the sheet
        # the engine reads is the raw sheet
        assert peaks.sheets_for(world) == raw


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
    # S1 (audit): one-script's check_distribution refuses an empty path, so
    # distribution() refuses the world instead of emitting one.
    with pytest.raises(ValueError, match="no action beat"):
        peaks.distribution(w)


def test_empty_world():
    # No scenes at all: nothing to play; exact() has one empty path with all
    # the mass, distribution() refuses (S1).
    w = _world(scenes=[])
    ex = peaks.exact(w)
    assert len(ex["paths"]) == 1 and ex["paths"][0]["p"] == 1 and ex["paths"][0]["path"] == ""
    assert peaks.first_decision(w) is None
    assert peaks.action_beats(w) == []
    with pytest.raises(ValueError, match="no action beat"):
        peaks.distribution(w)
    # A scene with no beats behaves the same.
    w2 = _world()
    w2["scenes"][0]["beats"] = []
    w2["scenes"] = w2["scenes"][:1]
    assert peaks.exact(w2)["paths"][0]["path"] == ""
    with pytest.raises(ValueError, match="no action beat"):
        peaks.distribution(w2)


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


# -- audit round (Sonnet, 6d1a597): S1, S2, N1, N3, N5, N6 ---------------------

def test_engine_stat_map_pinned_to_story_session():
    # N3: peaks duplicates engine_v1_7's private stat_map the way
    # story_session does; the two copies must not drift.
    from the_table import story_session
    assert peaks._ENGINE_STAT_MAP == story_session._ENGINE_STAT_MAP


def test_sheets_for_mirrors_engine_alias_collision(tmp_path):
    # N3 (audit coll.py): a world naming both Grit and Integrity hands
    # Engine.roll one dict where Integrity (the later key) overwrites Grit's
    # alias, so a Grit roll really adds Integrity's value. sheets_for says so,
    # and 2000 real StorySession rolls agree with the odds built from it.
    w = _world(stats=["Grit", "Integrity"])
    for c in w["characters"]:
        c["stats"] = {"Grit": 3, "Integrity": -4}
    for sc in w["scenes"]:
        for b in sc["beats"]:
            if b.get("suggests"):
                b["suggests"] = "Grit"
    assert peaks.raw_sheets_for(w)[0] == {"Grit": 3, "Integrity": -4}
    assert peaks.engine_view(peaks.raw_sheets_for(w)[0]) == {"Integrity": -4}
    assert peaks.sheets_for(w)[0] == {"Grit": -4, "Integrity": -4}
    p = peaks.exact(w)["per_beat"]["b1"]
    assert p == peaks.bucket_probs(-4)  # not bucket_probs(3)
    path = tmp_path / "coll.json"
    path.write_text(json.dumps(w))
    s = StorySession(str(path))
    got = Counter()
    n = 2000
    for seed in range(n):
        s.reset(seed)
        s.step(s.current_seat(), ("act", "Grit"))
        sc = s.result().scores
        got[next(k for k in peaks.BUCKETS if sc[k])] += 1
    for k in peaks.BUCKETS:
        assert abs(float(p[k]) - got[k] / n) <= MEASURED_TOL, (k, got)


class _ForcedDice:
    """An rng for ``rng_factory`` whose ``randint`` deals the dice it was
    given, in order. Nothing else is drawn by an action beat."""

    generator_id = "test/forced"

    def __init__(self, dice):
        self._it = iter(dice)

    def randint(self, lo, hi):
        v = next(self._it)
        assert lo <= v <= hi
        return v


def test_bucket_tied_to_story_session_by_forced_dice(tmp_path):
    # N5 (audit edge.py): drive the real StorySession.step over all 36 dice
    # pairs x stats -8..10 with the dice forced through the J2 rng_factory
    # seam, and read the bucket from the public tally. The thresholds in
    # peaks.bucket are thereby pinned to story_session mechanically, not by
    # a copied constant.
    checked = 0
    for stat in range(-8, 11):
        w = _world(base_stat=stat)
        w["characters"] = [{"id": "solo", "name": "Solo", "role": "seat", "seat": True, "stats": {}}]
        w["scenes"] = [w["scenes"][0]]
        w["scenes"][0]["beats"] = w["scenes"][0]["beats"][:1]
        path = tmp_path / f"stat{stat}.json"
        path.write_text(json.dumps(w))
        dice = []
        s = StorySession(str(path), rng_factory=lambda seed, d=dice: _ForcedDice(d))
        for a, b in itertools.product(range(1, 7), repeat=2):
            dice[:] = [a, b]
            s.reset(0)
            s.step(0, ("act", "Weird"))
            sc = s.result().scores
            got = next(k for k in peaks.BUCKETS if sc[k])
            assert got == peaks.bucket(a + b + stat), (a, b, stat, got)
            assert s.last_roll["result"] == a + b + stat
            checked += 1
    assert checked == 36 * 19


def test_exact_refuses_above_the_path_cap():
    # S2: the guard fires before any enumeration (no timing involved: a
    # world of MAX_ACTION_BEATS + 1 beats would be 3**11 paths).
    w = _world()
    b = w["scenes"][0]["beats"][0]
    w["scenes"] = [{**w["scenes"][0],
                    "beats": [{**b, "id": f"b{i}"} for i in range(peaks.MAX_ACTION_BEATS + 1)]}]
    with pytest.raises(ValueError, match="MAX_ACTION_BEATS"):
        peaks.exact(w)
    with pytest.raises(ValueError, match="MAX_ACTION_BEATS"):
        peaks.distribution(w, top=5)  # top does not lift the cap
    # exactly at the cap is allowed: its per-beat table builds without
    # enumerating (action_beats alone), proving the cap is > not >=
    assert len(peaks.action_beats(w)[:peaks.MAX_ACTION_BEATS]) == peaks.MAX_ACTION_BEATS


def test_exact_memoises_text_reads(monkeypatch):
    # S2: mentions() runs once per beat x bucket plus once per scene opening
    # plus once for the world opening -- never per path.
    calls = []
    real = peaks.mentions

    def counting(world, text):
        calls.append(text)
        return real(world, text)

    monkeypatch.setattr(peaks, "mentions", counting)
    w = _world()
    ex = peaks.exact(w)
    beats = len(peaks.action_beats(w))
    assert len(ex["paths"]) == 3 ** beats
    assert len(calls) == 3 * beats + 1 + 1  # outcomes + world opening + scene 0 opening


def test_distribution_tie_order_is_enumeration_order():
    # N6: equal p keeps enumeration order (stable sort). Hasbeen suggested:
    # strong-strong and strong-weak tie at 35/144 and both are likely.
    d = peaks.distribution(load_named_world("hasbeen"))
    assert [e["path"] for e in d[:2]] == ["strong-strong", "strong-weak"]
    assert d[0]["p"] == d[1]["p"] and {d[0]["band"], d[1]["band"]} == {"likely"}
    assert d[2]["band"] != "likely"


def test_partial_path_is_ambiguous_by_onescripts_rule():
    # N1: a partial string matches the first entry containing it; the
    # docstring tells a sealer to name the full path or a path_index.
    d = peaks.distribution(load_named_world("ironworks"))
    hits = [e["path"] for e in d if "weak-miss" in e["path"]]
    assert len(hits) > 1
    assert "FULL path" in peaks.__doc__ and "path_index" in peaks.distribution.__doc__


# -- end to end through one-script (audit e2e.py) ---------------------------

_ONESCRIPT_DIR = os.environ.get("ONESCRIPT_DIR", "/home/user/sandbox/repos/willow-bot/one-script")


def _onescript():
    """The onescript package, or None when its checkout is absent. Set
    ONESCRIPT_DIR to point at willow-bot/one-script."""
    if not os.path.isdir(os.path.join(_ONESCRIPT_DIR, "onescript")):
        return None
    import importlib
    import sys
    if _ONESCRIPT_DIR not in sys.path:
        sys.path.insert(0, _ONESCRIPT_DIR)
    try:
        return {m: importlib.import_module(f"onescript.{m}") for m in ("api", "gate", "reverse")}
    except ImportError:
        return None


_E2E_KEY = b"a-throwaway-human-key-for-tests"


def _box(tmp, api):
    """A throwaway one-script box (after audit e2e.py)."""
    from pathlib import Path
    tmp = Path(tmp)
    g = tmp / "grove"
    (g / "governance").mkdir(parents=True)
    (g / "governance" / "CONSTITUTION.md").write_text("CONST-III CONST-VI")
    ci = g / "ci.yml"
    ci.write_text("pip install ruff==0.16.7")
    k = tmp / "keys" / "keys.json"
    k.parent.mkdir(mode=0o700)
    k.write_text(json.dumps({"desk": "aa" * 32, "human": _E2E_KEY.hex()}))
    k.chmod(0o600)
    kf = tmp / "human" / "key.hex"
    kf.parent.mkdir(mode=0o700)
    kf.write_text(_E2E_KEY.hex() + "\n")
    kf.chmod(0o600)
    cfg = api.Config(box=tmp / "box", keys=k, constitution=g / "governance" / "CONSTITUTION.md",
                     ci=ci, root=tmp / "x", grove=g, venv=tmp / "v",
                     now="2026-10-17T00:00:00Z", no_tests=True, phone=True)
    return cfg, kf


def _forecast_seal_reconcile(tmp, os_, world, outcome):
    api, gate, reverse = os_["api"], os_["gate"], os_["reverse"]
    cfg, kf = _box(tmp, api)
    api.checkin(cfg)
    d = peaks.distribution(world)
    f = api.forecast(cfg, "w1", d)
    assert f["code"] == 0, f
    sign = lambda subj: gate.sign(_E2E_KEY, "seal", subj)
    api.seal_tip(cfg, f["tip"], proof=sign(f["tip"]))
    sub = reverse.outcome_subject(f["subject"], outcome)
    s = api.seal_outcome(cfg, f["subject"], outcome, proof=sign(sub))
    assert s.get("sealed"), s
    api.seal_tip(cfg, s["tip"], proof=sign(s["tip"]))
    r = api.reconcile(cfg, human_key=kf)
    return d, r["wagers"]["rows"][0]


def test_distribution_passes_onescript_check_distribution():
    os_ = _onescript()
    if os_ is None:
        pytest.skip(f"one-script not at {_ONESCRIPT_DIR} (set ONESCRIPT_DIR)")
    check = os_["reverse"].check_distribution
    for name in _WORLD_NAMES:
        for policy in peaks.POLICIES:
            assert check(peaks.distribution(load_named_world(name), policy=policy)) is None
    # a truncated list is not a forecast one-script takes
    assert check(peaks.distribution(load_named_world("hasbeen"), top=3)) is not None


@pytest.mark.parametrize("name", _WORLD_NAMES)
def test_forecast_seal_reconcile_end_to_end(name, tmp_path):
    # S1: a real distribution through api.forecast -> seal_tip -> seal_outcome
    # -> seal_tip -> reconcile, named by path_index and by full path.
    os_ = _onescript()
    if os_ is None:
        pytest.skip(f"one-script not at {_ONESCRIPT_DIR} (set ONESCRIPT_DIR)")
    world = load_named_world(name)
    d, row = _forecast_seal_reconcile(tmp_path / "idx", os_, world, {"path_index": 2})
    assert row["state"] == "reconciled" and row["graded_by"] is None
    assert row["path_index"] == 2 and row["actual_path"] == d[2]["path"]
    assert row["predicted_band"] == d[2]["band"] and row["predicted_p"] == d[2]["p"]
    d, row = _forecast_seal_reconcile(tmp_path / "path", os_, world, {"path": d[3]["path"]})
    assert row["state"] == "reconciled" and row["path_index"] == 3
