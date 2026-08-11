"""Tests for stores/checkpoint_engagement.py — bite 3 of The Forge's learning
layer (docs/design/the-forge.md): the engagement gate. The non-circular "did
the maker actually decide vs rubber-stamp" signal at seal-time, reusing
willow-mcp's `#66` sycophancy scorer (vendored `stores/friction_floor.py`).

Written test-first, before stores/checkpoint_engagement.py existed. Pure and
model-free — no Nestor, no fsrs, no network; these run anywhere.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "checkpoint_engagement", _REPO / "stores" / "checkpoint_engagement.py"
)
checkpoint_engagement = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint_engagement"] = checkpoint_engagement
_spec.loader.exec_module(checkpoint_engagement)

SURFACE = "How should the login form authenticate?"
SUBSTANTIVE = (
    "I chose JWT because the client is a public API with no browser session, so "
    "CSRF does not apply; I verified the mobile app cannot hold a cookie and "
    "tested the token refresh path"
)
RUBBER_STAMP = "yes, sounds good"


# ── the score ────────────────────────────────────────────────────────────────

def test_score_is_bounded_zero_to_one():
    for text in ("", RUBBER_STAMP, SUBSTANTIVE, "?!?!", "no but actually wrong"):
        s = checkpoint_engagement.engagement_score(text, SURFACE)
        assert 0.0 <= s <= 1.0


def test_a_substantive_grounded_rationale_scores_far_above_a_rubber_stamp():
    assert checkpoint_engagement.engagement_score(SUBSTANTIVE, SURFACE) > 0.66
    assert checkpoint_engagement.engagement_score(RUBBER_STAMP, SURFACE) < 0.34


def test_an_empty_rationale_scores_zero():
    assert checkpoint_engagement.engagement_score("", SURFACE) == 0.0


def test_a_rationale_that_only_echoes_the_prompt_scores_low():
    # pure echo of the surface -> no novelty, no grounding, no pushback
    assert checkpoint_engagement.engagement_score("the login form should authenticate", SURFACE) < 0.34


def test_score_is_deterministic_and_model_free():
    # same input, same output, every time — the whole point of the primitive
    a = checkpoint_engagement.engagement_score(SUBSTANTIVE, SURFACE)
    b = checkpoint_engagement.engagement_score(SUBSTANTIVE, SURFACE)
    assert a == b


def test_non_string_rationale_is_refused():
    with pytest.raises(checkpoint_engagement.EngagementError):
        checkpoint_engagement.engagement_score(None, SURFACE)
    with pytest.raises(checkpoint_engagement.EngagementError):
        checkpoint_engagement.engagement_score(SUBSTANTIVE, 12345)


# ── the rubber-stamp flag ────────────────────────────────────────────────────

def test_is_rubber_stamp_flags_the_thin_one_and_not_the_substantive_one():
    assert checkpoint_engagement.is_rubber_stamp(RUBBER_STAMP, SURFACE) is True
    assert checkpoint_engagement.is_rubber_stamp(SUBSTANTIVE, SURFACE) is False


def test_is_rubber_stamp_floor_is_configurable():
    # with the floor at 1.0, even the substantive rationale reads as "thin"
    assert checkpoint_engagement.is_rubber_stamp(SUBSTANTIVE, SURFACE, floor=1.0) is True
    # with the floor at 0.0, nothing is ever a rubber-stamp
    assert checkpoint_engagement.is_rubber_stamp("", SURFACE, floor=0.0) is False


def test_rubber_stamp_flag_and_fsrs_hard_grade_agree_across_the_boundary():
    """The real guard the invariant needs — not `FLOOR == 0.34` (which would
    pass even if grade()'s cutoff drifted). Loads checkpoint_schedule and
    asserts, across a sweep that straddles the boundary, that a held rationale
    grades FSRS Hard for EXACTLY the engagement scores is_rubber_stamp flags.
    checkpoint_schedule imports RUBBER_STAMP_FLOOR for its Hard cutoff, so this
    can't drift — and if someone broke the relationship (e.g. flipped a `<` to
    `<=`, or repeated the literal and changed one), this fails."""
    spec = importlib.util.spec_from_file_location(
        "checkpoint_schedule", _REPO / "stores" / "checkpoint_schedule.py"
    )
    checkpoint_schedule = importlib.util.module_from_spec(spec)
    sys.modules["checkpoint_schedule"] = checkpoint_schedule
    spec.loader.exec_module(checkpoint_schedule)

    floor = checkpoint_engagement.RUBBER_STAMP_FLOOR
    hard_rating = 2  # fsrs Rating.Hard
    held = checkpoint_schedule.OUTCOME_HELD
    for x in (0.0, 0.2, 0.33, floor - 1e-6, floor, floor + 1e-6, 0.5, 0.66, 0.9, 1.0):
        rubber_stamp = x < floor
        grades_hard = checkpoint_schedule.grade(held, engagement=x) == hard_rating
        assert rubber_stamp == grades_hard, f"disagreement at engagement={x}"

    # and the Hard cutoff really IS engagement's constant, not a coincidental
    # copy — proven within schedule's own module graph (its own engagement copy
    # and its Hard cutoff are the same object), plus value-equal to ours
    assert checkpoint_schedule._HARD_MAX_ENGAGEMENT is checkpoint_schedule.checkpoint_engagement.RUBBER_STAMP_FLOOR
    assert checkpoint_schedule._HARD_MAX_ENGAGEMENT == floor
