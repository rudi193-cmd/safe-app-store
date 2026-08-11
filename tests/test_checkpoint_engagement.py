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


def test_rubber_stamp_floor_aligns_with_the_fsrs_hard_grade_cutoff():
    # the default floor is the same line grade() uses for Hard (engagement <
    # 0.34 -> Hard), so "rubber_stamp" and "would grade Hard" never disagree
    assert checkpoint_engagement.RUBBER_STAMP_FLOOR == pytest.approx(0.34)
