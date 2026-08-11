"""Tests for stores/checkpoint_memory.py — per-builder checkpoint memory
(D9/D12, docs/design/the-forge.md).

**Honest environment note, in the same spirit as
`apps/the-forge/tests/test_sandbox_runner.py`'s bwrap disclosure.** These
tests exercise the REAL Nestor library, not a mock or a reimplementation —
`nestor.sqlite_store.SqliteStore`, `nestor.entity.EntityResolver`,
`nestor.memory.reject_match`/`reject_pair`, all real. Nestor is not on PyPI
(see `stores/checkpoint_memory.py`'s own module docstring and
`stores/requirements.txt`), so running this file requires it installed
editable from the sibling checkout first:

    pip install -e /workspace/nestor

(verify that path in your own environment before assuming it — `ls
/workspace/nestor` — it is not guaranteed to be there or at that path). If
Nestor is not importable, `stores/checkpoint_memory.py`'s own top-level
import raises a `ImportError` with this same instruction, and every test
below fails at collection with that message rather than a bare
`ModuleNotFoundError` — see that module's "import Nestor" section.

One more honest note: Nestor's seal-signature machinery (`NESTOR_SEAL_KEY`)
is intentionally left unconfigured here, exactly as `stores/checkpoint_memory.py`'s
own module docstring says it leaves it — Nestor's own documented default
("opt-in and backward-compatible: with no key configured, signing is OFF and
every seal is accepted"). That means every test below emits a `RuntimeWarning`
from `nestor.memory.is_verified_seal` on the first seal check
("NESTOR_SEAL_KEY not set..."); that warning is Nestor doing exactly what its
own docstring says it does with no key configured, not a defect in this
module or these tests, and no test here relies on the signature check
actually rejecting anything.
"""
from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "checkpoint_memory", _REPO / "stores" / "checkpoint_memory.py"
)
checkpoint_memory = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint_memory"] = checkpoint_memory
_spec.loader.exec_module(checkpoint_memory)

principal = checkpoint_memory.principal  # the same principal.py checkpoint_memory.py itself loaded

pytestmark = pytest.mark.filterwarnings(
    "ignore:NESTOR_SEAL_KEY not set.*:RuntimeWarning"
)

BUILDER_A = "a" * 32  # path-safe under principal.py's _check_builder_id
BUILDER_B = "b" * 32
DECISION_TYPE = "auth-flow-for-user-facing-form"

# Two decision-description strings whose StringMatcher-normalized keys are
# DIFFERENT (so a rejection keyed on one's norm cannot accidentally suppress
# the other) but whose fuzzy similarity is >= SEAL_THRESHOLD (0.92), so
# resolving the second one is a genuine tier-1 hit against the first one's
# sealed pair before any rejection is recorded. Measured directly against
# nestor.matcher.StringMatcher while writing this test (ratio 0.95, distinct
# normalized keys) rather than assumed.
DECISION_TEXT = "should we encrypt customer PII at rest"
DECISION_TEXT_VARIANT = "should we encrypt customer PII at rest now"
CHOSEN_OPTION = "yes, AES-256 with envelope encryption"


def _open(tmp_path, builder_id=BUILDER_A, decision_type=DECISION_TYPE):
    return checkpoint_memory.open_checkpoint_memory(
        builder_id, decision_type, root=tmp_path / "checkpoints"
    )


# ── two builders, genuinely separate files (D12's core promise) ────────────

def test_two_builders_get_different_db_files(tmp_path):
    root = tmp_path / "checkpoints"
    path_a = checkpoint_memory.checkpoint_db_path(BUILDER_A, root=root)
    path_b = checkpoint_memory.checkpoint_db_path(BUILDER_B, root=root)
    assert path_a != path_b
    assert path_a.name == f"{BUILDER_A}.db"
    assert path_b.name == f"{BUILDER_B}.db"


