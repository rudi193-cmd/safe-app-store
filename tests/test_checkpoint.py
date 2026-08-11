"""Tests for stores/checkpoint.py — the D8 checkpoint interaction, bite 1
of The Forge's learning layer (docs/design/the-forge.md, "Verification-as-
learning", 2026-08-11).

**Honest environment note, same as `tests/test_checkpoint_memory.py`'s own**
(and, transitively, this file's own — `checkpoint.py` loads the real
`checkpoint_memory.py`, which uses the real Nestor library for every test
here except the soft-Nestor degradation test, which deliberately blocks it).
See that file's module docstring for the `pip install -e /workspace/nestor`
note and the `NESTOR_SEAL_KEY`-unset `RuntimeWarning` this repo's tests all
silence the same way.

Every fixture here calls `checkpoint.run_checkpoint` through a fully
SCRIPTED `Responder` (`ScriptedResponder`, below) — no real maker UI exists
yet (see `checkpoint.py`'s own `Responder` docstring); each test pre-loads
the exact sequence of confirm/choose answers a real maker would have given
in that scenario and asserts on what `run_checkpoint` actually did with
them, not on what a UI displayed.
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("checkpoint", _REPO / "stores" / "checkpoint.py")
checkpoint = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint"] = checkpoint
_spec.loader.exec_module(checkpoint)

Decision = checkpoint.Decision
Option = checkpoint.Option
ChoiceResult = checkpoint.ChoiceResult

pytestmark = pytest.mark.filterwarnings(
    "ignore:NESTOR_SEAL_KEY not set.*:RuntimeWarning"
)

BUILDER_A = "a" * 32  # path-safe under principal.py's _check_builder_id, same fixture value test_checkpoint_memory.py uses


class ScriptedResponder:
    """A `Responder` whose every answer is pre-loaded by the test, in call
    order — the smallest possible stand-in for a maker who isn't there yet
    (see `checkpoint.py`'s `Responder` docstring). Records every prompt/
    decision it was actually asked about, so a test can assert not just
    "the flow finished" but "the flow asked exactly this, in this band."
    """

    def __init__(self, confirm_answers=None, choose_answers=None):
        self._confirm_answers = list(confirm_answers or [])
        self._choose_answers = list(choose_answers or [])
        self.confirm_prompts: list[str] = []
        self.choose_calls: list[Decision] = []

    def confirm(self, prompt: str) -> bool:
        self.confirm_prompts.append(prompt)
        if not self._confirm_answers:
            raise AssertionError(f"ScriptedResponder.confirm asked with no answer queued: {prompt!r}")
        return self._confirm_answers.pop(0)

    def choose(self, decision: Decision) -> ChoiceResult:
        self.choose_calls.append(decision)
        if not self._choose_answers:
            raise AssertionError(f"ScriptedResponder.choose asked with no answer queued: {decision.surface!r}")
        return self._choose_answers.pop(0)


# ── the auth-flow fixture the design doc's own loose-recognition example uses ──
#
# Same decision_type/surface/answer the design doc's "Decisions settled
# (2026-08-11)" section measures directly ("the auth decision reworded
# scored 0.65 confidence in Nestor") — several tests below share this setup
# rather than each inventing their own, so the confidence numbers asserted
# are directly traceable to that design-doc claim.
DECISION_TYPE = "auth-flow-for-user-facing-form"
ORIGINAL_SURFACE = "How should the login form authenticate?"
REWORDED_SURFACE = "What auth should the sign-in form use?"
CHOSEN_ANSWER = "session cookie + CSRF"
AUTH_OPTIONS = (
    Option("session cookie + CSRF", "server-side session state, needs a CSRF token"),
    Option("JWT bearer token", "stateless, needs a revocation strategy"),
)


def _seal_original_auth_decision(root: Path, builder_id: str = BUILDER_A) -> None:
    """Seals the ORIGINAL wording directly through `checkpoint_memory` — as
    if a full-Socratic checkpoint already ran once for this builder, the
    way `test_full_socratic_...` below exercises for real. Kept as its own
    helper because several tests need this exact prior state as their
    starting point, not their own subject under test."""
    with checkpoint.checkpoint_memory.open_checkpoint_memory(builder_id, DECISION_TYPE, root=root) as cm:
        cm.seal(ORIGINAL_SURFACE, CHOSEN_ANSWER)


# ── 1. full Socratic on a fresh decision-type ───────────────────────────────

def test_full_socratic_on_fresh_decision_type_seals_and_is_a_sealed_hit_on_repeat(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="schema-normalization-tradeoff",
        surface="Should the orders table be normalized or denormalized for reporting?",
        options=(
            Option("normalized", "cleaner writes, reporting needs joins"),
            Option("denormalized", "fast reporting, write-side duplication risk"),
        ),
        recommended="normalized",
    )
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="normalized", rationale="writes dominate this table")]
    )

    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.band == "socratic"
    assert outcome.deferred is False
    assert outcome.sealed is True
    assert outcome.memory_available is True
    assert outcome.chosen == "normalized"
    assert outcome.rationale == "writes dominate this table"
    assert responder.confirm_prompts == []  # a fresh decision-type never asks a confirm
    assert len(responder.choose_calls) == 1

    # Now the memory promise D9/D12 exist for: the SAME wording, asked
    # again, is a real Nestor tier-1 hit — not just "this module says it
    # sealed something."
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, decision.decision_type, root=root) as cm:
        result = cm.check(decision.surface)
        assert result["sealed"] is True
        assert result["canonical"] == "normalized: writes dominate this table"


def test_decision_with_no_options_is_refused_before_touching_memory(tmp_path):
    decision = Decision(decision_type="empty-decision", surface="anything", options=())
    responder = ScriptedResponder()
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.run_checkpoint(
            decision, builder_id=BUILDER_A, responder=responder, root=tmp_path / "checkpoints"
        )
    # Refused before any memory file existed at all — matches
    # checkpoint_memory.py's own "no file left behind on hostile input"
    # discipline, extended one caller up.
    assert not (tmp_path / "checkpoints").exists()


# ── 2. loose recognition — the headline ─────────────────────────────────────

def test_loose_recognition_reworded_decision_routes_to_recognize_band_and_seals_on_confirm(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    # Confirm the fixture is exercising a genuine sub-threshold recognition,
    # not a coincidence: measured directly, BEFORE run_checkpoint touches
    # anything else, the same way test_checkpoint_memory.py's own
    # DECISION_TEXT_VARIANT fixture is measured against nestor.matcher in
    # that file's own module docstring.
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        pre = cm.check(REWORDED_SURFACE)
    assert pre["sealed"] is False
    assert 0.6 <= pre["confidence"] < 0.92
    assert pre["provenance"]["suggestion"] == CHOSEN_ANSWER

    decision = Decision(decision_type=DECISION_TYPE, surface=REWORDED_SURFACE, options=AUTH_OPTIONS)
    responder = ScriptedResponder(confirm_answers=[True])

    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.band == "recognize"
    assert outcome.sealed is True
    assert outcome.deferred is False
    assert outcome.chosen == CHOSEN_ANSWER
    assert outcome.memory_available is True
    assert responder.choose_calls == []  # never fell through to full Socratic
    assert len(responder.confirm_prompts) == 1
    assert CHOSEN_ANSWER in responder.confirm_prompts[0]  # the prior answer was actually shown

    # "so next time it's an auto hit" — the design doc's own line: the
    # reworded wording, now sealed too, is a genuine tier-1 hit on repeat.
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        result = cm.check(REWORDED_SURFACE)
        assert result["sealed"] is True
        assert result["canonical"] == CHOSEN_ANSWER


def test_auto_band_on_a_genuine_sealed_hit_is_a_light_confirm_with_no_re_seal(tmp_path, monkeypatch):
    """The auto band, the recognize band's stricter sibling: the SAME
    wording that was sealed (not a rewording) is a real `sealed=True` hit,
    gets only a light confirm, and — unlike recognize's confirm, which DOES
    re-seal the new wording — never calls `seal` again, since nothing new
    needs recording."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    seal_calls = []
    original_seal = checkpoint.checkpoint_memory.CheckpointMemory.seal

    def _spy_seal(self, *a, **kw):
        seal_calls.append((a, kw))
        return original_seal(self, *a, **kw)

    monkeypatch.setattr(checkpoint.checkpoint_memory.CheckpointMemory, "seal", _spy_seal)

    decision = Decision(decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS)
    responder = ScriptedResponder(confirm_answers=[True])

    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.band == "auto"
    assert outcome.sealed is True
    assert outcome.chosen == CHOSEN_ANSWER
    assert responder.choose_calls == []
    assert seal_calls == []  # already sealed going in — confirmed, not re-sealed


# ── 3. the escape teaches ────────────────────────────────────────────────────

def test_recognize_band_different_teaches_reject_match_and_falls_through_to_socratic(tmp_path, monkeypatch):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    reject_calls = []
    original_reject_match = checkpoint.checkpoint_memory.CheckpointMemory.reject_match

    def _spy_reject_match(self, *a, **kw):
        reject_calls.append((a, kw))
        return original_reject_match(self, *a, **kw)

    monkeypatch.setattr(checkpoint.checkpoint_memory.CheckpointMemory, "reject_match", _spy_reject_match)

    decision = Decision(decision_type=DECISION_TYPE, surface=REWORDED_SURFACE, options=AUTH_OPTIONS)
    responder = ScriptedResponder(
        confirm_answers=[False],
        choose_answers=[
            ChoiceResult(
                chosen_label="JWT bearer token",
                rationale="this form serves a public API client, not a browser session",
            )
        ],
    )

    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    # reject_match really was invoked — not just "the flow didn't crash" —
    # with the reworded surface and the prior canonical as its identifying
    # handle (no pair_id exists at sub-threshold; see checkpoint.py's own
    # module docstring for why).
    assert len(reject_calls) == 1
    args, kwargs = reject_calls[0]
    assert args[0] == REWORDED_SURFACE
    assert kwargs.get("target_text") == CHOSEN_ANSWER

    # ...and the flow genuinely fell through to full Socratic, not a
    # silent no-op.
    assert len(responder.choose_calls) == 1
    assert outcome.band == "socratic"
    assert outcome.sealed is True
    assert outcome.chosen == "JWT bearer token"
    assert outcome.rationale == "this form serves a public API client, not a browser session"

    # And the new answer is what's actually sealed now for this wording.
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        result = cm.check(REWORDED_SURFACE)
        assert result["sealed"] is True
        assert result["canonical"] == (
            "JWT bearer token: this form serves a public API client, not a browser session"
        )


# ── 4. "you choose" deferral ─────────────────────────────────────────────────

def test_deferral_seals_as_a_taught_decision_and_a_repeat_does_not_re_socratic(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="library-choice-for-http-client",
        surface="Which HTTP client library should this build use?",
        options=(
            Option("requests", "battle-tested, synchronous only"),
            Option("httpx", "async-capable, newer, smaller ecosystem"),
        ),
        recommended="httpx",
    )
    responder = ScriptedResponder(choose_answers=[ChoiceResult(deferred=True)])

    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.deferred is True
    assert outcome.sealed is True
    assert outcome.band == "socratic"
    assert outcome.chosen == "httpx"  # decision.recommended, not guessed

    with checkpoint.checkpoint_memory.open_checkpoint_memory(
        BUILDER_A, decision.decision_type, root=root
    ) as cm:
        result = cm.check(decision.surface)
        assert result["sealed"] is True
        assert result["canonical"].startswith("[deferred] httpx")
        assert "handed the call to the Forge" in result["canonical"]

    # A repeat of the identical decision does not re-badger the maker —
    # it's now an auto-band hit, a light confirm only.
    responder2 = ScriptedResponder(confirm_answers=[True])
    outcome2 = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder2, root=root)
    assert outcome2.band == "auto"
    assert outcome2.sealed is True
    assert responder2.choose_calls == []


