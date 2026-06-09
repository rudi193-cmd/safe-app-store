"""Verification pipeline: submit verdicts, check threshold, fire SRS events."""
from __future__ import annotations

from . import db

AGREEMENT_THRESHOLD = 2 / 3   # iNaturalist 2/3 weighted model
NATIVE_WEIGHT = 2.0
CALIBRATED_WEIGHT = 1.5        # earned at calibration_score >= 0.8
DEFAULT_WEIGHT = 1.0

# fsrs Rating ints: Again=1, Hard=2, Good=3, Easy=4
_VERDICT_RATING = {"approved": 3, "corrected": 2, "rejected": 1}


def _learner_weight(learner: dict, is_native: bool) -> float:
    if is_native:
        return NATIVE_WEIGHT
    return CALIBRATED_WEIGHT if learner.get("calibration_score", 1.0) >= 0.8 else DEFAULT_WEIGHT


def _check_threshold(segment_id: str) -> str | None:
    """Return new status string if threshold met, else None."""
    vv = db.get_verifications(segment_id)
    if not vv:
        return None

    approve_w = sum(v["weight"] for v in vv if v["verdict"] in ("approved", "corrected"))
    total_w   = sum(v["weight"] for v in vv)
    has_native = any(v["weight"] >= NATIVE_WEIGHT for v in vv)

    if total_w == 0:
        return None

    ratio = approve_w / total_w
    if ratio >= AGREEMENT_THRESHOLD:
        return "verified" if has_native else "needs_native"
    if (1.0 - ratio) > AGREEMENT_THRESHOLD:
        return "rejected"
    return None


def _fire_srs(learner_id: str, atom_id: str, verdict: str) -> None:
    if not atom_id:
        return
    try:
        import json as _json
        from fsrs import Card, Rating, Scheduler  # type: ignore

        row = db.get_or_create_card(learner_id, atom_id)
        card_dict = _json.loads(row["card_json"]) if row["card_json"] and row["card_json"] != "{}" else None
        card = Card.from_dict(card_dict) if card_dict else Card()

        rating = Rating(_VERDICT_RATING.get(verdict, 3))
        card, _ = Scheduler().review_card(card, rating)

        db.update_card(row["id"], card_json=card.to_json(), due=card.due.isoformat())
        db.create_review_event(row["id"], learner_id, _VERDICT_RATING.get(verdict, 3),
                               source="verification")
    except ImportError:
        pass


def _nudge_calibration(learner_id: str, segment_id: str, verdict: str) -> None:
    vv = db.get_verifications(segment_id)
    if len(vv) < 2:
        return
    approve = sum(1 for v in vv if v["verdict"] in ("approved", "corrected"))
    consensus_approves = approve / len(vv) >= 0.5
    learner_approves   = verdict in ("approved", "corrected")
    agrees = learner_approves == consensus_approves
    learner = db.get_learner(learner_id)
    if not learner:
        return
    cal = learner["calibration_score"]
    cal = max(0.5, min(1.5, cal + (0.02 if agrees else -0.02)))
    db.update_calibration(learner_id, cal)


def submit_verification(
    segment_id: str,
    learner_id: str,
    verdict: str,
    correction: str = "",
    is_native: bool = False,
) -> dict:
    """
    Record a human verdict on a segment.
    verdict: 'approved' | 'corrected' | 'rejected'
    Returns the updated segment dict.
    """
    learner = db.get_learner(learner_id)
    if not learner:
        raise ValueError(f"Unknown learner: {learner_id}")

    weight = _learner_weight(learner, is_native)
    db.create_verification(segment_id, learner_id, verdict, correction, weight)

    if verdict == "corrected" and correction:
        db.update_segment(segment_id, candidate=correction, status="in_review")
    else:
        db.update_segment(segment_id, status="in_review")

    new_status = _check_threshold(segment_id)
    if new_status:
        db.update_segment(segment_id, status=new_status)

    seg = db.get_segment(segment_id) or {}
    _fire_srs(learner_id, seg.get("atom_id", ""), verdict)
    _nudge_calibration(learner_id, segment_id, verdict)
    return seg


def get_queue(limit: int = 50) -> list[dict]:
    """Pending segments, uncertain first (lowest jeles_score)."""
    return db.get_pending_segments(limit=limit)
