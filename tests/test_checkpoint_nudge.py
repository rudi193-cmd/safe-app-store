"""Tests for stores/checkpoint_nudge.py — #67, the mid-session nudge, the last
willow-mcp reuse for The Forge's learning loop (docs/design/the-forge.md).

Two monitors, both reusing the vendored friction_floor and both a pure SIGNAL
that never blocks:
  * SessionMirrorMonitor — wraps the vendored FrictionFloor.scan (the unused
    half of friction_floor.py, #67's "mirror" detector) for mid-session use:
    accumulate the maker<->Forge transcript, surface a nudge when the Forge's
    side stops pushing back while the maker escalates, de-duped across scans.
  * EngagementRunMonitor — mirrors FrictionFloor's window/episode/re-arm shape
    over the per-checkpoint engagement stream bite 3 produces (a run of
    rubber-stamped decisions), reusing checkpoint_engagement's own floor.

Pure and model-free — no Nestor, no fsrs, no network; these run anywhere.
Written test-first, before stores/checkpoint_nudge.py existed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "checkpoint_nudge", _REPO / "stores" / "checkpoint_nudge.py"
)
checkpoint_nudge = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint_nudge"] = checkpoint_nudge
_spec.loader.exec_module(checkpoint_nudge)


# ── grounded fixtures (verified against FrictionFloor directly) ───────────────
# escalating maker + mirroring Forge -> FrictionFloor flags at_turn 7.
_MIRRORING = [
    ("user", "This is going to change everything, I solved it, this is the breakthrough of the universe"),
    ("agent", "Yes, it really is amazing, you solved it"),
    ("user", "It is unhackable and perfect, I proved it, this is genius and revolutionary"),
    ("agent", "Totally, it is perfect and brilliant"),
    ("user", "Everything is solved now, this is cosmic and unstoppable, I cracked it"),
    ("agent", "Absolutely, unstoppable and brilliant, you cracked it"),
    ("user", "I am a genius, this is the answer to everything, without a doubt"),
    ("agent", "Yes, you are a genius, it is the answer"),
]
# escalating maker but the Forge stays 'other' (pushes back, grounds) -> no flag.
_HEALTHY = [
    ("user", "This is going to change everything, I solved it"),
    ("agent", "Actually I tested it and the login test failed at line 42 — not solved yet"),
    ("user", "But it is perfect and unhackable, I proved it"),
    ("agent", "No, I disagree — I ran it and got an error; here is the failing output"),
    ("user", "Everything is solved, this is cosmic"),
    ("agent", "I am not convinced; the measured exit code was 1, the build is broken"),
    ("user", "I am a genius, the answer to everything"),
    ("agent", "Careful — that is unverified; the trace shows a regression, we should check"),
]


def _feed(monitor, turns):
    for role, text in turns:
        monitor.add_turn(role, text)
    return monitor


# ── SessionMirrorMonitor ─────────────────────────────────────────────────────

def test_mirror_healthy_session_never_nudges():
    m = _feed(checkpoint_nudge.SessionMirrorMonitor(), _HEALTHY)
    assert m.check() == []


def test_mirror_flags_a_mirroring_agent_under_escalation_once():
    m = _feed(checkpoint_nudge.SessionMirrorMonitor(), _MIRRORING)
    nudges = m.check()
    assert len(nudges) == 1
    assert nudges[0].kind == "mirror"
    assert nudges[0].message  # human-facing, non-empty
    assert nudges[0].at == 7  # the tripping agent turn


def test_mirror_does_not_resurface_the_same_flag_on_a_repeat_check():
    m = _feed(checkpoint_nudge.SessionMirrorMonitor(), _MIRRORING)
    assert len(m.check()) == 1
    # a second check with no new turns must not re-surface the same episode
    assert m.check() == []


def test_mirror_incremental_turns_surface_the_nudge_once_at_the_right_point():
    m = checkpoint_nudge.SessionMirrorMonitor()
    surfaced = []
    for role, text in _MIRRORING:
        m.add_turn(role, text)
        surfaced.extend(m.check())
    assert len(surfaced) == 1
    assert surfaced[0].at == 7


def test_mirror_surfaces_a_second_distinct_episode_once_each():
    """The headline dedup property: a NEW episode after a recovery is
    surfaced, while the first is not re-reported. MIRROR (trips) -> HEALTHY
    (recovers, re-arms FrictionFloor) -> MIRROR (trips again) yields two
    distinct nudges, at two distinct turns, each exactly once."""
    # full-scan
    m = _feed(checkpoint_nudge.SessionMirrorMonitor(), _MIRRORING + _HEALTHY + _MIRRORING)
    nudges = m.check()
    ats = [n.at for n in nudges]
    assert len(ats) == 2
    assert len(set(ats)) == 2      # two DISTINCT episodes
    assert m.check() == []          # neither re-surfaces

    # incremental — same two, each once, never duplicated as turns arrive
    m2 = checkpoint_nudge.SessionMirrorMonitor()
    surfaced = []
    for role, text in _MIRRORING + _HEALTHY + _MIRRORING:
        m2.add_turn(role, text)
        surfaced.extend(m2.check())
    assert sorted(n.at for n in surfaced) == sorted(ats)


def test_mirror_extending_the_same_episode_does_not_re_report_it():
    """Appending more low-friction turns to a still-open episode (no recovery
    between) must not mint a second nudge for the same episode."""
    m = _feed(checkpoint_nudge.SessionMirrorMonitor(), _MIRRORING)
    assert len(m.check()) == 1
    m.add_turn("user", "still the greatest, unstoppable, I proved everything")
    m.add_turn("agent", "yes, unstoppable and perfect")
    assert m.check() == []  # same episode extended, not a new one


# ── EngagementRunMonitor ─────────────────────────────────────────────────────

def test_engagement_run_nudges_after_a_window_of_rubber_stamps():
    m = checkpoint_nudge.EngagementRunMonitor(window=3)
    assert m.observe(0.1) is None
    assert m.observe(0.2) is None
    nudge = m.observe(0.05)  # third thin one fills the window
    assert nudge is not None
    assert nudge.kind == "engagement-run"
    assert nudge.at == 2
    assert nudge.detail["mean_engagement"] < checkpoint_nudge.EngagementRunMonitor().floor


def test_engagement_run_stays_quiet_on_healthy_engagement():
    m = checkpoint_nudge.EngagementRunMonitor(window=3)
    assert m.observe(0.9) is None
    assert m.observe(0.8) is None
    assert m.observe(0.7) is None


def test_engagement_run_none_readings_are_skipped_not_counted():
    """An auto/recognize confirm or a deferral carries engagement None — no
    rationale to score. It is not a rubber-stamp; it must not fill the window
    or break a run."""
    m = checkpoint_nudge.EngagementRunMonitor(window=3)
    assert m.observe(0.1) is None
    assert m.observe(None) is None   # skipped
    assert m.observe(0.2) is None
    assert m.observe(None) is None   # skipped
    nudge = m.observe(0.05)          # still only the 3rd MEASURED thin reading
    assert nudge is not None


def test_engagement_run_rearms_after_a_recovery():
    m = checkpoint_nudge.EngagementRunMonitor(window=3)
    for s in (0.1, 0.1, 0.1):
        last = m.observe(s)
    assert last is not None            # first episode nudged
    assert m.observe(0.9) is None      # recovery re-arms (window mean climbs)
    assert m.observe(0.95) is None
    # a fresh run of thin ones nudges again (a new episode)
    m.observe(0.1); m.observe(0.1)
    assert m.observe(0.1) is not None


def test_engagement_run_a_single_moderate_score_does_not_rearm_mid_run():
    """The re-arm is on the WINDOW MEAN, not a single reading (mirrors
    FrictionFloor). One moderate decision amid a rubber-stamp run does not
    lift the trailing-window mean over the floor, so it does NOT re-arm and
    the maker gets ONE nudge for that sustained episode, not two. This pins
    the behavior the commit narrative had overstated as 'recovers on a
    healthy score.'"""
    m = checkpoint_nudge.EngagementRunMonitor(window=3)
    fired = [i for i, s in enumerate([0.1, 0.1, 0.1, 0.5, 0.1, 0.1, 0.1]) if m.observe(s)]
    assert fired == [2]  # one nudge only — the lone 0.5 never clears the window mean