def test_deferral_with_no_recommended_falls_back_to_first_option(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="error-handling-strategy",
        surface="How should this build handle a failed downstream call?",
        options=(
            Option("retry with backoff", "resilient, adds latency on failure"),
            Option("fail fast", "simple, pushes recovery to the caller"),
        ),
        # no recommended
    )
    responder = ScriptedResponder(choose_answers=[ChoiceResult(deferred=True)])
    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)
    assert outcome.chosen == "retry with backoff"  # decision.options[0].label
    assert outcome.deferred is True
    assert outcome.sealed is True


# ── 5. soft-Nestor degradation ───────────────────────────────────────────────

@contextlib.contextmanager
def _nestor_blocked():
    """Evicts `nestor`/`nestor.*` from `sys.modules` and installs a
    meta-path finder that refuses to import them, for the duration of the
    `with` block — mirrors `oakenscrolls-office` PR #3's
    `test_almanac_seam_degraded.py` technique (meta-path finder +
    `sys.modules` eviction), restated for this repo's own test since that
    file itself isn't present in this checkout to import directly (see
    `docs/design/the-forge.md`'s own "Nestor is a SOFT dependency" line for
    the pattern being mirrored, not copied file-for-file).

    Restores the evicted modules and removes the finder on exit, in a
    `finally`, so this never leaks into `test_checkpoint_memory.py` (which
    genuinely needs real Nestor) or any test that runs after this one in
    the same process.
    """
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


