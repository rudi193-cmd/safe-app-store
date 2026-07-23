"""
calibration.py — pure calibration math. b17: OAKOF

Dependency-free, stdlib-only, in the no-egress zone (tests/test_no_egress.py).
The vendoring pattern is utety/core/mastery.py: the ~40 lines of inference a
device actually needs, small enough to audit in one sitting.

A "pair" everywhere below is (confidence, outcome): the final P(true) the
person stated, and whether the claim turned out true.
"""
from __future__ import annotations

import math

_EPS = 1e-9

# House convention (design D3): claims are stated in the direction believed,
# so confidence lives in [0.5, 0.99]. Bins cover that range in five steps.
BIN_EDGES = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def brier(confidence: float, outcome: bool) -> float:
    """Squared distance between what you said and what happened. 0 is prophecy,
    0.25 is coin-flipping at 50%, 1.0 is confidently wrong."""
    return (confidence - (1.0 if outcome else 0.0)) ** 2


def log_score(confidence: float, outcome: bool) -> float:
    """Negative log likelihood of the outcome under your stated belief.
    Punishes confident wrongness much harder than Brier does."""
    p = confidence if outcome else 1.0 - confidence
    return -math.log(max(p, _EPS))


def bins(pairs: list[tuple[float, bool]]) -> list[dict]:
    """Reliability table: for each stated-confidence band, how often were you
    actually right? Empty bands are returned with n=0 so the mirror shows the
    whole range, not just where you've dared to speak."""
    out = []
    for lo, hi in zip(BIN_EDGES, BIN_EDGES[1:]):
        members = [(c, o) for c, o in pairs if lo <= c < hi or (hi == 1.0 and c == 1.0)]
        n = len(members)
        out.append({
            "lo": lo,
            "hi": hi,
            "n": n,
            "mean_confidence": sum(c for c, _ in members) / n if n else None,
            "hit_rate": sum(1 for _, o in members if o) / n if n else None,
        })
    return out


def summary(pairs: list[tuple[float, bool]]) -> dict:
    """The scorecard header. `overconfidence` is mean stated confidence minus
    actual hit rate: positive means you promise more than you deliver."""
    n = len(pairs)
    if not n:
        return {
            "n": 0,
            "brier": None,
            "log_score": None,
            "mean_confidence": None,
            "hit_rate": None,
            "overconfidence": None,
        }
    mean_conf = sum(c for c, _ in pairs) / n
    hit_rate = sum(1 for _, o in pairs if o) / n
    return {
        "n": n,
        "brier": sum(brier(c, o) for c, o in pairs) / n,
        "log_score": sum(log_score(c, o) for c, o in pairs) / n,
        "mean_confidence": mean_conf,
        "hit_rate": hit_rate,
        "overconfidence": mean_conf - hit_rate,
    }
