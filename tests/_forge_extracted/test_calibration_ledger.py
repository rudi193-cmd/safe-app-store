"""Tests for stores/calibration_ledger.py — the model's confidence mirror
(docs/design/the-forge-measure.md, the `calibration` class).

A prediction is a (confidence, outcome) pair the model states while building;
the ledger grades stated confidence against ground truth with the vendored
oakenscrolls calibration math, and routes ONE deduped `review` nudge when the
model is measurably overconfident — never blocking. Pure: soil_store +
vendored calibration + governance's route_nudge, no Nestor/fsrs.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "calibration_ledger", _REPO / "stores" / "calibration_ledger.py"
)
led = importlib.util.module_from_spec(_spec)
sys.modules["calibration_ledger"] = led
_spec.loader.exec_module(led)

governance = led.governance
BUILDER = "b" * 32


# ── record → resolve → score lifecycle ───────────────────────────────────────

def test_record_then_resolve_then_scorecard(tmp_path):
    root = tmp_path / "checkpoints"
    rec = led.record_prediction(BUILDER, "app.py parses", 0.9, root=root)
    assert rec["resolved"] is False and rec["outcome"] is None

    card = led.scorecard(BUILDER, root=root)
    assert card["pending"] == 1 and card["resolved"] == 0
    assert card["summary"]["n"] == 0  # nothing to grade until it settles

    led.resolve_prediction(BUILDER, rec["id"], True, root=root)
    card = led.scorecard(BUILDER, root=root)
    assert card["pending"] == 0 and card["resolved"] == 1
    assert card["summary"]["n"] == 1
    assert card["summary"]["hit_rate"] == 1.0


def test_same_claim_updates_the_pending_prediction_not_duplicates(tmp_path):
    root = tmp_path / "checkpoints"
    a = led.record_prediction(BUILDER, "the design holds", 0.7, root=root)
    b = led.record_prediction(BUILDER, "the design holds", 0.85, root=root)  # refined before truth
    assert a["id"] == b["id"]  # same claim → same prediction id
    card = led.scorecard(BUILDER, root=root)
    assert card["pending"] == 1  # one prediction, not two
    # the later confidence is what stands
    led.resolve_prediction(BUILDER, b["id"], True, root=root)
    assert led.scorecard(BUILDER, root=root)["summary"]["mean_confidence"] == 0.85


def test_explicit_ids_keep_two_same_text_claims_separate(tmp_path):
    root = tmp_path / "checkpoints"
    led.record_prediction(BUILDER, "it works", 0.9, prediction_id="p1", root=root)
    led.record_prediction(BUILDER, "it works", 0.9, prediction_id="p2", root=root)
    assert led.scorecard(BUILDER, root=root)["pending"] == 2


# ── the guards an adversarial audit looks for ────────────────────────────────

def test_confidence_below_half_is_rejected_not_clamped(tmp_path):
    # a claim believed FALSE is a true-claim restated, not a weak 'true' (D3)
    root = tmp_path / "checkpoints"
    with pytest.raises(led.CalibrationLedgerError):
        led.record_prediction(BUILDER, "probably false", 0.3, root=root)
    with pytest.raises(led.CalibrationLedgerError):
        led.record_prediction(BUILDER, "impossible", 1.5, root=root)
    # nothing was written by the rejected calls
    assert led.scorecard(BUILDER, root=root)["pending"] == 0


def test_cannot_re_record_a_resolved_prediction(tmp_path):
    root = tmp_path / "checkpoints"
    rec = led.record_prediction(BUILDER, "settled claim", 0.8, root=root)
    led.resolve_prediction(BUILDER, rec["id"], False, root=root)
    with pytest.raises(led.CalibrationLedgerError):
        led.record_prediction(BUILDER, "settled claim", 0.6, root=root)  # would rewrite history
    # the resolved outcome is untouched
    card = led.scorecard(BUILDER, root=root)
    assert card["resolved"] == 1 and card["summary"]["hit_rate"] == 0.0


def test_double_resolve_is_refused(tmp_path):
    root = tmp_path / "checkpoints"
    rec = led.record_prediction(BUILDER, "one shot", 0.9, root=root)
    led.resolve_prediction(BUILDER, rec["id"], True, root=root)
    with pytest.raises(led.CalibrationLedgerError):
        led.resolve_prediction(BUILDER, rec["id"], False, root=root)


def test_resolving_an_unknown_prediction_is_refused(tmp_path):
    root = tmp_path / "checkpoints"
    with pytest.raises(led.CalibrationLedgerError):
        led.resolve_prediction(BUILDER, "no-such-id", True, root=root)


# ── the overconfidence signal ────────────────────────────────────────────────

def _seed(root, pairs, builder=BUILDER):
    for i, (conf, outcome) in enumerate(pairs):
        rec = led.record_prediction(builder, f"claim {i}", conf, prediction_id=f"p{i}", root=root)
        led.resolve_prediction(builder, rec["id"], outcome, root=root)


def test_thin_record_does_not_route(tmp_path):
    root = tmp_path / "checkpoints"
    _seed(root, [(0.95, False), (0.95, False)])  # wildly overconfident but only n=2
    assert led.overconfidence_signal(BUILDER, root=root) is None
    assert len(governance.open_items(BUILDER, root=root, kind='review')) == 0


def test_well_calibrated_model_does_not_route(tmp_path):
    root = tmp_path / "checkpoints"
    # says ~0.8, hits ~0.8 → overconfidence ~0, well past min_n
    _seed(root, [(0.8, True)] * 4 + [(0.8, False)])
    sig = led.overconfidence_signal(BUILDER, root=root)
    assert sig is None


def test_sustained_overconfidence_routes_one_deduped_review(tmp_path):
    root = tmp_path / "checkpoints"
    _seed(root, [(0.9, False)] * 3 + [(0.9, True)] * 2)  # says 0.9, hits 0.4
    card = led.scorecard(BUILDER, root=root)
    assert card["summary"]["overconfidence"] >= led.OVERCONFIDENCE_FLOOR

    first = led.overconfidence_signal(BUILDER, root=root)
    assert first is not None and first["kind"] == "review"
    # deduped: a second call while the flag is open does not pile up a row
    assert led.overconfidence_signal(BUILDER, root=root) is None
    assert len(governance.open_items(BUILDER, root=root, kind='review')) == 1


def test_signal_never_blocks_and_is_isolated_per_builder(tmp_path):
    root = tmp_path / "checkpoints"
    other = "c" * 32
    _seed(root, [(0.99, False)] * 5, builder=BUILDER)  # overconfident builder
    _seed(root, [(0.8, True)] * 5, builder=other)      # calibrated builder
    assert led.overconfidence_signal(BUILDER, root=root) is not None
    assert led.overconfidence_signal(other, root=root) is None
    # each builder's records live in its own file — the calibrated one is clean
    assert led.scorecard(other, root=root)["summary"]["overconfidence"] <= 0
