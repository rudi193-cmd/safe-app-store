"""Subscription detector — synthetic transactions, pure and deterministic.

Runs WITHOUT textual: imports only the core subscriptions module.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from private_ledger import subscriptions  # noqa: E402

TODAY = date(2026, 7, 24)


def _monthly(desc, amount, category, start, count, day=5):
    """count monthly charges on the given day-of-month, ending most recently."""
    out = []
    y, m = start
    for _ in range(count):
        out.append({
            "date": date(y, m, day).isoformat(),
            "amount": amount,
            "description": desc,
            "category": category,
        })
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _build():
    txns = []
    # Monthly Netflix — 12x $9.99, description carries a store number each time.
    txns += _monthly("NETFLIX #1234", -9.99, "Entertainment", (2025, 8), 12)
    # Annual domain renewal — 2x, thin history, ~365d apart.
    txns.append({"date": "2024-06-10", "amount": -14.99,
                 "description": "NAMECHEAP DOMAIN RENEWAL",
                 "category": "Other"})
    txns.append({"date": "2025-06-11", "amount": -14.99,
                 "description": "NAMECHEAP DOMAIN RENEWAL",
                 "category": "Other"})
    # Variable usage-metered bill — monthly cadence, ranging amount.
    usage_amounts = [-42.10, -58.30, -71.05, -85.60, -96.20, -40.75]
    y, m = 2026, 2
    for amt in usage_amounts:
        txns.append({"date": date(y, m, 15).isoformat(), "amount": amt,
                     "description": "AWS CLOUD SERVICES",
                     "category": "Utilities"})
        m += 1
    # Lapsed sub — monthly, stopped ~3 intervals before today.
    txns += _monthly("SPOTIFY USA", -11.99, "Entertainment", (2026, 1), 3)
    # Monthly rent — recurring but category Housing -> excluded.
    txns += _monthly("MONTHLY RENT PAYMENT", -1500.0, "Housing", (2025, 8), 12)
    return txns


def _by_merchant(subs):
    return {s["normalized_merchant"]: s for s in subs}


def test_netflix_monthly_detected():
    subs = _by_merchant(subscriptions.detect_subscriptions(_build(), TODAY))
    assert "netflix" in subs
    nf = subs["netflix"]
    assert nf["cadence"] == "monthly"
    assert nf["amount"] == 9.99
    assert nf["occurrences"] == 12
    assert nf["status"] == "active"
    assert nf["confidence"] > 0.8


def test_annual_domain_renewal():
    subs = _by_merchant(subscriptions.detect_subscriptions(_build(), TODAY))
    assert "namecheap domain renewal" in subs
    dom = subs["namecheap domain renewal"]
    assert dom["cadence"] == "annual"
    assert dom["occurrences"] == 2  # >=2 threshold for annual


def test_variable_usage_bill_reports_range():
    subs = _by_merchant(subscriptions.detect_subscriptions(_build(), TODAY))
    assert "aws cloud services" in subs
    aws = subs["aws cloud services"]
    assert aws["cadence"] == "monthly"
    assert aws["amount"] is None
    assert aws["amount_range"][0] == 40.75
    assert aws["amount_range"][1] == 96.20


def test_lapsed_sub_flagged_possibly_cancelled():
    subs = _by_merchant(subscriptions.detect_subscriptions(_build(), TODAY))
    assert "spotify usa" in subs
    sp = subs["spotify usa"]
    assert sp["status"] == "possibly_cancelled"


def test_rent_excluded_by_category():
    subs = _by_merchant(subscriptions.detect_subscriptions(_build(), TODAY))
    assert "monthly rent payment" not in subs
    # nothing in the results should carry a Housing-derived merchant
    assert all("rent" not in m for m in subs)


def test_next_expected_is_last_plus_interval():
    subs = _by_merchant(subscriptions.detect_subscriptions(_build(), TODAY))
    nf = subs["netflix"]
    last = date.fromisoformat(nf["last_charge"])
    nxt = date.fromisoformat(nf["next_expected"])
    gap = (nxt - last).days
    assert 26 <= gap <= 35  # a monthly interval past the last charge


def test_normalize_strips_store_numbers_and_dates():
    assert subscriptions.normalize_merchant("NETFLIX #1234") == "netflix"
    assert subscriptions.normalize_merchant("NETFLIX 07/24") == "netflix"
    assert subscriptions.normalize_merchant("Netflix") == "netflix"


def test_determinism():
    txns = _build()
    a = subscriptions.detect_subscriptions(txns, TODAY)
    b = subscriptions.detect_subscriptions(txns, TODAY)
    assert a == b


def test_inflows_ignored():
    txns = [
        {"date": f"2026-0{m}-05", "amount": 2000.0,
         "description": "PAYROLL DEPOSIT", "category": "Income"}
        for m in range(1, 6)
    ]
    assert subscriptions.detect_subscriptions(txns, TODAY) == []