def test_soft_nestor_degradation_runs_full_socratic_without_crashing(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="algorithm-choice",
        surface="Which structure should back this build's own priority queue?",
        options=(
            Option("binary heap", "O(log n) push/pop, simple, array-backed"),
            Option("skip list", "O(log n) expected, supports fast range queries"),
        ),
    )
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="binary heap", rationale="no range queries needed here")]
    )

    with _nestor_blocked():
        # A FRESH module load, not the shared `checkpoint` object every
        # other test in this file uses — `_nestor()`'s cache (see
        # checkpoint_memory.py) only ever caches SUCCESS, but the shared
        # `checkpoint` module already cached a successful import in every
        # test above; reusing it here would silently observe the stale
        # cached success instead of this block's real, freshly-blocked
        # environment. A fresh load starts with a virgin, uncached
        # `_nestor()`, so `nestor_available()` genuinely re-probes.
        fresh_spec = importlib.util.spec_from_file_location(
            "checkpoint_degraded_probe", _REPO / "stores" / "checkpoint.py"
        )
        fresh_checkpoint = importlib.util.module_from_spec(fresh_spec)
        sys.modules["checkpoint_degraded_probe"] = fresh_checkpoint
        fresh_spec.loader.exec_module(fresh_checkpoint)

        assert fresh_checkpoint.checkpoint_memory.nestor_available() is False

        outcome = fresh_checkpoint.run_checkpoint(
            decision, builder_id=BUILDER_A, responder=responder, root=root
        )

    assert outcome.band == "socratic"
    assert outcome.sealed is False
    assert outcome.memory_available is False
    assert outcome.deferred is False
    assert outcome.chosen == "binary heap"
    assert outcome.rationale == "no range queries needed here"
    # No seal, so nothing to attest — governance stays empty on this path.
    assert outcome.attestation_id == ""
    # Never touched the filesystem either — no memory to write to.
    assert not root.exists()

    # And Nestor is genuinely usable again, in this same process, right
    # after the block exits — proves the fixture actually restores state
    # rather than merely not crashing the one test that used it.
    assert checkpoint.checkpoint_memory.nestor_available() is True


