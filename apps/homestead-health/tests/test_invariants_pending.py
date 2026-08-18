"""The module invariants later bites must satisfy — written now, failing on purpose.

H-1 through H-5 from `homestead/docs/PLAN-homestead-health.md`, landing the day
the seat exists, exactly as that plan promised. Every one is
`xfail(strict=True)`, the engine's `tests/test_invariants_pending.py` mechanism
taken whole (with its history: the shared-reason-string defect, the
mis-attribution limit, the four promotions — read it there):

  * the suite stays green while a bite is unbuilt, so CI is honest; and
  * the moment an implementation makes one of these pass, **the suite fails**
    and forces the test to be promoted out of this file.

So this is not a wish list. It is a set of claims that cannot be quietly
satisfied and cannot be quietly forgotten.
"""
from __future__ import annotations

import importlib.util

import pytest

# Every module a pending test reaches for, and the bite that builds it.
# The guard is module-granular (`find_spec` answers for a module, not a symbol)
# — the engine's file documents that limit and it is inherited here unchanged.
UNBUILT = {
    "homestead_health.reference": "bite 3/4 — the pinned schedule snapshot",
    "homestead_health.due": "bite 4 — due onto Today, calendar days and k ≥ 2",
    "homestead_health.school_form": "bite 5 — health's first purposed egress",
    "homestead_health.emergency": "post-v1 — the emergency card",
}


def pending(module: str, why: str):
    """xfail with a reason naming *this* test's module and bite.

    Per-test module naming plus `test_pending_liveness` below — the engine's
    answer to the audit finding where a typo'd symbol left the suite green at
    13 xfailed.
    """
    bite = UNBUILT.get(module, "unknown bite")
    return pytest.mark.xfail(strict=True, reason=f"{module} unbuilt ({bite}) — {why}")


def _exists(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        # `find_spec` imports parent packages on the way down, so asking about
        # `homestead_health.packs.immunizations` before `packs` exists raises
        # rather than returning None. A missing parent means the module is
        # certainly unbuilt — the engine's flat UNBUILT list never met this
        # shape; this one has a nested pack in it.
        return False


def test_pending_liveness():
    """Asserts exactly which modules are still unbuilt. When a bite lands,
    this fails *first* and by name — so a pending test cannot keep xfailing
    for a reason nobody checked."""
    built = sorted(m for m in UNBUILT if _exists(m))
    assert not built, (
        f"these modules now exist: {built}. Their pending tests must be "
        "promoted out of this file, and this list updated — do not leave them "
        "xfailing."
    )


# ── H-1 · a subject is opaque everywhere but the roster and the detail pane ──
#
# Promoted to tests/test_invariants_roster.py when homestead_health.roster
# landed as bite 2 — subjects before records. The moment the module existed
# `test_pending_liveness` failed by name, and stays red until the H-1 test is
# carried out of this file unmarked. This is the first promotion in the health
# module; the engine's own file records four more, and the mechanism is its,
# taken whole.


# ── H-2 · the app never advises care ─────────────────────────────────────────


@pending(
    "homestead_health.due",
    "H-2 — operator-facing text composes from a closed vocabulary (the closed "
    "Event enum's discipline, R-7), so no code path can phrase a recommendation",
)
def test_h2_derived_lines_come_from_a_closed_vocabulary():
    from homestead_health.due import DERIVED, derived_line

    # Every line `derived_line` can produce is a member of the closed set,
    # parameterised by counts and nothing else — there is no free-text
    # position for advice to be phrased in, which is the structural half of
    # "the app never advises care". The behavioural half lands with the
    # surface itself.
    line = derived_line(due=2)
    assert line in {template.format(n=2) for template in DERIVED}


# ── H-3 · the emergency card is authored, not computed ───────────────────────


@pending(
    "homestead_health.emergency",
    "H-3 — the card holds a closed, operator-chosen field set; no path "
    "auto-includes by relevance",
)
def test_h3_the_card_holds_only_what_the_operator_chose():
    from homestead_health.emergency import Card

    card = Card(fields=("allergies",))
    assert card.fields == ("allergies",)
    # A computed card is a query someone else effectively wrote. The class
    # must not offer the machinery: no auto-include, no relevance.
    assert not hasattr(Card, "auto_include")
    assert not hasattr(Card, "relevant_fields")


# ── H-4 · a dose is a fact with a source ─────────────────────────────────────
#
# Promoted to tests/test_invariants_immunizations.py when
# homestead_health.packs.immunizations landed as bite 3 — the pack, classified
# at import. The `packs.immunizations` key came out of UNBUILT and the H-4 test
# moved there with its body kept, the way the roster's H-1 moved before it.


# ── H-5 · reference data is pinned, never fetched ────────────────────────────


@pending(
    "homestead_health.reference",
    "H-5 — the schedule ships as a versioned snapshot showing its own date; "
    "updating it is an operator's act (the fetch half is already enforced by "
    "the seat's network scan)",
)
def test_h5_the_snapshot_shows_its_own_date():
    from homestead_health.reference import SCHEDULE

    assert SCHEDULE.version, "a snapshot that cannot say which version it is, isn't one"
    assert SCHEDULE.as_of, "a snapshot that cannot say its date is a live feed in disguise"


# ── bite 5 · the school form — health's first purposed egress ────────────────


@pending(
    "homestead_health.school_form",
    "bite 5 — export one subject's immunization history through "
    "serve(…, S4_EGRESS, purpose=…) and keep/export; both log entries carry "
    "references and no content (I-15)",
)
def test_bite5_the_export_exists_and_is_purposed():
    from homestead_health.school_form import export_history

    assert callable(export_history)
