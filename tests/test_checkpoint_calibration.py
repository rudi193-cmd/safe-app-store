"""Tests for stores/checkpoint_calibration.py — bite 2 of The Forge's
learning layer (docs/design/the-forge.md, "Verification-as-learning",
2026-08-11): `#12` lesson-regression (resurface a sealed decision, does it
still hold) folded with `#3` contradiction (a regressed resurface IS the
practical contradiction signal; Nestor's own `ConflictingSealError` is the
other reachable contradiction, reused unwrapped as `CheckpointConflict`).

**Honest environment note, same as bite 1's own test files** — these tests
exercise the REAL Nestor library (except the soft-Nestor degradation test,
which deliberately blocks it). See `tests/test_checkpoint_memory.py`'s
module docstring for the `pip install -e /workspace/nestor` note.

Written test-first, before `stores/checkpoint_calibration.py` existed.
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "checkpoint_calibration", _REPO / "stores" / "checkpoint_calibration.py"
)
checkpoint_calibration = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint_calibration"] = checkpoint_calibration
_spec.loader.exec_module(checkpoint_calibration)

checkpoint = checkpoint_calibration.checkpoint
checkpoint_memory = checkpoint_calibration.checkpoint_memory

_HAS_FSRS = checkpoint_calibration.checkpoint_schedule.fsrs_available()
_needs_fsrs = pytest.mark.skipif(not _HAS_FSRS, reason="fsrs not installed in this environment")

_SUBSTANTIVE_JUSTIFICATION = (
    "I re-measured the reporting query at 1.2s with joins versus 40ms on the "
    "denormalized copy and the write rate has not changed, so the tradeoff still holds"
)
_THIN_JUSTIFICATION = "yeah still fine"

pytestmark = pytest.mark.filterwarnings(
    "ignore:NESTOR_SEAL_KEY not set.*:RuntimeWarning"
)

BUILDER_A = "a" * 32  # path-safe under principal.py's _check_builder_id, same fixture value bite 1's tests use
DECISION_TYPE = "auth-flow-for-user-facing-form"
ORIGINAL_SURFACE = "How should the login form authenticate?"
CHOSEN_ANSWER = "session cookie + CSRF"


class ScriptedResponder:
    """Same shape as `tests/test_checkpoint.py`'s own `ScriptedResponder` —
    a `Responder` whose every answer is pre-loaded, in call order. Kept as
    its own (small) copy rather than importing the other test file's class:
    a test-only fixture, not a mechanism this repo's rule 11 governs."""

    def __init__(self, confirm_answers=None, choose_answers=None, justify_answers=None):
        self._confirm_answers = list(confirm_answers or [])
        self._choose_answers = list(choose_answers or [])
        self._justify_answers = list(justify_answers or [])
        self.confirm_prompts: list[str] = []
        self.choose_calls: list = []
        self.justify_prompts: list[str] = []

    def confirm(self, prompt: str) -> bool:
        self.confirm_prompts.append(prompt)
        if not self._confirm_answers:
            raise AssertionError(f"ScriptedResponder.confirm asked with no answer queued: {prompt!r}")
        return self._confirm_answers.pop(0)

    def justify(self, prompt: str) -> str:
        # Unlike confirm/choose, an unscripted justify returns "" (a legitimate
        # decline — a bare hold), so tests that don't care about the engagement
        # wire keep their pre-wire behavior instead of erroring.
        self.justify_prompts.append(prompt)
        return self._justify_answers.pop(0) if self._justify_answers else ""

    def choose(self, decision) -> "checkpoint.ChoiceResult":
        self.choose_calls.append(decision)
        if not self._choose_answers:
            raise AssertionError(f"ScriptedResponder.choose asked with no answer queued: {decision.surface!r}")
        return self._choose_answers.pop(0)