def test_a_decision_sealed_by_one_builder_is_invisible_to_another_even_for_the_identical_decision_type(
    tmp_path,
):
    """The core promise D12 makes: one Nestor SqliteStore file per
    builder_id, not domain-tag scoping inside one shared database — so even
    the SAME decision_type string, for a DIFFERENT builder_id, sees nothing.
    """
    with _open(tmp_path, BUILDER_A) as cm_a:
        assert cm_a.has_sealed() is False
        cm_a.seal(DECISION_TEXT, CHOSEN_OPTION)
        assert cm_a.has_sealed() is True
        assert cm_a.check(DECISION_TEXT)["sealed"] is True

    with _open(tmp_path, BUILDER_B) as cm_b:
        assert cm_b.has_sealed() is False
        result = cm_b.check(DECISION_TEXT)
        assert result["sealed"] is False
        assert result["canonical"] is None

    # Not just "the API says no" — the file on disk for B genuinely holds
    # nothing. Open builder B's raw SqliteStore directly (bypassing this
    # module entirely) and confirm there is no row at all, not just an
    # unsealed one this module happened to filter.
    from nestor.sqlite_store import SqliteStore

    path_b = checkpoint_memory.checkpoint_db_path(BUILDER_B, root=tmp_path / "checkpoints")
    raw_b = SqliteStore(str(path_b))
    try:
        raw_b.memory_init()
        domain = checkpoint_memory._domain(BUILDER_B, DECISION_TYPE)
        assert raw_b.memory_candidates(domain, domain) == []
    finally:
        raw_b.close()


def test_reopening_the_same_builder_sees_its_own_prior_seal(tmp_path):
    """Not a leak test, the sibling check: closing and reopening the SAME
    builder's memory (a realistic caller pattern — one process per request)
    must still see what was sealed earlier."""
    with _open(tmp_path, BUILDER_A) as cm:
        cm.seal(DECISION_TEXT, CHOSEN_OPTION)

    with _open(tmp_path, BUILDER_A) as cm:
        assert cm.has_sealed() is True
        assert cm.check(DECISION_TEXT)["canonical"] == CHOSEN_OPTION


# ── has_sealed reflects a seal ──────────────────────────────────────────────

def test_has_sealed_is_false_before_and_true_after_a_seal(tmp_path):
    with _open(tmp_path) as cm:
        assert cm.has_sealed() is False
        result = cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        assert result["sealed"] is True
        assert result["pair_id"]
        assert cm.has_sealed() is True


def test_has_sealed_is_scoped_to_its_own_decision_type_not_global(tmp_path):
    """Sealing under one decision_type must not make a DIFFERENT
    decision_type (same builder) report sealed — the other half of D9's
    "domain must be (builder_id, decision_type), never just decision_type
    globally" line: this checks the decision_type axis, the cross-builder
    tests above check the builder_id axis."""
    with _open(tmp_path, BUILDER_A, "decision-type-one") as cm:
        cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        assert cm.has_sealed() is True

    with _open(tmp_path, BUILDER_A, "decision-type-two") as cm:
        assert cm.has_sealed() is False


# ── reject_match: this application wrong, pattern still holds ──────────────

def test_reject_match_suppresses_only_the_rejected_query_not_the_sealed_pair(tmp_path):
    with _open(tmp_path) as cm:
        sealed = cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        pair_id = sealed["pair_id"]

        # Before any rejection: the near-duplicate variant is a genuine
        # tier-1 fuzzy hit against the same sealed pair (confirms the test
        # fixture is exercising a real fuzzy match, not a coincidence).
        before = cm.check(DECISION_TEXT_VARIANT)
        assert before["sealed"] is True
        assert before["provenance"]["pair_id"] == pair_id

        cm.reject_match(
            DECISION_TEXT_VARIANT, pair_id=pair_id, verifier=BUILDER_A,
            reason="this variant means something slightly different here",
        )

        # The specific application (the variant wording) is now suppressed...
        after_variant = cm.check(DECISION_TEXT_VARIANT)
        assert after_variant["sealed"] is False

        # ...but the ORIGINAL sealed wording is untouched — this is the
        # distinction reject_match exists to draw, not just "the function
        # ran without raising."
        after_original = cm.check(DECISION_TEXT)
        assert after_original["sealed"] is True
        assert after_original["canonical"] == CHOSEN_OPTION
        assert after_original["provenance"]["pair_id"] == pair_id

        # has_sealed() (the decision-type-wide question) is unaffected too —
        # reject_match never touches the pair's own sealed status.
        assert cm.has_sealed() is True


def test_reject_match_requires_pair_id_or_target_text(tmp_path):
    with _open(tmp_path) as cm:
        cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        with pytest.raises(checkpoint_memory.CheckpointMemoryError, match="pair_id or target_text"):
            cm.reject_match(DECISION_TEXT_VARIANT)


# ── reject_pair: the pattern itself was wrong, unseal everywhere ───────────