# ── 6. band thresholds ───────────────────────────────────────────────────────

def test_a_clearly_different_decision_routes_to_socratic_not_recognize(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    decision = Decision(
        decision_type=DECISION_TYPE,
        surface="What database engine should we use for the analytics warehouse?",
        options=(
            Option("Postgres", "the team already knows it"),
            Option("ClickHouse", "faster for this workload, unfamiliar"),
        ),
    )
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="Postgres", rationale="the team already knows it")]
    )

    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.band == "socratic"
    assert responder.confirm_prompts == []  # never asked a confirm-style question at all
    assert len(responder.choose_calls) == 1
    assert outcome.sealed is True
    assert outcome.chosen == "Postgres"


def test_recognize_threshold_is_the_forges_own_not_nestors(tmp_path):
    """The design doc's own line, restated as a test: the recognize
    threshold is a parameter of THIS module, not Nestor's `sealed` flag.
    Setting `recognize_threshold` above the measured sub-threshold
    confidence for the reworded auth decision pushes the SAME situation
    that routed to `recognize` in test 2 down into `socratic` instead —
    proving the split is genuinely enforced here, not inherited from
    Nestor's own (unrelated) `SEAL_THRESHOLD`."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        measured_confidence = cm.check(REWORDED_SURFACE)["confidence"]
    assert measured_confidence < 0.92  # still not a Nestor tier-1 hit on its own

    decision = Decision(decision_type=DECISION_TYPE, surface=REWORDED_SURFACE, options=AUTH_OPTIONS)
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="session cookie + CSRF", rationale="matches the prior call")]
    )

    outcome = checkpoint.run_checkpoint(
        decision,
        builder_id=BUILDER_A,
        responder=responder,
        root=root,
        recognize_threshold=measured_confidence + 0.05,  # raise the bar above what was actually measured
    )

    assert outcome.band == "socratic"
    assert len(responder.choose_calls) == 1


# ── 7. engagement signal (bite 3) — a seal-time signal, never a block ────────

def test_socratic_with_a_substantive_rationale_scores_high_engagement_not_rubber_stamp(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="schema-normalization-tradeoff",
        surface="Should the orders table be normalized or denormalized for reporting?",
        options=(Option("normalized", "cleaner writes"), Option("denormalized", "fast reporting")),
    )
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(
            chosen_label="denormalized",
            rationale=("I measured the reporting query at 1.2s with joins and tested a denormalized "
                       "copy at 40ms; writes are rare here so the duplication risk is acceptable"),
        )]
    )
    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.band == "socratic"
    assert outcome.sealed is True
    assert outcome.engagement is not None and outcome.engagement > 0.34
    assert outcome.rubber_stamp is False


def test_socratic_with_a_thin_rationale_is_flagged_rubber_stamp_but_still_seals(tmp_path):
    """The whole point: a rubber-stamp is a SIGNAL, not a gate — the seal
    happens anyway (checkpoint_engagement's "never blocks")."""
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="cache-eviction-policy",
        surface="Which cache eviction policy should this build use?",
        options=(Option("LRU", "recency"), Option("LFU", "frequency")),
    )
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="LRU", rationale="sure")]
    )
    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.rubber_stamp is True
    assert outcome.engagement is not None and outcome.engagement < 0.34
    assert outcome.sealed is True  # NEVER blocked
    # and it really is durably sealed despite the thin rationale
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, decision.decision_type, root=root) as cm:
        assert cm.check(decision.surface)["sealed"] is True