def _seal_original_auth_decision(root: Path, builder_id: str = BUILDER_A) -> None:
    with checkpoint_memory.open_checkpoint_memory(builder_id, DECISION_TYPE, root=root) as cm:
        cm.seal(ORIGINAL_SURFACE, CHOSEN_ANSWER)


# ── 1. held ──────────────────────────────────────────────────────────────────

def test_resurface_held_confirms_and_does_not_reseal(tmp_path, monkeypatch):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    seal_calls = []
    original_seal = checkpoint_memory.CheckpointMemory.seal

    def _spy_seal(self, *a, **kw):
        seal_calls.append((a, kw))
        return original_seal(self, *a, **kw)

    monkeypatch.setattr(checkpoint_memory.CheckpointMemory, "seal", _spy_seal)

    responder = ScriptedResponder(confirm_answers=[True])
    outcome = checkpoint_calibration.resurface(
        builder_id=BUILDER_A,
        decision_type=DECISION_TYPE,
        surface=ORIGINAL_SURFACE,
        responder=responder,
        root=root,
    )

    assert outcome.held is True
    assert outcome.regressed is False
    assert outcome.resealed is False
    assert outcome.prior == CHOSEN_ANSWER
    assert outcome.new == ""
    assert len(responder.confirm_prompts) == 1
    assert CHOSEN_ANSWER in responder.confirm_prompts[0]
    assert responder.choose_calls == []
    assert seal_calls == []  # held -> nothing re-sealed

    # still sealed to the SAME answer afterward
    with checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        result = cm.check(ORIGINAL_SURFACE)
        assert result["sealed"] is True
        assert result["canonical"] == CHOSEN_ANSWER


# ── 2. regressed — the #12 headline ─────────────────────────────────────────

def test_resurface_regressed_rejects_prior_and_seals_new_answer(tmp_path, monkeypatch):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    reject_calls = []
    original_reject_match = checkpoint_memory.CheckpointMemory.reject_match

    def _spy_reject_match(self, *a, **kw):
        reject_calls.append((a, kw))
        return original_reject_match(self, *a, **kw)

    monkeypatch.setattr(checkpoint_memory.CheckpointMemory, "reject_match", _spy_reject_match)

    reject_pair_calls = []
    original_reject_pair = checkpoint_memory.CheckpointMemory.reject_pair

    def _spy_reject_pair(self, *a, **kw):
        reject_pair_calls.append((a, kw))
        return original_reject_pair(self, *a, **kw)

    monkeypatch.setattr(checkpoint_memory.CheckpointMemory, "reject_pair", _spy_reject_pair)

    responder = ScriptedResponder(
        confirm_answers=[False],
        choose_answers=[
            checkpoint.ChoiceResult(
                chosen_label="JWT bearer token",
                rationale="switched to a public API client, no browser session anymore",
            )
        ],
    )

    outcome = checkpoint_calibration.resurface(
        builder_id=BUILDER_A,
        decision_type=DECISION_TYPE,
        surface=ORIGINAL_SURFACE,
        responder=responder,
        root=root,
    )

    assert outcome.held is False
    assert outcome.regressed is True
    assert outcome.resealed is True
    assert outcome.prior == CHOSEN_ANSWER
    assert outcome.new == "JWT bearer token: switched to a public API client, no browser session anymore"
    assert len(responder.choose_calls) == 1

    # reject_match (not reject_pair) was the teaching call, identified by
    # target_text — see checkpoint_calibration.py's own module docstring for
    # why pair_id/reject_pair are both the wrong choice here (verified
    # against real Nestor: pair_id survives an in-place reseal and would
    # permanently block this exact surface from resolving sealed again;
    # reject_pair would make the immediate reseal itself raise
    # RejectedPairError).
    assert len(reject_calls) == 1
    args, kwargs = reject_calls[0]
    assert args[0] == ORIGINAL_SURFACE
    assert kwargs.get("target_text") == CHOSEN_ANSWER
    assert reject_pair_calls == []

    # the NEW answer is what's sealed now for this exact wording
    with checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        result = cm.check(ORIGINAL_SURFACE)
        assert result["sealed"] is True
        assert result["canonical"] == outcome.new

    # ...and a SUBSEQUENT resurface reflects the NEW answer, not the old one
    responder2 = ScriptedResponder(confirm_answers=[True])
    outcome2 = checkpoint_calibration.resurface(
        builder_id=BUILDER_A,
        decision_type=DECISION_TYPE,
        surface=ORIGINAL_SURFACE,
        responder=responder2,
        root=root,
    )
    assert outcome2.held is True
    assert outcome2.prior == outcome.new
    assert len(responder2.confirm_prompts) == 1
    assert outcome.new in responder2.confirm_prompts[0]
    assert CHOSEN_ANSWER not in responder2.confirm_prompts[0]