def test_reject_pair_retracts_the_seal_so_has_sealed_reflects_it(tmp_path):
    with _open(tmp_path) as cm:
        sealed = cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        assert cm.has_sealed() is True

        cm.reject_pair(sealed["pair_id"], verifier=BUILDER_A, reason="this guidance was just wrong")

        assert cm.has_sealed() is False
        result = cm.check(DECISION_TEXT)
        assert result["sealed"] is False
        assert result["canonical"] is None


def test_reject_pair_is_a_stronger_retraction_than_reject_match(tmp_path):
    """reject_match on the ORIGINAL wording leaves the pair's own status
    untouched for other queries; reject_pair retires it everywhere. Same
    setup, different call, to make the two calls' actual difference in
    behavior visible rather than asserted."""
    with _open(tmp_path) as cm:
        sealed = cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        pair_id = sealed["pair_id"]

        cm.reject_match(
            DECISION_TEXT_VARIANT, pair_id=pair_id, verifier=BUILDER_A, reason="wrong for this variant",
        )
        # reject_match alone: the pair is still sealed and reachable via its
        # own original wording.
        assert cm.has_sealed() is True
        assert cm.check(DECISION_TEXT)["sealed"] is True

        cm.reject_pair(pair_id, verifier=BUILDER_A, reason="actually wrong in general")
        # reject_pair: gone, even via the original wording.
        assert cm.has_sealed() is False
        assert cm.check(DECISION_TEXT)["sealed"] is False


# ── malformed builder_id: rejected before any file gets created ────────────
#
# Same "no file left behind on hostile input" discipline
# apps/the-forge/src/the_forge/mount_policy.py's write_scoped_policy and
# stores/session.py's own validation already follow.

@pytest.mark.parametrize(
    "bad_builder_id",
    [
        "",
        "../escape",
        "../../etc/passwd",
        "/absolute/path",
        ".hidden",
        "with a space",
        "trailing/slash/",
        "null\x00byte",
        "a" * 200,  # exceeds principal.py's _MAX_BUILDER_ID_LEN
    ],
)
def test_malformed_builder_id_is_refused_before_any_file_is_created(tmp_path, bad_builder_id):
    root = tmp_path / "checkpoints"
    with pytest.raises(checkpoint_memory.CheckpointMemoryError):
        checkpoint_memory.open_checkpoint_memory(bad_builder_id, DECISION_TYPE, root=root)
    # Not just "it raised" — nothing was written. Either the root was never
    # created at all, or (if a prior parametrized case already created it)
    # it holds no .db file for this attempt.
    if root.exists():
        assert list(root.glob("*.db")) == []


def test_malformed_builder_id_is_refused_by_checkpoint_db_path_too(tmp_path):
    root = tmp_path / "checkpoints"
    with pytest.raises(checkpoint_memory.CheckpointMemoryError):
        checkpoint_memory.checkpoint_db_path("../escape", root=root)
    assert not root.exists()


@pytest.mark.parametrize(
    "bad_decision_type",
    ["", "with a space", "has:colon", "../traversal", "a" * 200],
)
def test_malformed_decision_type_is_refused_before_any_file_is_created(tmp_path, bad_decision_type):
    root = tmp_path / "checkpoints"
    with pytest.raises(checkpoint_memory.CheckpointMemoryError):
        checkpoint_memory.open_checkpoint_memory(BUILDER_A, bad_decision_type, root=root)
    if root.exists():
        assert list(root.glob("*.db")) == []


# ── adversarial: try to prove checkpoint_db_path CAN collide, and fail ─────

def test_checkpoint_db_path_is_injective_over_many_builder_ids(tmp_path):
    """Not a proof by construction alone (the module docstring gives that) —
    this generates a large, varied set of valid builder_ids, including
    adjacent/near-collision-looking ones, and confirms the resulting paths
    are pairwise distinct and each stays a single path component directly
    under root."""
    import secrets

    root = tmp_path / "checkpoints"
    candidates = {secrets.token_hex(16) for _ in range(200)}
    # Near-miss candidates chosen to look like they might collide once a
    # fixed ".db" suffix is appended: "aaaa" -> "aaaa.db" looks like it could
    # collide with a builder literally named "aaaa.db" -> "aaaa.db.db". It
    # cannot: the suffix is appended AFTER validation, once, to each distinct
    # (already-validated) builder_id string, so the two paths are "aaaa.db"
    # and "aaaa.db.db" — different strings, not a collision.
    candidates.update({"a" * 32, "aaaa", "aaaa.db", "aaaa.db.db"})
    paths = {}
    for bid in candidates:
        p = checkpoint_memory.checkpoint_db_path(bid, root=root)
        assert p.parent == root, f"{bid!r} escaped its root: {p}"
        if p in paths:
            pytest.fail(f"collision: {bid!r} and {paths[p]!r} both map to {p}")
        paths[p] = bid


