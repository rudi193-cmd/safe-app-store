"""Tests for stores/checkpoint_schedule.py — the FSRS fold-in for bite 2's
deferred scheduler (docs/design/the-forge-fsrs.md, 2026-08-11).

Written test-first, before stores/checkpoint_schedule.py existed.

**Soft-FSRS environment note.** These tests run whether or not `fsrs` is
installed: the FSRS-specific assertions (real spaced-repetition intervals) are
`skipif`'d when `fsrs` is absent, and the fixed-interval fallback test blocks
`fsrs` on purpose via a meta-path finder — the exact technique
`tests/test_checkpoint.py` uses to block Nestor. Everything else (grade map,
save/load, `is_due`/`due_at` on a given card dict) is scheduler-agnostic.
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent


def _load_schedule(mod_name: str = "checkpoint_schedule"):
    spec = importlib.util.spec_from_file_location(
        mod_name, _REPO / "stores" / "checkpoint_schedule.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


checkpoint_schedule = _load_schedule()

_HAS_FSRS = checkpoint_schedule.fsrs_available()
_needs_fsrs = pytest.mark.skipif(not _HAS_FSRS, reason="fsrs not installed in this environment")

BUILDER_A = "a" * 32
CARD_ID = "d4d60bcc-ae00-4522-a159-dc28b8485d27"  # a Nestor pair_id shape
NOW = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)


# ── grade map (D-FSRS-2) ──────────────────────────────────────────────────────

def test_grade_held_is_good_regressed_is_again():
    assert checkpoint_schedule.grade(checkpoint_schedule.OUTCOME_HELD) == 3       # Good
    assert checkpoint_schedule.grade(checkpoint_schedule.OUTCOME_REGRESSED) == 1  # Again


def test_grade_rejects_an_unknown_outcome():
    with pytest.raises(checkpoint_schedule.ScheduleError):
        checkpoint_schedule.grade("sideways")


def test_grade_engagement_seam_is_reserved_but_real():
    # bite-3 seam: held + low engagement -> Hard(2), high -> Easy(4); None -> Good(3)
    held = checkpoint_schedule.OUTCOME_HELD
    assert checkpoint_schedule.grade(held, engagement=None) == 3
    assert checkpoint_schedule.grade(held, engagement=0.1) == 2   # Hard
    assert checkpoint_schedule.grade(held, engagement=0.9) == 4   # Easy
    assert checkpoint_schedule.grade(held, engagement=0.5) == 3   # Good
    # a regression is Again regardless of engagement — you didn't hold it
    assert checkpoint_schedule.grade(checkpoint_schedule.OUTCOME_REGRESSED, engagement=0.9) == 1


# ── is_due / due_at on a given card dict (scheduler-agnostic) ─────────────────

def test_is_due_true_when_now_is_past_due():
    card = {"kind": "fixed", "due": (NOW - timedelta(days=1)).isoformat()}
    assert checkpoint_schedule.is_due(card, NOW) is True


def test_is_due_false_when_due_is_in_the_future():
    card = {"kind": "fixed", "due": (NOW + timedelta(days=1)).isoformat()}
    assert checkpoint_schedule.is_due(card, NOW) is False


def test_is_due_true_at_the_exact_boundary():
    card = {"kind": "fixed", "due": NOW.isoformat()}
    assert checkpoint_schedule.is_due(card, NOW) is True


def test_due_at_parses_the_due_field():
    card = {"kind": "fixed", "due": NOW.isoformat()}
    assert checkpoint_schedule.due_at(card) == NOW


# ── save / load round-trip (the sidecar, keyed by pair_id) ────────────────────

def test_save_then_load_card_round_trips(tmp_path):
    root = tmp_path / "checkpoints"
    card = {"kind": "fixed", "due": NOW.isoformat(), "interval_days": 4.0}
    checkpoint_schedule.save_card(BUILDER_A, CARD_ID, card, root=root)
    loaded = checkpoint_schedule.load_card(BUILDER_A, CARD_ID, root=root)
    assert loaded == card


def test_load_card_absent_is_none(tmp_path):
    root = tmp_path / "checkpoints"
    assert checkpoint_schedule.load_card(BUILDER_A, CARD_ID, root=root) is None


def test_two_cards_for_one_builder_share_a_file_but_not_a_slot(tmp_path):
    root = tmp_path / "checkpoints"
    checkpoint_schedule.save_card(BUILDER_A, "pair-1", {"kind": "fixed", "due": NOW.isoformat()}, root=root)
    checkpoint_schedule.save_card(BUILDER_A, "pair-2", {"kind": "fixed", "due": NOW.isoformat()}, root=root)
    assert checkpoint_schedule.load_card(BUILDER_A, "pair-1", root=root) is not None
    assert checkpoint_schedule.load_card(BUILDER_A, "pair-2", root=root) is not None
    # one file per builder (mirrors checkpoint_memory's one-db-per-builder)
    assert checkpoint_schedule.schedule_path(BUILDER_A, root=root).exists()


def test_save_card_rejects_a_bad_builder_id(tmp_path):
    root = tmp_path / "checkpoints"
    with pytest.raises(checkpoint_schedule.ScheduleError):
        checkpoint_schedule.save_card("../escape", CARD_ID, {"kind": "fixed", "due": NOW.isoformat()}, root=root)


# ── real FSRS: intervals actually adapt (skipped if fsrs absent) ──────────────

@_needs_fsrs
def test_first_held_review_makes_a_real_fsrs_card_due_in_the_future():
    card = checkpoint_schedule.record_review(None, checkpoint_schedule.OUTCOME_HELD, NOW)
    assert card["kind"] == "fsrs"
    assert checkpoint_schedule.due_at(card) > NOW


@_needs_fsrs
def test_a_second_held_review_pushes_the_interval_further_out_than_the_first():
    first = checkpoint_schedule.record_review(None, checkpoint_schedule.OUTCOME_HELD, NOW)
    # review the SAME card again, a day later, still holding
    later = NOW + timedelta(days=1)
    second = checkpoint_schedule.record_review(first, checkpoint_schedule.OUTCOME_HELD, later)
    # the second review's next-due sits further from its review time than the
    # first's did — the memory strengthened (stability grew)
    first_gap = checkpoint_schedule.due_at(first) - NOW
    second_gap = checkpoint_schedule.due_at(second) - later
    assert second_gap > first_gap


@_needs_fsrs
def test_a_regression_resets_stability_below_a_held_streak(tmp_path):
    # build a small held streak, then regress, and confirm the regressed card's
    # stability is lower than the streak's (FSRS Again is a lapse/reset)
    c1 = checkpoint_schedule.record_review(None, checkpoint_schedule.OUTCOME_HELD, NOW)
    c2 = checkpoint_schedule.record_review(c1, checkpoint_schedule.OUTCOME_HELD, NOW + timedelta(days=2))
    regressed = checkpoint_schedule.record_review(c2, checkpoint_schedule.OUTCOME_REGRESSED, NOW + timedelta(days=3))
    assert regressed["card"]["stability"] < c2["card"]["stability"]


# ── soft-FSRS fallback: fixed intervals when fsrs is absent ───────────────────

@contextlib.contextmanager
def _fsrs_blocked():
    saved = {name: mod for name, mod in sys.modules.items() if name == "fsrs" or name.startswith("fsrs.")}
    for name in saved:
        del sys.modules[name]

    class _BlockFsrs:
        def find_spec(self, name, path, target=None):
            if name == "fsrs" or name.startswith("fsrs."):
                raise ImportError(f"blocked for test: {name}")
            return None

    finder = _BlockFsrs()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(saved)


def test_fallback_when_fsrs_absent_uses_fixed_intervals_that_grow_and_reset():
    with _fsrs_blocked():
        fresh = _load_schedule("checkpoint_schedule_fallback_probe")
        assert fresh.fsrs_available() is False

        held1 = fresh.record_review(None, fresh.OUTCOME_HELD, NOW)
        assert held1["kind"] == "fixed"
        i1 = held1["interval_days"]
        assert i1 == fresh.FIXED_BASE_INTERVAL_DAYS

        held2 = fresh.record_review(held1, fresh.OUTCOME_HELD, NOW + timedelta(days=i1))
        assert held2["interval_days"] > i1  # a held review grows the interval

        regressed = fresh.record_review(held2, fresh.OUTCOME_REGRESSED, NOW + timedelta(days=10))
        assert regressed["interval_days"] == fresh.FIXED_BASE_INTERVAL_DAYS  # reset

    # fsrs usable again right after, same process
    assert checkpoint_schedule.fsrs_available() is _HAS_FSRS


def test_is_due_reads_a_fallback_card_the_same_way(tmp_path):
    # a fixed-kind card and an fsrs-kind card are both just "has a due field"
    fixed = {"kind": "fixed", "due": (NOW - timedelta(seconds=1)).isoformat()}
    assert checkpoint_schedule.is_due(fixed, NOW) is True