def test_resurface_regressed_prompt_shows_the_prior_answer(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    responder = ScriptedResponder(
        confirm_answers=[False],
        choose_answers=[checkpoint.ChoiceResult(chosen_label="JWT bearer token", rationale="changed my mind")],
    )
    checkpoint_calibration.resurface(
        builder_id=BUILDER_A,
        decision_type=DECISION_TYPE,
        surface=ORIGINAL_SURFACE,
        responder=responder,
        root=root,
    )
    assert len(responder.confirm_prompts) == 1
    assert CHOSEN_ANSWER in responder.confirm_prompts[0]
    assert DECISION_TYPE in responder.confirm_prompts[0]


# ── 3. nothing to resurface ──────────────────────────────────────────────────

def test_resurface_with_no_prior_seal_at_all_raises(tmp_path):
    root = tmp_path / "checkpoints"
    responder = ScriptedResponder()
    with pytest.raises(checkpoint_calibration.CalibrationError):
        checkpoint_calibration.resurface(
            builder_id=BUILDER_A,
            decision_type="never-sealed-decision-type",
            surface="anything at all",
            responder=responder,
            root=root,
        )
    assert responder.confirm_prompts == []
    assert responder.choose_calls == []


def test_resurface_a_surface_that_was_never_itself_sealed_raises(tmp_path):
    """`has_sealed()` is True for the decision-type (something else was
    sealed under it), but THIS surface never resolved to a sealed hit —
    still nothing to resurface for this specific wording."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    responder = ScriptedResponder()
    with pytest.raises(checkpoint_calibration.CalibrationError):
        checkpoint_calibration.resurface(
            builder_id=BUILDER_A,
            decision_type=DECISION_TYPE,
            surface="What database engine should we use for the analytics warehouse?",
            responder=responder,
            root=root,
        )


# ── 4. contradiction surfaces (reuse, not rebuild) ──────────────────────────

def test_conflicting_seal_from_a_different_verifier_raises_checkpoint_conflict(tmp_path):
    """Pins that Nestor's own `ConflictingSealError` — surfaced by
    `checkpoint_memory.py` as `CheckpointConflict` — is reachable through
    the same `seal()` call this module's regression path itself uses, and
    that `checkpoint_calibration.contradictions()` is a thin, unwrapped
    pass-through to it rather than a new detector."""
    root = tmp_path / "checkpoints"
    surface = "Should this endpoint rate-limit by IP or by API key?"
    with checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        cm.seal(surface, "by API key", verifier="verifier-one")
        with pytest.raises(checkpoint_memory.CheckpointConflict):
            cm.seal(surface, "by IP", verifier="verifier-two")

    with checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        with pytest.raises(checkpoint_memory.CheckpointConflict):
            checkpoint_calibration.contradictions(
                cm, surface, "by IP", verifier="verifier-three"
            )


# ── 5. resurface advances the FSRS schedule (bite 2 fold-in) ─────────────────
# The scheduler's own math (interval growth/reset, fallback) is exercised in
# tests/test_checkpoint_schedule.py; these pin only the WIRING — that resurface
# records a review, keyed on the decision's pair_id, and reports next_due.

_T0 = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_resurface_held_records_a_future_due_date_and_persists_a_card(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    outcome = checkpoint_calibration.resurface(
        builder_id=BUILDER_A, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=ScriptedResponder(confirm_answers=[True]), root=root, now=_T0,
    )
    assert outcome.next_due
    assert datetime.fromisoformat(outcome.next_due) > _T0

    # a card was persisted, keyed by the decision's Nestor pair_id
    with checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        pair_id = cm.check(ORIGINAL_SURFACE)["provenance"]["pair_id"]
    card = checkpoint_calibration.checkpoint_schedule.load_card(BUILDER_A, pair_id, root=root)
    assert card is not None
    assert card["due"] == outcome.next_due


def test_resurface_regressed_records_a_review_too(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    outcome = checkpoint_calibration.resurface(
        builder_id=BUILDER_A, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=ScriptedResponder(
            confirm_answers=[False],
            choose_answers=[checkpoint.ChoiceResult(chosen_label="JWT bearer token", rationale="public API now")],
        ),
        root=root, now=_T0,
    )
    assert outcome.regressed is True
    assert outcome.next_due
    assert datetime.fromisoformat(outcome.next_due) > _T0


def test_two_held_resurfaces_advance_the_same_card(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    o1 = checkpoint_calibration.resurface(
        builder_id=BUILDER_A, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=ScriptedResponder(confirm_answers=[True]), root=root, now=_T0,
    )
    o2 = checkpoint_calibration.resurface(
        builder_id=BUILDER_A, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=ScriptedResponder(confirm_answers=[True]), root=root, now=_T0 + timedelta(days=3),
    )
    # the schedule advanced on the same card — second due is later than first
    assert datetime.fromisoformat(o2.next_due) > datetime.fromisoformat(o1.next_due)


# ── 6. the engagement→grade wire (bite 3) ────────────────────────────────────

def _resurface_held(root, responder, now=_T0):
    return checkpoint_calibration.resurface(
        builder_id=BUILDER_A, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=responder, root=root, now=now,
    )


def test_held_justification_is_scored_and_surfaced_on_the_outcome(tmp_path):
    """The score itself is fsrs-independent — assert the engagement value
    regardless of whether real FSRS is installed."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    strong = _resurface_held(root, ScriptedResponder(confirm_answers=[True], justify_answers=[_SUBSTANTIVE_JUSTIFICATION]))
    assert strong.held is True
    assert strong.engagement is not None and strong.engagement > 0.66

    _seal_original_auth_decision(root, builder_id="b" * 32)
    thin = checkpoint_calibration.resurface(
        builder_id="b" * 32, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=ScriptedResponder(confirm_answers=[True], justify_answers=[_THIN_JUSTIFICATION]),
        root=root, now=_T0,
    )
    assert thin.engagement is not None and thin.engagement < 0.34

    _seal_original_auth_decision(root, builder_id="c" * 32)
    declined = checkpoint_calibration.resurface(
        builder_id="c" * 32, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
        responder=ScriptedResponder(confirm_answers=[True]), root=root, now=_T0,  # no justify_answers -> declines
    )
    assert declined.engagement is None  # no signal, not a fabricated 0.0


@_needs_fsrs
def test_a_re_argued_hold_is_due_later_than_a_thin_hold_which_is_due_later_than_none(tmp_path):
    """The wire actually moving the schedule: Easy (re-argued) pushes the next
    review well past Good (declined) past Hard (thin). This is the whole point
    of closing the wire — the signal bends the cadence, it isn't just recorded."""
    def _due(builder, justify_answers):
        root = tmp_path / builder
        _seal_original_auth_decision(root, builder_id=builder)
        o = checkpoint_calibration.resurface(
            builder_id=builder, decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE,
            responder=ScriptedResponder(confirm_answers=[True], justify_answers=justify_answers),
            root=root, now=_T0,
        )
        return datetime.fromisoformat(o.next_due)

    due_easy = _due("a" * 32, [_SUBSTANTIVE_JUSTIFICATION])
    due_good = _due("b" * 32, [])                    # declined -> Good
    due_hard = _due("c" * 32, [_THIN_JUSTIFICATION])
    assert due_easy > due_good > due_hard


def test_a_hold_is_never_blocked_by_a_thin_justification(tmp_path):
    """Non-punitive: a rubber-stamp justification still leaves the decision
    held and sealed — only the review cadence tightens."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    outcome = _resurface_held(root, ScriptedResponder(confirm_answers=[True], justify_answers=[_THIN_JUSTIFICATION]))
    assert outcome.held is True
    assert outcome.regressed is False
    with checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        result = cm.check(ORIGINAL_SURFACE)
        assert result["sealed"] is True
        assert result["canonical"] == CHOSEN_ANSWER  # unchanged — a hold, not a reseal


def test_a_responder_without_justify_reverts_to_pre_wire_behavior(tmp_path):
    """Duck-typing: a Responder that only does confirm/choose is never asked to
    justify, so engagement is None and the hold grades Good exactly as it did
    before the wire existed."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    class _ConfirmOnly:
        def confirm(self, prompt): return True
        def choose(self, decision):  # pragma: no cover - a held path never reaches choose
            raise AssertionError("held path must not call choose")

    outcome = _resurface_held(root, _ConfirmOnly())
    assert outcome.held is True
    assert outcome.engagement is None
    assert outcome.next_due  # still scheduled (Good)


# ── 6. soft-Nestor on resurface ──────────────────────────────────────────────

@contextlib.contextmanager
def _nestor_blocked():
    """Same technique `tests/test_checkpoint.py`'s own `_nestor_blocked`
    uses — meta-path finder + `sys.modules` eviction — restated here since
    this file needs its own fresh module chain to observe it (see below)."""
    saved = {name: mod for name, mod in sys.modules.items() if name == "nestor" or name.startswith("nestor.")}
    for name in saved:
        del sys.modules[name]

    class _BlockNestor:
        def find_spec(self, name, path, target=None):
            if name == "nestor" or name.startswith("nestor."):
                raise ImportError(f"blocked for test: {name}")
            return None

    finder = _BlockNestor()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(saved)


def test_soft_nestor_on_resurface_degrades_honestly_never_crashes(tmp_path):
    root = tmp_path / "checkpoints"
    responder = ScriptedResponder()

    with _nestor_blocked():
        # A FRESH module chain, not the shared `checkpoint_calibration`
        # object every other test in this file uses — `_nestor()`'s cache
        # (checkpoint_memory.py) only ever caches SUCCESS, and the shared
        # module already cached one in every test above. See
        # `tests/test_checkpoint.py`'s own identical comment.
        fresh_spec = importlib.util.spec_from_file_location(
            "checkpoint_calibration_degraded_probe", _REPO / "stores" / "checkpoint_calibration.py"
        )
        fresh_calibration = importlib.util.module_from_spec(fresh_spec)
        sys.modules["checkpoint_calibration_degraded_probe"] = fresh_calibration
        fresh_spec.loader.exec_module(fresh_calibration)

        assert fresh_calibration.checkpoint_memory.nestor_available() is False

        with pytest.raises(fresh_calibration.CalibrationError):
            fresh_calibration.resurface(
                builder_id=BUILDER_A,
                decision_type=DECISION_TYPE,
                surface=ORIGINAL_SURFACE,
                responder=responder,
                root=root,
            )

    # never touched the filesystem — no memory to resurface against
    assert not root.exists()
    assert responder.confirm_prompts == []
    assert responder.choose_calls == []

    # Nestor is genuinely usable again right after, in this same process.
    assert checkpoint_memory.nestor_available() is True