def test_checkpoint_db_path_never_produces_a_path_outside_root(tmp_path):
    root = tmp_path / "checkpoints"
    attempts = ["../sibling", "..", "a/../../b", "a/b", "./a"]
    for bid in attempts:
        with pytest.raises(checkpoint_memory.CheckpointMemoryError):
            checkpoint_memory.checkpoint_db_path(bid, root=root)


# ── close/cleanup semantics ─────────────────────────────────────────────────

def test_using_a_closed_checkpoint_memory_raises_the_module_own_exception_type(tmp_path):
    cm = _open(tmp_path)
    cm.seal(DECISION_TEXT, CHOSEN_OPTION)
    cm.close()
    # A caller of THIS module should never have to catch
    # nestor.sqlite_store.StoreClosedError directly — see CheckpointMemoryError's
    # own docstring.
    with pytest.raises(checkpoint_memory.CheckpointMemoryError):
        cm.has_sealed()


def test_context_manager_closes_on_exit_even_after_an_exception(tmp_path):
    with pytest.raises(RuntimeError, match="boom"):
        with _open(tmp_path) as cm:
            cm.seal(DECISION_TEXT, CHOSEN_OPTION)
            raise RuntimeError("boom")
    with pytest.raises(checkpoint_memory.CheckpointMemoryError):
        cm.has_sealed()


def test_close_is_idempotent(tmp_path):
    cm = _open(tmp_path)
    cm.close()
    cm.close()  # must not raise


# ── conflict / rejection Nestor exceptions surface as this module's own ────

def test_conflicting_seal_by_a_different_verifier_raises_checkpoint_conflict(tmp_path):
    with _open(tmp_path) as cm:
        cm.seal(DECISION_TEXT, CHOSEN_OPTION, verifier=BUILDER_A)
        with pytest.raises(checkpoint_memory.CheckpointConflict):
            cm.seal(DECISION_TEXT, "a completely different answer", verifier="someone-else")


def test_resealing_a_rejected_pair_raises_checkpoint_rejected(tmp_path):
    with _open(tmp_path) as cm:
        sealed = cm.seal(DECISION_TEXT, CHOSEN_OPTION)
        cm.reject_pair(sealed["pair_id"], verifier=BUILDER_A, reason="wrong")
        with pytest.raises(checkpoint_memory.CheckpointRejected):
            cm.seal(DECISION_TEXT, CHOSEN_OPTION, verifier=BUILDER_A)


# ── ledger: sanity, not a re-test of Nestor's own hash-chain suite ─────────

# ── the soft-Nestor import strategy (2026-08-11, bite 1 of D8/D9/D12) ──────
#
# Not a re-test of the degraded-Nestor CASE — that belongs to
# `tests/test_checkpoint.py` (the orchestrator that actually has to behave
# differently when Nestor is absent), and needs a meta-path-finder /
# sys.modules eviction this file's own `_open` fixtures don't set up. This
# is only the structural claim this file's own docstring above now depends
# on: importing `checkpoint_memory` no longer requires Nestor to be
# importable, and `nestor_available()` exists and returns a plain bool.
# Since Nestor genuinely IS installed in this test environment (see this
# file's own module docstring), this deliberately does NOT assert which way
# `nestor_available()` comes back — only that the import-without-crashing
# path and the public function exist and behave, covering the code path
# structurally without needing to fake Nestor's absence here.

def test_module_imports_and_nestor_available_returns_a_bool_without_asserting_nestor_presence():
    assert isinstance(checkpoint_memory.nestor_available(), bool)


def test_sealing_writes_to_this_root_own_ledger_not_the_process_cwd(tmp_path):
    root = tmp_path / "checkpoints"
    with _open(tmp_path) as cm:
        cm.seal(DECISION_TEXT, CHOSEN_OPTION)
    assert (root / "ledger.jsonl").exists()
    # And nothing was written to the conventional cwd-relative default this
    # module deliberately overrides (see module docstring) — best-effort:
    # only meaningful if that path doesn't already legitimately exist from
    # something else, which it should not inside a fresh tmp cwd, but this
    # repo's tests may run from the repo root, so just check our own file
    # is the one Nestor's cascade is pointed at.
    from nestor import cascade

    assert cascade._ledger_path() == root / "ledger.jsonl"
