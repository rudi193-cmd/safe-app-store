"""Tests for stores/checkpoint_governance.py — the human_loop adoption wrapper
(docs/design/the-forge-human-loop.md): attestation under a decision (D-HL-4),
the park half of the async seam (D-HL-5), and the nudge outbox (D-HL-6).

Pure — soil_store + vendored human_loop only, no Nestor/fsrs. Written test-first.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "checkpoint_governance", _REPO / "stores" / "checkpoint_governance.py"
)
gov = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint_governance"] = gov
_spec.loader.exec_module(gov)

human_loop = gov.human_loop
BUILDER_A = "a" * 32


# ── attestation under a decision (D-HL-4) ────────────────────────────────────

def test_attest_decision_writes_a_non_forgeable_record(tmp_path):
    root = tmp_path / "checkpoints"
    rec = gov.attest_decision(
        BUILDER_A, "pair-1", chosen="session cookie + CSRF", by_human=True, root=root,
    )
    assert rec["attested_by"] == BUILDER_A       # bound to the builder, not free text
    assert rec["by_human"] is True
    assert gov.has_decision_attestation(BUILDER_A, "pair-1", root=root) is True
    assert gov.has_decision_attestation(BUILDER_A, "pair-1", require_human=True, root=root) is True


def test_an_agent_attestation_does_not_satisfy_require_human(tmp_path):
    root = tmp_path / "checkpoints"
    gov.attest_decision(BUILDER_A, "pair-2", chosen="x", by_human=False, root=root)
    assert gov.has_decision_attestation(BUILDER_A, "pair-2", root=root) is True
    assert gov.has_decision_attestation(BUILDER_A, "pair-2", require_human=True, root=root) is False


def test_has_attestation_is_false_for_an_unsigned_decision(tmp_path):
    root = tmp_path / "checkpoints"
    assert gov.has_decision_attestation(BUILDER_A, "never-signed", root=root) is False


# ── the park half of the async seam (D-HL-5) ─────────────────────────────────

def test_park_decision_enqueues_the_evidence_and_seals_nothing(tmp_path):
    root = tmp_path / "checkpoints"
    item = gov.park_decision(
        BUILDER_A,
        decision_type="auth-flow",
        surface="How should the login form authenticate?",
        options=[("session cookie + CSRF", "server session"), ("JWT", "stateless")],
        recommended="session cookie + CSRF",
        root=root,
    )
    assert item["kind"] == "attestation"
    assert item["status"] == "open"
    # the full decision rides along as evidence a human can read
    assert "How should the login form authenticate" in item["summary"]
    # nothing attested yet — parking is not deciding
    assert gov.has_decision_attestation(BUILDER_A, "auth-flow", root=root) is False
    # visible in the open queue
    assert len(gov.open_items(BUILDER_A, root=root)) == 1


def test_resolve_item_updates_in_place_states_not_deletions(tmp_path):
    root = tmp_path / "checkpoints"
    item = gov.park_decision(
        BUILDER_A, decision_type="d", surface="s", options=[("a", "t")], recommended=None, root=root,
    )
    gov.resolve_item(BUILDER_A, item["id"], resolved_by=BUILDER_A, status="resolved", root=root)
    assert gov.open_items(BUILDER_A, root=root) == []  # no longer open, not deleted


# ── the nudge outbox (D-HL-6) ────────────────────────────────────────────────

def test_route_nudge_enqueues_a_review_item(tmp_path):
    root = tmp_path / "checkpoints"
    gov.route_nudge(
        BUILDER_A, kind="review", title="thin rationale on cache-eviction-policy",
        summary="engagement 0.10", source_ref="engagement:cache-eviction-policy", root=root,
    )
    items = gov.open_items(BUILDER_A, root=root)
    assert len(items) == 1
    assert items[0]["kind"] == "review"


def test_route_nudge_dedupes_by_source_ref(tmp_path):
    root = tmp_path / "checkpoints"
    for _ in range(3):
        gov.route_nudge(
            BUILDER_A, kind="overload", title="rubber-stamp run", summary="mean 0.12",
            source_ref="engagement-run:7", root=root,
        )
    # the same episode routed three times is ONE open item, not three
    assert len(gov.open_items(BUILDER_A, root=root)) == 1


def test_route_nudge_rejects_a_non_queue_kind(tmp_path):
    root = tmp_path / "checkpoints"
    with pytest.raises(gov.GovernanceError):
        gov.route_nudge(BUILDER_A, kind="not-a-kind", title="x", source_ref="y", root=root)