def test_an_empty_rationale_is_the_loudest_rubber_stamp(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="log-format-choice",
        surface="What log format should this build emit?",
        options=(Option("json", "machine-readable"), Option("text", "human-readable")),
    )
    responder = ScriptedResponder(choose_answers=[ChoiceResult(chosen_label="json", rationale="")])
    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)
    assert outcome.engagement == 0.0
    assert outcome.rubber_stamp is True
    assert outcome.sealed is True


def test_auto_and_recognize_confirms_have_no_engagement_reading(tmp_path):
    """Reusing a PRIOR seal (auto/recognize confirm) means the maker gave no
    fresh rationale — engagement is None, not a fabricated 0.0, and never a
    rubber-stamp."""
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)

    # auto: same wording, a light confirm
    auto = checkpoint.run_checkpoint(
        Decision(decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS),
        builder_id=BUILDER_A, responder=ScriptedResponder(confirm_answers=[True]), root=root,
    )
    assert auto.band == "auto"
    assert auto.engagement is None
    assert auto.rubber_stamp is False

    # recognize: reworded, a light confirm
    rec = checkpoint.run_checkpoint(
        Decision(decision_type=DECISION_TYPE, surface=REWORDED_SURFACE, options=AUTH_OPTIONS),
        builder_id=BUILDER_A, responder=ScriptedResponder(confirm_answers=[True]), root=root,
    )
    assert rec.band == "recognize"
    assert rec.engagement is None
    assert rec.rubber_stamp is False


