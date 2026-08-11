#!/usr/bin/env python3
"""stores/checkpoint.py — The Forge's D8 checkpoint interaction, bite 1 of
the learning layer (docs/design/the-forge.md, "Verification-as-learning —
the willow-mcp reuse map", 2026-08-11).

D8 names the mode: every design/implementation decision the model is about
to make on the builder's behalf stops and poses the decision as a question
with real options and tradeoffs, before writing anything — the builder
answers, and the code that gets written matches their answer. D9/D12 give
that interaction a memory: `stores/checkpoint_memory.py` (already built,
this module's only real dependency) answers "has this builder sealed this
decision-type before" via a per-builder Nestor `EntityResolver`. **This
module is the interaction on top of that memory** — the three-band router
the 2026-08-11 design-doc section settled on, and nothing more:

    Decision --check() against builder's own memory--> band (auto |
    recognize | socratic) --present/confirm, per band--> CheckpointOutcome
    (chosen, rationale, sealed?)

Store-side authority (D1), same directory and same trust level as
`checkpoint_memory.py`, `principal.py`, `session.py`: `apps/the-forge/`
never imports this module, for the same reason it never imports
`checkpoint_memory.py` — a builder's own calibration record is not
something a sandboxed build in `apps/` gets to read or write about itself.

**The three bands, settled 2026-08-11 (not this module's own invention —
recorded in the design doc, restated here as code):**

  * **auto** — Nestor's own `sealed=True` hit (>= its `SEAL_THRESHOLD`,
    0.92 by default): a light confirm ("you chose X before, say so if
    it's different"), no re-seal on a plain confirm — it is already sealed.
  * **recognize** — a sub-threshold but real hit (`sealed=False`,
    `confidence >= recognize_threshold`, and a prior candidate exists):
    **loose recognition**, the headline decision this bite implements. A
    reworded-but-same decision still gets the lighter confirm rather than a
    fresh Socratic pass, because the confirm is never a silent commit — "it's
    different" always escapes to `reject_match` + full Socratic, so loose
    recognition cannot commit the wrong thing; the worst case is one extra
    "actually, different" that teaches the memory to stop conflating the two.
    **The recognize threshold lives HERE, not in Nestor** — Nestor's own
    `sealed` flag stays at its own threshold; this module reads the raw
    `confidence` Nestor returns and applies its own, separate split.
  * **socratic** — everything else: low confidence, or no prior memory at
    all, or memory unavailable outright (see soft-Nestor gate, below).
    Options + tradeoffs are presented for real; "I don't know, you choose"
    is a legitimate answer that still gets sealed **as a taught deferral**
    (the maker saw the tradeoff and deliberately handed it back), not a
    block — see `_full_socratic`'s own docstring.

**What "the prior canonical" is, and where it comes from below threshold —
verified against `nestor.entity.EntityResolver.resolve`'s real return
shape, not assumed:** `checkpoint_memory.check()` is a thin wrapper over
`resolve()`, which returns `{"canonical": str | None, "confidence": float,
"sealed": bool, "provenance": {...}}`. At/above Nestor's own seal
threshold, `canonical` IS populated (the auto band reads it straight from
there). **Below that threshold, `canonical` is always `None`** — Nestor
only populates `canonical` for an actual sealed serve, never for a draft
suggestion, precisely so nothing downstream can mistake an unsealed
candidate for a committed answer by accident. The recognize band therefore
reads the prior answer from `result["provenance"]["suggestion"]` instead —
`EntityResolver.resolve`'s own code sets `provenance["suggestion"] =
pair["target_text"]` for exactly this case (the top sub-threshold
candidate's own canonical text). This module does not fabricate a
candidate some other way; it reads the one field Nestor's own recipe
already puts there for this. One consequence worth naming: the sub-threshold
provenance dict does NOT carry a `pair_id` (only the sealed-hit path does),
so the recognize band's own `reject_match` call below identifies the pair
by `target_text=prior_canonical` instead of `pair_id` — the auto band's
"not this" path, which DOES have a real `provenance["pair_id"]` (a genuine
tier-1 hit), uses that instead. Different bands, different identifying
handle, because that is genuinely what Nestor hands back at each tier.

**Soft-Nestor gate — the degradation lives HERE, not in
`checkpoint_memory.py`.** `checkpoint_memory.nestor_available()` (Part A of
this bite) is checked FIRST, before this module does anything else. False
means: skip memory entirely, go straight to full Socratic, and return an
outcome honestly marked `band="socratic"`, `sealed=False`,
`memory_available=False` — never crash, never silently pretend memory
exists. `checkpoint_memory.py` itself still refuses outright (via
`CheckpointMemoryError`) if something in IT is asked to operate without
Nestor; this module's whole job on that front is to never ask it to.

**Exception discipline, matching `forge_build.py`/`seam.py`.** This module
does NOT wrap `checkpoint_memory.CheckpointMemoryError` (or its
`CheckpointConflict`/`CheckpointRejected` subclasses) in a second layer —
they already are the "one exception type at the call site"
`checkpoint_memory.py`'s own docstring promises, the same way
`forge_build.py` lets `SandboxError`/`PlanError`/`GateError`/`SeamError`
propagate from the stages it calls rather than paper over each one. This
module's own `CheckpointError` exists ONLY for refusals that are this
orchestrator's own — a `Decision` with no options to present, or a
`Responder` whose answer doesn't make sense — never as a re-skin of a
lower layer's exception.

Not in scope, deliberately (see docs/design/the-forge.md's own bite
ladder): calibration/resurfacing (`#12` lesson-regression, `#3`
contradiction detection — bite 2), the engagement/friction gate (`#66`/
`#67` — bite 3), and wiring this to D7's real model routing or bite 0's
actual build path — every `Decision` this module sees is an EXPLICIT,
already-formed input (a stub standing in for D7's not-yet-existent model,
exactly as bite 0's `stub_builder` stood in for the same thing).

Usage (dev CLI, mirroring `forge_build.py`'s shape):
    python stores/checkpoint.py demo <builder_id> <decision_type> \\
        [--root DIR] [--recognize-threshold 0.6]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

_REPO = Path(__file__).resolve().parent.parent

# checkpoint_memory.py has no relative imports of its own — same
# spec_from_file_location pattern seam.py already uses to load sap_gate.py,
# and forge_build.py reuses seam.py's own loaded copy rather than loading it
# a second time. This module is the first OTHER caller of
# checkpoint_memory.py (forge_build.py/seam.py never touch it — D9/D12's
# memory is a separate axis from D3/D4/D5's build pipeline), so it loads its
# own copy here, the same way seam.py loads its own copy of sap_gate.py.
_spec = importlib.util.spec_from_file_location(
    "checkpoint_memory", _REPO / "stores" / "checkpoint_memory.py"
)
checkpoint_memory = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint_memory"] = checkpoint_memory
_spec.loader.exec_module(checkpoint_memory)

DEFAULT_RECOGNIZE_THRESHOLD = 0.6

Band = Literal["auto", "recognize", "socratic"]


class CheckpointError(Exception):
    """Refused by THIS orchestrator — never a re-wrap of
    `checkpoint_memory.CheckpointMemoryError` (or its
    `CheckpointConflict`/`CheckpointRejected` subclasses), which propagate
    as-is; see module docstring's "Exception discipline" section. Raised
    for input this module itself cannot make sense of: a `Decision` with no
    `options` to present, or a `Responder` answer that violates the
    minimal contract `choose()`/`confirm()` are documented to uphold."""


# ── the D7-stub input shape ─────────────────────────────────────────────────

@dataclass(frozen=True)
class Option:
    """One choice in a `Decision` — a label and the tradeoff that comes
    with picking it. Never presented alone; `Decision.options` is always a
    real set the maker can actually weigh against each other."""

    label: str
    tradeoff: str


@dataclass(frozen=True)
class Decision:
    """A design/implementation decision the model is about to make on the
    builder's behalf (D8) — EXPLICIT input to this module, a stub standing
    in for D7's not-yet-existent model, exactly the posture bite 0's
    `stub_builder` already took for D7 (see that module's own docstring).
    Nothing in this module infers a `Decision` from anything; a caller
    (eventually D7's routing layer) always hands one in fully formed.

    `decision_type`: the calibration key `checkpoint_memory` scopes memory
    to (D9's own line: "the seal domain must be `(builder_id,
    decision_type)`") — e.g. `"auth-flow-for-user-facing-form"`.
    `surface`: the actual question text this specific occurrence poses —
    what `checkpoint_memory.check()`/`.seal()` matches/records against.
    Two different `Decision`s can share a `decision_type` while having
    differently-worded `surface`s (that's the whole point of loose
    recognition — see module docstring).
    `options`: the real choices, never empty — `run_checkpoint` refuses a
    `Decision` with none (`CheckpointError`) rather than presenting nothing.
    `recommended`: the model's own default suggestion, if it has one — used
    ONLY as the fallback pick for a "you choose" deferral (see
    `_full_socratic`); never auto-applied on its own.
    """

    decision_type: str
    surface: str
    options: tuple[Option, ...]
    recommended: str | None = None


@dataclass(frozen=True)
class ChoiceResult:
    """The maker's answer to a full Socratic checkpoint — what
    `Responder.choose` returns. `deferred=True` ("I don't know, you
    choose") means `chosen_label`/`rationale` are not meaningful and are
    ignored; `run_checkpoint` picks `Decision.recommended` (or the first
    option) itself. See module docstring's "socratic" band."""

    chosen_label: str = ""
    rationale: str = ""
    deferred: bool = False


class Responder(Protocol):
    """The maker's answers — injected, since there is no maker UI yet (a
    scripted stub in tests, a real UI later; same "explicit input standing
    in for a not-yet-built surface" posture as `Decision` itself stands in
    for D7). The smallest interface the three-band flow actually needs:

      * `confirm(prompt) -> bool` — the light-touch yes/no the auto and
        recognize bands use ("you chose X before, say so if it's
        different"). `prompt` is plain text meant to be shown to a human
        as-is; this module does not otherwise structure it.
      * `choose(decision) -> ChoiceResult` — the full Socratic answer: pick
        an option (by returning its label as `chosen_label` plus a
        `rationale`), or defer (`deferred=True`).

    Deliberately NOT required: anything about follow-up questions that test
    whether the maker actually understood (vs. just picked) — D8's own
    "not just picked an option — explained why" bar is a real, undesigned
    UX question the module docstring's "Not in scope" section already
    defers to a later bite, not something this Protocol pre-guesses.
    """

    def confirm(self, prompt: str) -> bool: ...

    def choose(self, decision: Decision) -> ChoiceResult: ...


# ── the outcome ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CheckpointOutcome:
    """What `run_checkpoint` returns — every band lands here, so a caller
    never has to branch on which band ran to know what happened.

    `chosen`/`rationale`, restated honestly for the two shapes memory can
    hand back (an explicit architectural choice, not an oversight):
    `checkpoint_memory.seal()` stores ONE combined `canonical` string, not a
    separate `(chosen, rationale)` pair — so for a FRESH full-Socratic
    answer, `chosen`/`rationale` are the maker's own `chosen_label`/
    `rationale` from `ChoiceResult`, exactly as given. For an `auto` or
    `recognize` confirm — reusing a PRIOR seal rather than a fresh answer —
    there is nothing more granular to hand back than the one canonical
    string Nestor already returned; `chosen` carries that full string and
    `rationale` is `""` rather than this module inventing a split (e.g. by
    guessing where a `": "` separator might fall) that could silently
    mis-parse a rationale containing its own colon. See module docstring's
    "Exception discipline" section for the parallel choice not to guess
    at things a lower layer didn't hand over explicitly.

    `band`: which of the three bands actually ran — `"auto"` (a genuine
    Nestor `sealed=True` hit, confirmed), `"recognize"` (a sub-threshold
    loose match, confirmed), or `"socratic"` (either band's own "it's
    different" escape, a fresh unsealed decision-type, or the soft-Nestor
    degradation with memory unavailable outright).
    `deferred`: True only for "I don't know, you choose" — orthogonal to
    `band` (a deferral always runs through the socratic path, so `band` is
    always `"socratic"` when `deferred` is True, but not every
    `band="socratic"` outcome is a deferral).
    `sealed`: True iff this run left this decision durably recorded in
    memory — False only when memory was unavailable outright
    (`memory_available=False`) or the auto band's plain confirm ran (no
    re-seal needed — it was already sealed going in).
    `memory_available`: mirrors `checkpoint_memory.nestor_available()` at
    the START of this run — the soft-Nestor gate's own honest record,
    independent of `sealed`.
    """

    decision_type: str
    chosen: str
    rationale: str
    band: Band
    deferred: bool
    sealed: bool
    memory_available: bool


# ── the flow ─────────────────────────────────────────────────────────────────

def _full_socratic(decision: Decision, responder: Responder) -> tuple[str, str, bool]:
    """Present options+tradeoffs (the caller's job — a real UI later; this
    function's own job is just calling `responder.choose`), get the
    maker's answer. Returns `(chosen_label, rationale, deferred)`.

    `deferred=True` ("I don't know, you choose") is a legitimate answer,
    per the design doc's 2026-08-11 settlement, not a block: the maker saw
    the tradeoff and deliberately handed the call back. `chosen_label`
    becomes `decision.recommended` if the model had one, else the first
    option — never a guess this function invents on its own — and
    `rationale` is left empty here (the maker stated none; `run_checkpoint`
    records the deferral itself in the sealed canonical text, rather than
    this function fabricating a rationale on the maker's behalf)."""
    choice = responder.choose(decision)
    if choice.deferred:
        chosen_label = decision.recommended or decision.options[0].label
        return chosen_label, "", True
    if not choice.chosen_label:
        raise CheckpointError(
            "Responder.choose returned deferred=False with an empty chosen_label — "
            "nothing to seal"
        )
    return choice.chosen_label, choice.rationale, False


def _deferred_canonical(chosen_label: str) -> str:
    """The canonical text a taught deferral seals — records that the maker
    saw the tradeoff and deliberately handed it back, per the design doc's
    own example phrasing, not just the bare option label a plain choice
    would seal. Kept as its own function so `run_checkpoint`'s three call
    sites that can reach a deferral (fresh socratic, auto's "not this"
    escape, recognize's "it's different" escape) all produce the identical
    wording rather than three near-copies drifting apart."""
    return f"[deferred] {chosen_label} — maker reviewed the tradeoff and handed the call to the Forge"


def _seal_socratic_answer(
    cm: "checkpoint_memory.CheckpointMemory", decision: Decision, responder: Responder
) -> CheckpointOutcome:
    """Run a full Socratic pass and seal the result — the shared tail every
    path that falls through to full Socratic (a fresh decision-type, or
    either band's own "it's different" escape) ends on. `cm` must already
    be open; this never opens or closes it."""
    chosen_label, rationale, deferred = _full_socratic(decision, responder)
    canonical = _deferred_canonical(chosen_label) if deferred else f"{chosen_label}: {rationale}"
    cm.seal(decision.surface, canonical)
    return CheckpointOutcome(
        decision_type=decision.decision_type,
        chosen=chosen_label,
        rationale=rationale,
        band="socratic",
        deferred=deferred,
        sealed=True,
        memory_available=True,
    )


def run_checkpoint(
    decision: Decision,
    *,
    builder_id: str,
    responder: Responder,
    root: Path = checkpoint_memory.DEFAULT_CHECKPOINT_ROOT,
    recognize_threshold: float = DEFAULT_RECOGNIZE_THRESHOLD,
) -> CheckpointOutcome:
    """The D8 checkpoint, end to end: soft-Nestor gate, then route by band,
    present/confirm accordingly, seal what needs sealing. See module
    docstring for the three bands and where each one's "prior answer" comes
    from. Raises `CheckpointError` for this orchestrator's own refusals
    (an empty `Decision.options`, a malformed `ChoiceResult`) and lets
    `checkpoint_memory.CheckpointMemoryError`/`CheckpointConflict`/
    `CheckpointRejected` propagate unwrapped for everything memory-side —
    see module docstring's "Exception discipline" section. Never raises for
    "Nestor is absent"; that is precisely what the soft-Nestor gate below
    exists to turn into an honest `memory_available=False` outcome instead.
    """
    if not decision.options:
        raise CheckpointError(
            f"Decision {decision.decision_type!r} has no options — nothing to present"
        )

    # ── soft-Nestor gate (Part A) — checked FIRST, before anything else in
    # this module touches checkpoint_memory. False means: skip memory
    # entirely, full Socratic every time, and say so honestly in the
    # outcome rather than letting `open_checkpoint_memory` raise partway
    # through a flow the caller had no way to have avoided starting.
    if not checkpoint_memory.nestor_available():
        chosen_label, rationale, deferred = _full_socratic(decision, responder)
        return CheckpointOutcome(
            decision_type=decision.decision_type,
            chosen=chosen_label,
            rationale=rationale,
            band="socratic",
            deferred=deferred,
            sealed=False,
            memory_available=False,
        )

    with checkpoint_memory.open_checkpoint_memory(builder_id, decision.decision_type, root=root) as cm:
        result = cm.check(decision.surface)

        # ── auto band: a genuine Nestor tier-1 hit ──────────────────────
        if result["sealed"] is True:
            canonical = result["canonical"]
            prompt = (
                f"You've handled a {decision.decision_type!r} decision like this before "
                f"— you chose: {canonical}. Same call here?"
            )
            if responder.confirm(prompt):
                return CheckpointOutcome(
                    decision_type=decision.decision_type,
                    chosen=canonical,
                    rationale="",
                    band="auto",
                    deferred=False,
                    sealed=True,  # already sealed going in — no re-seal, still a true fact
                    memory_available=True,
                )
            # "Not this" -> the recognize-band "different" path, restated
            # for the auto band's own identifying handle: a real tier-1 hit
            # DOES carry a pair_id in its provenance (unlike the
            # sub-threshold case below), so reject_match uses that.
            pair_id = result.get("provenance", {}).get("pair_id", "")
            cm.reject_match(
                decision.surface,
                pair_id=pair_id,
                reason="maker said this was not the same call as the prior sealed answer",
            )
            return _seal_socratic_answer(cm, decision, responder)

        # ── recognize band: a real, sub-threshold hit ───────────────────
        # `canonical` is always None below Nestor's own seal threshold (see
        # module docstring) — the prior answer lives in
        # provenance["suggestion"] instead, EntityResolver's own recipe for
        # exactly this case. Not fabricated: read straight from what
        # Nestor's resolve() already computed, or absent entirely.
        prior_canonical = result.get("provenance", {}).get("suggestion")
        if prior_canonical is not None and result["confidence"] >= recognize_threshold:
            prompt = (
                f"This looks like the {decision.decision_type!r} decision you made before "
                f"— you chose: {prior_canonical}. Same call here?"
            )
            if responder.confirm(prompt):
                # Seal the NEW wording to the SAME answer — next time this
                # exact phrasing is an auto hit, per the design doc's own
                # "loose recognition" line.
                cm.seal(decision.surface, prior_canonical)
                return CheckpointOutcome(
                    decision_type=decision.decision_type,
                    chosen=prior_canonical,
                    rationale="",
                    band="recognize",
                    deferred=False,
                    sealed=True,
                    memory_available=True,
                )
            # "It's different" -> teach the memory not to conflate the two,
            # then fall through to full Socratic. No pair_id available at
            # this tier (see module docstring) — target_text is the real
            # identifying handle Nestor's own resolve() gave us.
            cm.reject_match(
                decision.surface,
                target_text=prior_canonical,
                reason="maker said this was not the same call as the recognized prior seal",
            )
            return _seal_socratic_answer(cm, decision, responder)

        # ── socratic band: low confidence, or nothing sealed yet at all ──
        return _seal_socratic_answer(cm, decision, responder)


# ── CLI (optional; a scripted demo, mirroring forge_build.py's shape) ──────

class _ScriptedResponder:
    """A tiny, fully-deterministic `Responder` for the CLI demo — prints
    every prompt it's asked and always picks the FIRST option with a fixed
    rationale, never defers. Not used by the test suite (which scripts its
    own responders per-scenario); this exists only so `python
    stores/checkpoint.py demo ...` has something to run without a real
    maker UI."""

    def confirm(self, prompt: str) -> bool:
        print(f"[confirm] {prompt}")
        print("[confirm] -> yes")
        return True

    def choose(self, decision: Decision) -> ChoiceResult:
        print(f"[choose] {decision.surface}")
        for opt in decision.options:
            print(f"  - {opt.label}: {opt.tradeoff}")
        chosen = decision.options[0]
        print(f"[choose] -> {chosen.label} (demo default: first option)")
        return ChoiceResult(chosen_label=chosen.label, rationale="demo run, first option picked")


def _sample_decision(decision_type: str) -> Decision:
    return Decision(
        decision_type=decision_type,
        surface=f"Sample {decision_type} decision for the demo CLI",
        options=(
            Option(label="option A", tradeoff="simpler, less flexible"),
            Option(label="option B", tradeoff="more flexible, more surface area"),
        ),
        recommended="option A",
    )


def _cmd_demo(args: argparse.Namespace) -> int:
    decision = _sample_decision(args.decision_type)
    outcome = run_checkpoint(
        decision,
        builder_id=args.builder_id,
        responder=_ScriptedResponder(),
        root=Path(args.root),
        recognize_threshold=args.recognize_threshold,
    )
    print(json.dumps(
        {
            "decision_type": outcome.decision_type,
            "chosen": outcome.chosen,
            "rationale": outcome.rationale,
            "band": outcome.band,
            "deferred": outcome.deferred,
            "sealed": outcome.sealed,
            "memory_available": outcome.memory_available,
        },
        indent=2,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint.py")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser(
        "demo",
        help="run the D8 checkpoint flow once against a scripted responder and a sample decision",
    )
    d.add_argument("builder_id")
    d.add_argument("decision_type")
    d.add_argument("--root", default=str(checkpoint_memory.DEFAULT_CHECKPOINT_ROOT))
    d.add_argument("--recognize-threshold", type=float, default=DEFAULT_RECOGNIZE_THRESHOLD)
    d.set_defaults(func=_cmd_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
