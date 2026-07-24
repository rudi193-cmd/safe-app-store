# b17: SUBSCR  ΔΣ=42
"""
subscriptions.py — recurring-charge detector. Core, PURE, no network.

A pass over the existing transactions: no new data source, stdlib only. The
whole module is deterministic — "today" is injected as a parameter so the same
transactions always yield the same detections. The seam points inward only:
nothing here reaches for a socket.

Pipeline (per the subscription-detector card):
  1. Consider only outflows (amount < 0). Normalize the merchant from the
     description — lowercase, collapse whitespace, strip store numbers, ref/auth
     codes and embedded dates ('NETFLIX #1234' / 'NETFLIX 07/24' -> 'netflix').
  2. Group by normalized merchant, then cluster within a group by amount
     tolerance (max of 5% or $1) so price hikes don't split one subscription.
  3. Infer cadence from the median gap between sorted charge dates; bucket to
     weekly / biweekly / monthly / quarterly / annual. Require >=3 occurrences
     (>=2 for annual, where history is thin).
  4. Score confidence from interval regularity and amount stability.
  5. Derive next-expected, monthly-equivalent, annualized, and a status of
     'active' or 'possibly_cancelled'.
  6. Respect category: housing / rent / mortgage / debt / loan are recurring
     but not subscriptions — they are excluded from the results.
"""
from __future__ import annotations

import re
import statistics
from datetime import date, timedelta

# ── Merchant normalization ────────────────────────────────────────────────────

# MM/DD, MM/DD/YY, MM-DD-YYYY, YYYY-MM-DD, etc.
_DATE_RE = re.compile(r"\b\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?\b")
# '#1234' style store numbers
_STORE_NUM_RE = re.compile(r"#\s*\w+")
# ref/auth/confirmation/trace codes and the token that trails them
_CODE_KW_RE = re.compile(
    r"\b(?:ref|auth|authorization|conf|confirmation|trace|txn|trans|invoice|inv|id|no)\b"
    r"[:#]?\s*\w*",
    re.IGNORECASE,
)

# Categories that are recurring but are NOT subscriptions.
_EXCLUDED_CATEGORY_RE = re.compile(
    r"hous|rent|mortgage|debt|loan", re.IGNORECASE
)

# ── Cadence buckets ───────────────────────────────────────────────────────────

_CADENCE_BUCKETS = (
    ("weekly", 6, 8),
    ("biweekly", 13, 16),
    ("monthly", 26, 35),
    ("quarterly", 85, 95),
    ("annual", 350, 380),
)
_MIN_OCCURRENCES = {"annual": 2}  # everything else defaults to 3
_DEFAULT_MIN_OCCURRENCES = 3

_DAYS_PER_YEAR = 365.25
_DAYS_PER_MONTH = _DAYS_PER_YEAR / 12.0

# Fraction of variation in amount above which a sub is reported as a range.
_VARIABLE_AMOUNT_CV = 0.05
# Weighting of the confidence blend.
_INTERVAL_WEIGHT = 0.65
_AMOUNT_WEIGHT = 0.35


def normalize_merchant(description: str) -> str:
    """Collapse a raw statement description to a stable merchant identity.

    'NETFLIX #1234' and 'NETFLIX 07/24' both become 'netflix'. Tokens carrying
    digits (store numbers, auth codes, embedded dates) are dropped; what remains
    is the alphabetic core of the name.
    """
    s = (description or "").lower()
    s = _DATE_RE.sub(" ", s)
    s = _STORE_NUM_RE.sub(" ", s)
    s = _CODE_KW_RE.sub(" ", s)
    # Punctuation to spaces; keep '&' which is part of some merchant names.
    s = re.sub(r"[^a-z0-9&\s]", " ", s)
    tokens = [t for t in s.split() if not any(ch.isdigit() for ch in t)]
    return " ".join(tokens).strip()


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ── Detection primitives ──────────────────────────────────────────────────────

def _classify_cadence(median_gap: float) -> str | None:
    for name, lo, hi in _CADENCE_BUCKETS:
        if lo <= median_gap <= hi:
            return name
    return None


def _confidence(gaps: list[int], amounts: list[float]) -> float:
    """Blend interval regularity and amount stability into 0..1."""
    if gaps:
        mean_gap = statistics.fmean(gaps)
        gap_cv = statistics.pstdev(gaps) / mean_gap if mean_gap else 1.0
    else:
        gap_cv = 1.0
    interval_score = max(0.0, 1.0 - gap_cv)

    if amounts:
        mean_amt = statistics.fmean(amounts)
        amt_cv = statistics.pstdev(amounts) / mean_amt if mean_amt else 0.0
    else:
        amt_cv = 0.0
    amount_score = max(0.0, 1.0 - amt_cv)

    blended = _INTERVAL_WEIGHT * interval_score + _AMOUNT_WEIGHT * amount_score
    return max(0.0, min(1.0, blended))


