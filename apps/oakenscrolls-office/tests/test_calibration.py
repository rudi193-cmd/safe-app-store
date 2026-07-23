import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import calibration as cal


def test_brier_bounds():
    assert cal.brier(1.0, True) == 0.0
    assert cal.brier(1.0, False) == 1.0
    assert cal.brier(0.5, True) == cal.brier(0.5, False) == 0.25


def test_log_score_punishes_confident_wrongness():
    mild = cal.log_score(0.6, False)
    harsh = cal.log_score(0.95, False)
    assert harsh > mild > cal.log_score(0.6, True)
    assert math.isfinite(cal.log_score(1.0, False))  # eps guard


def test_bins_cover_range_and_group():
    pairs = [(0.55, True), (0.58, False), (0.92, True), (1.0, True)]
    b = cal.bins(pairs)
    assert len(b) == 5
    assert b[0]["n"] == 2 and b[0]["hit_rate"] == 0.5
    assert b[4]["n"] == 2  # 0.92 and the 1.0 edge case both land in the top bin
    assert b[1]["n"] == 0 and b[1]["hit_rate"] is None


def test_summary_overconfidence_sign():
    overconfident = [(0.9, False), (0.9, True)]   # says 90%, hits 50%
    s = cal.summary(overconfident)
    assert s["overconfidence"] > 0
    assert s["n"] == 2
    empty = cal.summary([])
    assert empty["n"] == 0 and empty["brier"] is None