def test_a_deferral_is_not_a_rubber_stamp(tmp_path):
    """"You choose" is a legitimate taught handoff — no rationale to score,
    so engagement is None and rubber_stamp is False, never conflated with a
    thin-rationale rubber-stamp."""
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type="serialization-format",
        surface="Which serialization format should this build use on the wire?",
        options=(Option("protobuf", "compact, needs a schema"), Option("json", "ubiquitous, larger")),
        recommended="protobuf",
    )
    responder = ScriptedResponder(choose_answers=[ChoiceResult(deferred=True)])
    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)
    assert outcome.deferred is True
    assert outcome.engagement is None
    assert outcome.rubber_stamp is False


# ── 8. governance: attestation under the seal + the park/resume async seam ───
#     (human_loop adoption, docs/design/the-forge-human-loop.md)

_gov = checkpoint.checkpoint_governance


def _pair_id(builder_id, decision_type, surface, root):
    with checkpoint.checkpoint_memory.open_checkpoint_memory(builder_id, decision_type, root=root) as cm:
        return cm.check(surface)["provenance"]["pair_id"]


def _schema_decision():
    return Decision(
        decision_type="schema-normalization-tradeoff",
        surface="Should the orders table be normalized or denormalized?",
        options=(Option("normalized", "cleaner writes"), Option("denormalized", "fast reporting")),
    )


def test_socratic_commit_attests_but_not_as_human_by_default(tmp_path):
    """A commit writes an attestation bound to the builder, but does NOT claim a
    human signed it: a ScriptedResponder is a machine, the Forge has no D11
    identity to prove otherwise, so `by_human` defaults False and
    `require_human=True` is honestly unsatisfiable. (The first cut stamped
    by_human=True unconditionally — an automated responder minted a 'human'
    attestation; the adversarial audit caught it.)"""
    root = tmp_path / "checkpoints"
    decision = _schema_decision()
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="normalized", rationale="writes dominate this table")]
    )
    outcome = checkpoint.run_checkpoint(decision, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.attestation_id  # a governance record was written...
    pid = _pair_id(BUILDER_A, decision.decision_type, decision.surface, root)
    assert _gov.has_decision_attestation(BUILDER_A, pid, root=root) is True
    # ...but it is NOT a human sign-off, because nothing proved a human answered
    assert _gov.has_decision_attestation(BUILDER_A, pid, require_human=True, root=root) is False


def test_an_explicit_human_binding_produces_a_human_attestation(tmp_path):
    """When a caller CAN establish human presence (a real UI, post-D11), it
    passes by_human=True and the attestation counts under require_human — the
    property is real, driven by a binding, not stamped by default."""
    root = tmp_path / "checkpoints"
    decision = _schema_decision()
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="normalized", rationale="writes dominate")]
    )
    outcome = checkpoint.run_checkpoint(
        decision, builder_id=BUILDER_A, responder=responder, root=root, by_human=True
    )
    assert outcome.attestation_id
    pid = _pair_id(BUILDER_A, decision.decision_type, decision.surface, root)
    assert _gov.has_decision_attestation(BUILDER_A, pid, require_human=True, root=root) is True