def _cluster_by_amount(charges: list[dict]) -> list[list[dict]]:
    """Split a merchant's charges into amount clusters. Adjacent amounts within
    max(5%, $1) of one another stay together, so a price hike or FX drift does
    not fracture one subscription; genuinely distinct plans separate."""
    ordered = sorted(charges, key=lambda c: c["amount_abs"])
    clusters: list[list[dict]] = [[ordered[0]]]
    for charge in ordered[1:]:
        ref = clusters[-1][-1]["amount_abs"]
        tol = max(0.05 * ref, 1.0)
        if charge["amount_abs"] - ref <= tol:
            clusters[-1].append(charge)
        else:
            clusters.append([charge])
    return clusters


def _detect_one(charges: list[dict], merchant: str, today: date) -> dict | None:
    """Turn a set of same-merchant charges into a subscription record, or None
    if they are too few or too irregular to call a subscription."""
    ordered = sorted(charges, key=lambda c: c["date"])
    dates = [c["date"] for c in ordered]
    if len(dates) < 2:
        return None

    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    gaps = [g for g in gaps if g > 0]  # drop same-day duplicates
    if not gaps:
        return None

    median_gap = statistics.median(gaps)
    cadence = _classify_cadence(median_gap)
    if cadence is None:
        return None

    occurrences = len(dates)
    if occurrences < _MIN_OCCURRENCES.get(cadence, _DEFAULT_MIN_OCCURRENCES):
        return None

    amounts = [c["amount_abs"] for c in ordered]
    mean_amt = statistics.fmean(amounts)
    amt_cv = statistics.pstdev(amounts) / mean_amt if mean_amt else 0.0
    variable = amt_cv > _VARIABLE_AMOUNT_CV

    interval = int(round(median_gap))
    last_charge = dates[-1]
    next_expected = last_charge + timedelta(days=interval)

    # Lapsed: we are already a full interval past the next expected charge.
    if today > next_expected + timedelta(days=interval):
        status = "possibly_cancelled"
    else:
        status = "active"

    monthly_equivalent = mean_amt * _DAYS_PER_MONTH / median_gap
    annualized = mean_amt * _DAYS_PER_YEAR / median_gap

    record = {
        "normalized_merchant": merchant,
        "cadence": cadence,
        "amount": None if variable else round(statistics.median(amounts), 2),
        "amount_range": [round(min(amounts), 2), round(max(amounts), 2)] if variable else None,
        "occurrences": occurrences,
        "last_charge": last_charge.isoformat(),
        "next_expected": next_expected.isoformat(),
        "monthly_equivalent": round(monthly_equivalent, 2),
        "annualized": round(annualized, 2),
        "confidence": round(_confidence(gaps, amounts), 3),
        "status": status,
    }
    return record


def _subs_for_group(charges: list[dict], merchant: str, today: date,
                    min_confidence: float) -> list[dict]:
    """Detect subscriptions within one merchant. Try amount clusters first (two
    real plans at the same merchant separate cleanly); if no cluster qualifies,
    fall back to the whole group as one variable/usage-metered subscription."""
    results: list[dict] = []
    for cluster in _cluster_by_amount(charges):
        sub = _detect_one(cluster, merchant, today)
        if sub and sub["confidence"] >= min_confidence:
            results.append(sub)
    if not results:
        sub = _detect_one(charges, merchant, today)
        if sub and sub["confidence"] >= min_confidence:
            results.append(sub)
    return results


# ── Public API ────────────────────────────────────────────────────────────────

def detect_subscriptions(transactions: list[dict], today: date,
                         min_confidence: float = 0.5) -> list[dict]:
    """Detect recurring subscriptions in a list of transaction dicts.

    Each transaction needs at least: date ('YYYY-MM-DD'), amount (signed float,
    negative = outflow), description (str), category (str | None). Deterministic:
    the result depends only on ``transactions`` and ``today``.
    """
    groups: dict[str, list[dict]] = {}
    for tx in transactions:
        amount = tx.get("amount")
        if amount is None or amount >= 0:  # inflows and zeroes are not subs
            continue
        category = tx.get("category") or ""
        if _EXCLUDED_CATEGORY_RE.search(category):  # rent / mortgage / loan / debt
            continue
        merchant = normalize_merchant(tx.get("description", ""))
        if not merchant:
            continue
        parsed = _parse_date(tx.get("date"))
        if parsed is None:
            continue
        groups.setdefault(merchant, []).append(
            {"merchant": merchant, "date": parsed, "amount_abs": abs(float(amount))}
        )

    subs: list[dict] = []
    for merchant, charges in groups.items():
        subs.extend(_subs_for_group(charges, merchant, today, min_confidence))

    # Deterministic order: biggest annual commitment first, then merchant name.
    subs.sort(key=lambda s: (-s["annualized"], s["normalized_merchant"]))
    return subs


def from_db(db, today: date | None = None, limit: int = 2000,
            min_confidence: float = 0.5) -> list[dict]:
    """Convenience wrapper: pull recent transactions from a LedgerDB and detect.

    ``today`` defaults to the real calendar date here only because this is the
    outward convenience seam; the pure core (:func:`detect_subscriptions`)
    always takes an explicit ``today``.
    """
    if today is None:
        today = date.today()
    rows = db.get_transactions(limit=limit)
    transactions = [dict(row) for row in rows]
    return detect_subscriptions(transactions, today, min_confidence=min_confidence)
