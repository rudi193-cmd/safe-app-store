"""Reproduce the caption-dimensionality figures quoted in docs/BUILD_PLAN.md.

The claim under test: the DCI sheet is close to one-dimensional, so a model
fitted to it would learn placement and present it as eight independent
judgements. That is the evidence half of the "measurement is not evaluation"
decision — the values half stands on its own.

METHOD, and why it is this one. Correlations are computed on ranks *within* each
(year, round) sheet. An earlier pass residualised each caption on the composed
total instead. That is arithmetically valid and produces a false answer: when
components sum to the total you subtract, the residuals are forced to correlate
negatively regardless of the underlying agreement. It reported GE1 vs GE2 at
-0.24 — a startling finding of judge independence that does not exist. The true
value is +0.988. Do not residualise on an aggregate the inputs compose.

Usage:  python tools/caption_dimensionality.py path/to/dci_scores.db

Stdlib only. Reads; never writes.
"""
from __future__ import annotations

import collections
import sqlite3
import statistics as st
import sys

# Pairs chosen to test separation at three levels: within GE, within a single
# discipline's two judges, and across the two top-level captions.
PAIRS = [
    ("ge1", "ge2", "within GE"),
    ("brass", "mus_analysis", "within music"),
    ("vis_prof", "vis_analysis", "within visual"),
    ("ge", "visual", "across captions"),
]

MIN_SHEET = 5  # a rank correlation over four corps is noise


def _ranks(values: list[float]) -> list[int]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0] * len(values)
    for position, index in enumerate(order):
        out[index] = position
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    a, b = _ranks(xs), _ranks(ys)
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den


def main(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM captions").fetchall()

    # One sheet = one (year, round). Ranking across years would mix scoring eras.
    sheets = collections.defaultdict(list)
    for row in rows:
        sheets[(row["year"], row["round"])].append(row)
    scored = [s for s in sheets.values() if len(s) >= MIN_SHEET]

    print(f"{len(rows)} caption rows, {len(scored)} sheets of >= {MIN_SHEET}\n")
    print(f"{'pair':<34}{'mean rho':>10}{'worst':>9}   scope")
    for left, right, scope in PAIRS:
        rhos = [spearman([r[left] for r in s], [r[right] for r in s]) for s in scored]
        print(f"{left + ' ~ ' + right:<34}{st.mean(rhos):>10.3f}{min(rhos):>9.3f}   {scope}")

    semis = [r for r in rows if r["round"] == "semifinals"]
    print(f"\nspread, {len(semis)} semifinals rows")
    for caption in ("ge", "visual", "music"):
        values = [r[caption] for r in semis]
        print(f"  {caption:<8} sd {st.pstdev(values):.3f}   "
              f"range {min(values):.2f}-{max(values):.2f}")

    print("\n12th-place semifinals cutoff (the margin a director reads first)")
    cutoffs = conn.execute(
        "SELECT e.year, r.score FROM results r JOIN events e USING (event_id) "
        "WHERE e.event_type = 'semifinals' AND r.place = 12 ORDER BY e.year"
    ).fetchall()
    for year, score in cutoffs:
        print(f"  {year}  {score:.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