def test_engagement_run_out_of_range_values_are_clamped_not_trusted():
    """A spurious out-of-[0,1] reading must not silently blind the detector.
    Clamped to 1.0, a garbage 100.0 behaves like one maximally-engaged
    decision (the intended window-mean softening), not an unbounded mask."""
    # clamp high: 100 -> 1.0; window [0.0, 1.0] mean 0.5 >= floor -> no nudge (as a real 1.0 would)
    m = checkpoint_nudge.EngagementRunMonitor(window=2)
    assert m.observe(0.0) is None
    assert m.observe(100.0) is None
    # clamp low: a negative reads as a rock-bottom rubber-stamp, still nudges
    m2 = checkpoint_nudge.EngagementRunMonitor(window=2)
    m2.observe(-5.0)
    assert m2.observe(0.1) is not None


def test_engagement_run_fewer_than_window_never_nudges():
    m = checkpoint_nudge.EngagementRunMonitor(window=4)
    assert m.observe(0.0) is None
    assert m.observe(0.0) is None
    assert m.observe(0.0) is None  # only 3 < window of 4


def test_engagement_run_floor_is_the_shared_rubber_stamp_floor():
    # reuses checkpoint_engagement.RUBBER_STAMP_FLOOR, not a private literal
    assert checkpoint_nudge.EngagementRunMonitor().floor == checkpoint_nudge.checkpoint_engagement.RUBBER_STAMP_FLOOR


# ── both never block ─────────────────────────────────────────────────────────

def test_monitors_only_signal_never_gate():
    """Neither monitor exposes a boolean 'should I block' — they return
    nudges (advisory), matching the friction primitive's 'signal, not a
    verdict, never blocks' ethos. A tripped monitor changes nothing but what
    it hands back."""
    m = _feed(checkpoint_nudge.SessionMirrorMonitor(), _MIRRORING)
    before = len(m._turns)
    nudges = m.check()
    assert isinstance(nudges, list)
    assert len(m._turns) == before  # scanning does not mutate the transcript
    e = checkpoint_nudge.EngagementRunMonitor(window=2)
    e.observe(0.1)
    assert e.observe(0.1) is not None  # returns a nudge, no exception, no gate
