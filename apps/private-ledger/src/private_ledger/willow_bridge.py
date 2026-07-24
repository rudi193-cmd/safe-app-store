# b17: PLBRDG  ΔΣ=42
"""
willow_bridge.py — the ONE outward seam for Private Ledger.

Deliberately OUTSIDE the no-egress core (oakenscrolls-office willow_bridge
pattern): the ledger core (db.py), the schema, the path resolver and the
subscription math NEVER import this module — it imports THEM. Direction is
always bridge -> core, never core -> bridge. Everything here is optional and
degrades to a silent no-op when Willow is absent.

PRIVACY (privacy_tier: client_only). This app's transaction data never leaves
the device as rows. The bridge emits ONLY aggregates: totals, per-category
sums, subscription counts and annualized figures. It NEVER emits an individual
transaction, and NEVER a raw statement description. Merchant identities that do
appear in the proactive signal are the normalized merchant tokens produced by
the core detector (e.g. "netflix"), never the raw description line.

Two seams, both borrowed from the house pattern:
  * surface_due()      — the dew: publish subscriptions coming due to a signal
                         file hooks can read. Off by default; the env flag
                         PRIVATE_LEDGER_PROACTIVE=1 enables it.
  * promote_summary()  — the promote pattern: an aggregate monthly summary can
                         become a knowledge atom. The ingest callable is
                         INJECTED (willow's knowledge_ingest, or anything with
                         the same shape); there is NO ``import willow`` here,
                         ever. With no callable the atom is returned unsent.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import subscriptions


# ── Proactive gate ────────────────────────────────────────────────────────────

def proactive_enabled() -> bool:
    return os.environ.get("PRIVATE_LEDGER_PROACTIVE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def signal_path(signal_dir: Optional[str] = None) -> Path:
    if signal_dir is not None:
        return Path(signal_dir).expanduser() / "private_ledger_dew.json"
    home = Path(os.environ.get("WILLOW_HOME", Path.home() / ".willow"))
    return home / "signals" / "private_ledger_dew.json"


# ── The dew: subscriptions coming due ─────────────────────────────────────────

def surface_due(db, today: Optional[date] = None, lead_days: int = 7,
                signal_dir: Optional[str] = None) -> bool:
    """Publish subscriptions due within ``lead_days`` to the signal file.

    Off by default: returns False immediately unless ``proactive_enabled()``.
    The payload is FACTS ONLY — normalized merchant, next_expected, and the
    amount / annualized figures. No raw transaction descriptions, no rows.
    Returns True when a signal was written, False otherwise (including when
    nothing is due, or on OSError, which is swallowed)."""
    if not proactive_enabled():
        return False
    if today is None:
        today = date.today()

    from datetime import timedelta
    window_end = today + timedelta(days=lead_days)
    due = []
    for sub in subscriptions.from_db(db, today):
        if sub.get("status") != "active":
            continue
        nxt = sub.get("next_expected")
        try:
            nxt_date = date.fromisoformat(str(nxt)[:10])
        except (TypeError, ValueError):
            continue
        if today <= nxt_date <= window_end:
            due.append({
                "merchant": sub["normalized_merchant"],
                "next_expected": sub["next_expected"],
                "amount": sub.get("amount"),
                "annualized": sub.get("annualized"),
            })
    if not due:
        return False

    payload = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "app_id": "private-ledger",
        "lead_days": lead_days,
        "due": due,
    }
    path = signal_path(signal_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        return True
    except OSError:
        return False


# ── The promote: aggregate monthly summary -> knowledge atom ──────────────────

class PromotionRefused(Exception):
    """The summary was NOT stored. Raised loudly so a refused KB write can
    never be mistaken for a successful one (fleet rule: hard stops, no swallowed
    failures)."""


def build_summary_atom(db, today: Optional[date] = None) -> dict:
    """Build a knowledge atom of AGGREGATE STRUCTURE ONLY for the current month.

    Privacy: NO individual transactions and NO raw descriptions are read into
    the atom — only monthly totals, per-category sums, and subscription counts.
    The atom is shaped like a willow knowledge atom: {content, domain, source,
    tags} (plus a stable id)."""
    if today is None:
        today = date.today()
    month_str = f"{today.year:04d}-{today.month:02d}"

    rows = db.get_transactions(limit=1_000_000)
    income_total = 0.0
    spend_total = 0.0
    per_category: dict[str, float] = {}
    tx_count = 0
    for row in rows:
        if not str(row["date"]).startswith(month_str):
            continue
        tx_count += 1
        amount = float(row["amount"])
        if amount > 0:
            income_total += amount
        elif amount < 0:
            outflow = -amount
            spend_total += outflow
            category = row["category"] or "Other"
            per_category[category] = per_category.get(category, 0.0) + outflow

    subs = subscriptions.from_db(db, today)
    active = [s for s in subs if s.get("status") == "active"]
    active_count = len(active)
    annualized_total = round(sum(s.get("annualized") or 0.0 for s in active), 2)

    ordered_cats = sorted(per_category.items(), key=lambda kv: (-kv[1], kv[0]))
    cats_str = "; ".join(f"{cat} ${amt:,.2f}" for cat, amt in ordered_cats) or "none"

    content = (
        f"Private Ledger monthly summary for {month_str}: "
        f"income ${income_total:,.2f}, spend ${spend_total:,.2f} across "
        f"{tx_count} transaction(s). By category — {cats_str}. "
        f"Active subscriptions: {active_count} "
        f"(~${annualized_total:,.2f}/yr annualized)."
    )

    return {
        "id": f"private-ledger-{month_str}",
        "content": content,
        "domain": "saps1",
        "source": "private-ledger",
        "tags": ["private-ledger", "budget-summary", "aggregate", month_str],
    }


def promote_summary(db, today: Optional[date] = None,
                    ingest: Optional[Callable[[dict], object]] = None) -> dict:
    """Build the aggregate monthly atom and hand it to an injected ingest
    callable. With no callable, returns the atom without sending it anywhere —
    this module never phones home.

    The ingest contract is LOUD: on success it must return a truthy
    confirmation (e.g. willow's ``{"id": ...}``). A falsy/None result, an
    ``{"error": ...}`` dict, or an exception raised by the callable all raise
    ``PromotionRefused`` — a summary that did not land is never reported as if
    it did."""
    atom = build_summary_atom(db, today=today)
    if ingest is None:
        return atom
    try:
        outcome = ingest(atom)
    except Exception as exc:  # a raising ingest is a refused write, made loud
        raise PromotionRefused(
            f"ingest raised for {atom['id']} — the summary did not land: {exc}"
        ) from exc
    if isinstance(outcome, dict) and outcome.get("error"):
        raise PromotionRefused(
            f"summary REFUSED, not stored: {outcome['error']} (atom {atom['id']})"
        )
    if not outcome:
        raise PromotionRefused(
            f"ingest returned no confirmation for {atom['id']} — "
            "the summary did not land; refusing to report success"
        )
    return {**atom, "stored": outcome}