def test_auto_confirm_attests_the_reaffirmation(tmp_path):
    root = tmp_path / "checkpoints"
    _seal_original_auth_decision(root)
    outcome = checkpoint.run_checkpoint(
        Decision(decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS),
        builder_id=BUILDER_A, responder=ScriptedResponder(confirm_answers=[True]), root=root,
    )
    assert outcome.band == "auto"
    assert outcome.attestation_id  # a confirm is a fresh on-the-record sign-off


def test_park_checkpoint_enqueues_evidence_and_seals_nothing(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(
        decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS,
        recommended="session cookie + CSRF",
    )
    item_id = checkpoint.park_checkpoint(decision, builder_id=BUILDER_A, root=root)
    assert item_id
    assert len(_gov.open_items(BUILDER_A, root=root)) == 1  # a human_required item is waiting
    # parking is not deciding — nothing sealed, nothing attested
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        assert cm.check(ORIGINAL_SURFACE)["sealed"] is False


def test_resume_checkpoint_seals_attests_and_resolves_the_item(tmp_path):
    root = tmp_path / "checkpoints"
    decision = Decision(decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS)
    item_id = checkpoint.park_checkpoint(decision, builder_id=BUILDER_A, root=root)

    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="session cookie + CSRF", rationale="server-rendered form")]
    )
    outcome = checkpoint.resume_checkpoint(item_id, builder_id=BUILDER_A, responder=responder, root=root)

    assert outcome.sealed is True
    assert outcome.attestation_id
    assert _gov.open_items(BUILDER_A, root=root) == []  # resolved in place, not left open
    with checkpoint.checkpoint_memory.open_checkpoint_memory(BUILDER_A, DECISION_TYPE, root=root) as cm:
        assert cm.check(ORIGINAL_SURFACE)["sealed"] is True  # now durably decided

    # single-use: the same parked item cannot be resumed a second time (it would
    # mint a duplicate seal+attestation for a decision already on the record)
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.resume_checkpoint(
            item_id, builder_id=BUILDER_A,
            responder=ScriptedResponder(choose_answers=[ChoiceResult(chosen_label="JWT bearer token", rationale="x")]),
            root=root,
        )


def test_resume_an_unknown_item_raises(tmp_path):
    with pytest.raises(checkpoint.CheckpointError):
        checkpoint.resume_checkpoint(
            "no-such-item", builder_id=BUILDER_A,
            responder=ScriptedResponder(), root=tmp_path / "checkpoints",
        )


def test_resume_leaves_the_item_open_when_the_seal_fails(tmp_path, monkeypatch):
    """If memory is unavailable at resume time, run_checkpoint can't seal — the
    parked item must NOT be consumed (resolving it with no seal + no attestation
    would lose the decision permanently, since single-use blocks a retry). It
    stays open for a real retry once memory is back. (Bug caught by the
    adversarial audit of the first cut.)"""
    root = tmp_path / "checkpoints"
    decision = Decision(decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS)
    item_id = checkpoint.park_checkpoint(decision, builder_id=BUILDER_A, root=root)

    def _unsealed(decision, *, builder_id, responder, root, by_human=False):
        return checkpoint.CheckpointOutcome(
            decision_type=decision.decision_type, chosen="x", rationale="", band="socratic",
            deferred=False, sealed=False, memory_available=False,
        )

    monkeypatch.setattr(checkpoint, "run_checkpoint", _unsealed)
    outcome = checkpoint.resume_checkpoint(
        item_id, builder_id=BUILDER_A, responder=ScriptedResponder(), root=root
    )
    assert outcome.sealed is False
    # NOT consumed: still open, and the parked decision is still retrievable
    assert len(_gov.open_items(BUILDER_A, root=root)) == 1
    assert _gov.get_parked_decision(BUILDER_A, item_id, root=root) is not None
