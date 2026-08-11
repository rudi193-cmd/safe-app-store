#!/usr/bin/env python3
"""stores/checkpoint_calibration.py — The Forge's calibration engine, bite 2
of the learning layer (docs/design/the-forge.md, "Verification-as-learning —
the willow-mcp reuse map", 2026-08-11; see also that section's "bite ladder").

Bite 1 (`stores/checkpoint.py`) is the interaction that SEALS a decision.
This module is what turns a pile of seals into *learning*, per the design
doc's own settlement: **calibration happens by resurfacing a seal later and
seeing whether the maker still holds it (`#12` lesson-regression), not by a
scorer at seal-time.** A maker *contradicting* their own prior seal on
resurface (`#3`) is the practical contradiction signal this bite implements —
not a new semantic-similarity matcher (see "Reuse discipline" below).

    resurface(surface) --check() against the SAME builder's memory-->
        prior sealed answer found (or CalibrationError: nothing to resurface)
        --present/confirm--> held (light, no re-seal)
                            | regressed (reject_match the prior, fresh
                              Socratic for the new answer, seal it)
        --> ResurfaceOutcome

**Reuse discipline (rule 11 — this bite is mostly wiring, not new build):**
  * **Contradiction (`#3`)** is NOT a new semantic matcher. Nestor's own
    `ConflictingSealError` (a different verifier already sealed a different
    answer for the same wording) already surfaces as
    `checkpoint_memory.CheckpointConflict` — see `contradictions()` below, a
    thin, unwrapped pass-through, not a detector this module invents. The
    fleet's real semantic-refutation pass is Jeles' `conflict_scan` ("search
    for what refutes, not what resembles") — a corpus-wide contradiction scan
    is explicitly OUT of scope here; reuse `conflict_scan` for that later,
    don't rebuild it. This bite's own contradiction signal is narrower and
    already-built: a **regressed resurface** (the maker saying "no" to their
    own prior seal), which is `reject_match` + a fresh seal — both bite-1/D12
    primitives, not new ones.
  * **Scheduling ("is it due for review") is now FOLDED IN**, in its own
    module `stores/checkpoint_schedule.py` (the reuse-map named the scheduler:
    py-fsrs, MIT — docs/design/the-forge-fsrs.md). `resurface` records a
    review there after every held/regressed outcome (held -> FSRS Good,
    regressed -> FSRS Again), keyed on the decision's Nestor `pair_id`, and
    reports the next `due` date on `ResurfaceOutcome.next_due`. Bite 2's old
    fixed-interval `is_due` placeholder is gone; `checkpoint_schedule.is_due`
    (card-driven) replaces it. FSRS is a SOFT dependency there — absent, it
    degrades to fixed intervals — so `resurface` gains no hard `fsrs` import.

**The `reject_match` vs `reject_pair` choice on a regression — verified
against the real Nestor library, not guessed.** A regression needs to do two
things in the same breath: (1) teach the memory this specific resurfaced
wording is no longer trustworthy as-is, and (2) immediately reseal that SAME
wording to the maker's new answer. Three ways to identify what's being
taught were tried against real Nestor before picking one:

  * `reject_match(surface, pair_id=<the resurfaced pair's id>)` — looks like
    bite 1's own auto-band "not this" escape, but is WRONG here: Nestor's
    `reject_match` records the rejection keyed on `(query_norm, pair_id)`.
    `cm.seal(surface, new_canonical)` right after does a same-verifier
    self-correction *in place* — SAME `pair_id`, only `target_text` changes
    (see `nestor.memory.add_pair`'s "self-correction" branch). The old
    rejection is still keyed to that same `pair_id`, so `best_sealed` keeps
    filtering that row out for this exact query FOREVER, even after it holds
    the correct new answer — the resurfaced surface can never show `sealed`
    again. Confirmed empirically, not assumed.
  * `reject_pair(pair_id)` — retires the pair itself, `status="rejected"`,
    everywhere. The immediate reseal right after then hits
    `nestor.memory.add_pair`'s `RejectedPairError` guard (`existing["status"]
    == "rejected"` blocks an implicit re-seal) unless `override_rejection`
    is passed — which would also be too broad: `reject_pair` says "the
    mapping itself is wrong, for every query, forever," which discards any
    OTHER differently-worded seal (bite 1's recognize band deliberately
    seals a reworded surface as its own new pair with the SAME canonical
    text) that resolves to the same pair the maker was never actually asked
    about.
  * `reject_match(surface, target_text=<the prior canonical STRING>)` — the
    one this module uses. Nestor's rejection is keyed on `(query_norm,
    target_text)` here instead of `pair_id`, so once the in-place reseal
    changes the row's `target_text` to the NEW answer, the OLD rejection no
    longer matches anything the row now holds — the resurfaced surface
    resolves `sealed=True` again immediately, with the new answer, exactly
    the outcome a regression needs. This is also literally bite 1's own
    recognize-band choice (its own module docstring: no `pair_id` exists at
    sub-threshold, so `target_text` is the identifying handle) — restated
    here for a different, empirically-verified reason specific to the
    reseal-in-place case, not copied blind.

**Soft-Nestor on resurface.** `resurface` RAISES `CalibrationError` when
`checkpoint_memory.nestor_available()` is False, rather than returning some
`ResurfaceOutcome` marked "unavailable." `ResurfaceOutcome` has no
`memory_available` field the way bite 1's `CheckpointOutcome` does — there is
no honest way to fill `held`/`regressed`/`prior`/`new` when there is no
memory to resurface against, and a caller reading `held=True` back with
memory actually absent would look exactly like a real held-seal confirmation
that never happened. Raising is also consistent with the OTHER "nothing to
resurface" case below (no prior seal) — both are the same shape of refusal:
this call has no seal to resurface against, for two different reasons.

**"Nothing to resurface" is `has_sealed()` AND an exact `sealed=True`
`check(surface)` hit — not a sub-threshold suggestion.** `checkpoint.py`'s
own module docstring is explicit that Nestor's `canonical` is populated ONLY
for a genuine sealed serve, "precisely so nothing downstream can mistake an
unsealed candidate for a committed answer by accident." Resurfacing is
`"You decided X ... does that still hold?"` — X has to be something the
maker actually sealed, not a fuzzy candidate this module would otherwise be
putting words in their mouth over. `has_sealed()` is checked first (a cheap
decision-type-wide "has this builder ever sealed ANYTHING here" refusal,
matching bite 1's own use of it) before the surface-specific `check()`.

**Loaded modules, and why only one copy of each.** This module loads its own
copy of `stores/checkpoint.py` (for `Decision`/`Option`/`ChoiceResult`/
`Responder`/`CheckpointError`/`_full_socratic`/`_deferred_canonical`) the
same `spec_from_file_location` way `checkpoint.py` itself loads
`checkpoint_memory.py`. It does NOT separately load `checkpoint_memory.py`
a second time — `checkpoint.py` already loaded its own copy
(`checkpoint.checkpoint_memory`), and this module reuses THAT one via
`checkpoint_memory = checkpoint.checkpoint_memory` below, the exact "reuse
the sibling's loaded copy rather than loading it again" precedent
`checkpoint.py`'s own docstring names for `forge_build.py`/`seam.py`. This
also keeps Nestor's soft-dependency `_nestor_cache` singular per load chain,
which the soft-Nestor test below depends on for a genuinely fresh probe.

Store-side authority (D1), same trust level as `checkpoint.py`/
`checkpoint_memory.py`/`principal.py`/`session.py`: `apps/the-forge/` never
imports this module, for the same reason it never imports either of those.

Not in scope, deliberately: a real scheduler (see "Scheduling" above), a
corpus-wide semantic contradiction scan (see "Reuse discipline" above), and
bite 3's engagement/friction gate (`#66`/`#67`) — this module has no opinion
on whether a maker engaged honestly with a resurfaced decision, only on
whether they said it still holds.

Usage (dev CLI, mirroring `checkpoint.py`'s own `demo` shape):
    python stores/checkpoint_calibration.py resurface <builder_id> \\
        <decision_type> --surface "..." [--root DIR] [--regress]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("checkpoint", _REPO / "stores" / "checkpoint.py")
checkpoint = importlib.util.module_from_spec(_spec)
sys.modules["checkpoint"] = checkpoint
_spec.loader.exec_module(checkpoint)

# Reuse checkpoint.py's OWN already-loaded checkpoint_memory copy — see
# module docstring's "Loaded modules" section for why this is not a second,
# independently-cached load.
checkpoint_memory = checkpoint.checkpoint_memory

# The FSRS scheduler (bite 2's deferred "is it due" half, now folded in —
# docs/design/the-forge-fsrs.md). Loaded the same spec way; its own Nestor
# dependency is nil (it only borrows checkpoint_memory's _check_builder_id and
# root), so we repoint its checkpoint_memory at OUR already-loaded copy rather
# than let it keep the second one its own module-level load created — one
# checkpoint_memory object across this whole load chain, same "reuse the
# sibling's loaded copy" discipline this module already applies to
# checkpoint_memory itself.
_sched_spec = importlib.util.spec_from_file_location(
    "checkpoint_schedule", _REPO / "stores" / "checkpoint_schedule.py"
)
checkpoint_schedule = importlib.util.module_from_spec(_sched_spec)
sys.modules["checkpoint_schedule"] = checkpoint_schedule
_sched_spec.loader.exec_module(checkpoint_schedule)
checkpoint_schedule.checkpoint_memory = checkpoint_memory


class CalibrationError(Exception):
    """Refused by THIS module's own bite-2 orchestration — never a re-wrap
    of `checkpoint_memory.CheckpointMemoryError` (or its `CheckpointConflict`/
    `CheckpointRejected` subclasses), which propagate unwrapped exactly as
    `checkpoint.py`'s own `CheckpointError` docstring commits to for bite 1.
    Raised for: nothing sealed to resurface (this decision-type has no seals
    at all, or this exact surface was never itself sealed), and Nestor being
    unavailable outright (resurface has no memory to resurface against —
    see module docstring's "Soft-Nestor on resurface" section)."""


# ── the outcome ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResurfaceOutcome:
    """What `resurface` returns.

    `prior`: the sealed canonical text that was resurfaced (always the FULL
    canonical string `checkpoint_memory.check()` returned as `canonical` —
    same "don't guess at a split a lower layer didn't hand over" posture
    `checkpoint.py`'s own `CheckpointOutcome` docstring states for its own
    `chosen`/`rationale` split).
    `new`: the maker's answer THIS time — `""` when `held` (nothing new was
    asked), else the freshly-sealed canonical text (same full-string shape
    as `prior`, so a caller can compare the two directly).
    `resealed`: True iff this run left a NEW canonical durably sealed for
    `surface` — False for `held` (nothing needed re-recording; the light
    confirm is not a re-seal, same reasoning as bite 1's auto band).
    `next_due`: ISO-8601 timestamp for when this decision is next due for
    review, from the FSRS schedule advanced this run (held -> Good graduates
    it, regressed -> Again resets it). Always set — every resurface records a
    review. See `stores/checkpoint_schedule.py`.
    """

    decision_type: str
    held: bool
    regressed: bool
    prior: str
    new: str
    resealed: bool
    next_due: str = ""


# ── the flow ─────────────────────────────────────────────────────────────────

def resurface(
    *,
    builder_id: str,
    decision_type: str,
    surface: str,
    responder: "checkpoint.Responder",
    root: Path = checkpoint_memory.DEFAULT_CHECKPOINT_ROOT,
    now: "datetime | None" = None,
) -> ResurfaceOutcome:
    """Resurface ONE previously-sealed decision and find out whether the
    maker still holds it. Raises `CalibrationError` for either shape of
    "nothing to resurface" (see module docstring), and lets
    `checkpoint_memory.CheckpointMemoryError`/`CheckpointConflict`/
    `CheckpointRejected` propagate unwrapped for everything memory-side —
    same exception discipline `checkpoint.py`'s `run_checkpoint` uses.

    `now` is the review timestamp fed to the FSRS schedule; injected here at
    the boundary (D-FSRS-3: the schedule module itself never reads the wall
    clock). Defaults to `datetime.now(timezone.utc)` when a caller — like the
    CLI — declines to supply one; the tests always inject it for determinism.
    """
    now = now or datetime.now(timezone.utc)
    # ── soft-Nestor gate — checked first, same posture as
    # checkpoint.run_checkpoint's own gate, but resurface has no honest
    # degraded outcome to hand back (see module docstring), so it refuses
    # outright instead of returning one.
    if not checkpoint_memory.nestor_available():
        raise CalibrationError(
            "Nestor is unavailable — resurface has no memory to resurface "
            "against (checkpoint_memory.nestor_available() is False). This "
            "is a refusal, not a degraded outcome: there is no honest way "
            "to fill held/regressed/prior/new when there is nothing sealed "
            "to even check against."
        )

    with checkpoint_memory.open_checkpoint_memory(builder_id, decision_type, root=root) as cm:
        if not cm.has_sealed():
            raise CalibrationError(
                f"nothing sealed to resurface for decision_type={decision_type!r} "
                f"— builder_id={builder_id!r} has not sealed anything under this "
                f"decision-type yet"
            )
        result = cm.check(surface)
        if not result["sealed"] or not result.get("canonical"):
            raise CalibrationError(
                f"nothing sealed to resurface for decision_type={decision_type!r} "
                f"surface={surface!r} — this exact wording has no sealed answer "
                f"(a sub-threshold suggestion is not a seal; see module "
                f"docstring's 'Nothing to resurface' section)"
            )
        prior = result["canonical"]
        # The decision's stable identity in Nestor — the FSRS card key (see
        # module docstring / docs/design/the-forge-fsrs.md D-FSRS-1). Stable
        # across a held->regressed->held cycle because a same-verifier reseal
        # is in-place (same pair_id), so one card follows the decision.
        pair_id = result.get("provenance", {}).get("pair_id")

        prompt = f"You decided {prior!r} for {decision_type!r}. Does that still hold?"
        if responder.confirm(prompt):
            next_due = _record_review(builder_id, pair_id, checkpoint_schedule.OUTCOME_HELD, now, root)
            return ResurfaceOutcome(
                decision_type=decision_type,
                held=True,
                regressed=False,
                prior=prior,
                new="",
                resealed=False,
                next_due=next_due,
            )

        # ── regressed: the practical #3 contradiction signal ────────────
        # target_text, not pair_id, and reject_match not reject_pair — see
        # module docstring's own dedicated section, verified against real
        # Nestor.
        cm.reject_match(
            surface,
            target_text=prior,
            reason="maker resurfaced this decision and no longer holds the prior seal",
        )

        # A fresh full-Socratic pass for the new answer, reusing bite 1's
        # own machinery rather than re-implementing "ask, defer-or-not,
        # validate" here. `resurface` is not handed a real options set (no
        # D7 routing exists yet to offer one at resurface time either — the
        # same "explicit stub" posture bite 1's own Decision already takes),
        # so this builds the smallest placeholder Decision that satisfies
        # `Responder.choose`'s contract; only `chosen_label`/`rationale`
        # from the maker's actual answer are used in the common case —
        # `decision.options`/`recommended` matter only for the "I don't
        # know, you choose" deferral fallback (see `_full_socratic`).
        fresh_decision = checkpoint.Decision(
            decision_type=decision_type,
            surface=surface,
            options=(
                checkpoint.Option(
                    label="revised answer",
                    tradeoff="whatever the maker now believes for this decision",
                ),
            ),
        )
        chosen_label, rationale, deferred = checkpoint._full_socratic(fresh_decision, responder)
        new_canonical = (
            checkpoint._deferred_canonical(chosen_label)
            if deferred
            else f"{chosen_label}: {rationale}"
        )
        cm.seal(surface, new_canonical)

        # Same pair_id (the reseal was in-place); grade the SAME card Again.
        next_due = _record_review(builder_id, pair_id, checkpoint_schedule.OUTCOME_REGRESSED, now, root)
        return ResurfaceOutcome(
            decision_type=decision_type,
            held=False,
            regressed=True,
            prior=prior,
            new=new_canonical,
            resealed=True,
            next_due=next_due,
        )


def _record_review(builder_id, pair_id, outcome, now, root) -> str:
    """Advance and persist the FSRS schedule for this decision, returning the
    next-due ISO timestamp. No-ops to "" if Nestor handed back no `pair_id`
    (there is nothing stable to key the card on) — the resurface still stands;
    only the schedule half is skipped, and that is honestly reported as an
    empty `next_due` rather than a guessed key."""
    if not pair_id:
        return ""
    prior_card = checkpoint_schedule.load_card(builder_id, pair_id, root=root)
    new_card = checkpoint_schedule.record_review(prior_card, outcome, now)
    checkpoint_schedule.save_card(builder_id, pair_id, new_card, root=root)
    return new_card["due"]


def contradictions(
    cm: "checkpoint_memory.CheckpointMemory",
    decision_description: str,
    chosen_option_and_rationale: str,
    **seal_kwargs,
) -> dict:
    """Thin, unwrapped pass-through to `CheckpointMemory.seal` — named
    separately only so a bite-2 caller has one obvious place to look for
    "where does contradiction detection live," per module docstring's reuse
    discipline. This adds NO new matching or detection: `seal` already
    raises `checkpoint_memory.CheckpointConflict` (wrapping Nestor's own
    `ConflictingSealError`) when a different verifier asserts a different
    answer for the same wording, and this function does nothing but call it
    and let that propagate. `cm` must already be open."""
    return cm.seal(decision_description, chosen_option_and_rationale, **seal_kwargs)


# `is_due` used to live here as a fixed-interval placeholder; bite 2's FSRS
# fold-in moved it (card-driven) to `stores/checkpoint_schedule.py`. Reach for
# `checkpoint_schedule.is_due(card, now)` — a caller with a resurfaced
# decision's `pair_id` loads its card via `checkpoint_schedule.load_card` and
# asks from there.


# ── CLI (optional; a scripted demo, mirroring checkpoint.py's own shape) ────

class _ScriptedResumeResponder:
    """A tiny, fully-deterministic `Responder` for the CLI demo. Confirms
    "still holds" unless `--regress` is passed, in which case it answers
    "no" once and then picks the first option with a fixed rationale for the
    fresh Socratic pass — mirrors `checkpoint.py`'s own `_ScriptedResponder`.
    Not used by the test suite (which scripts its own responders)."""

    def __init__(self, regress: bool):
        self._regress = regress

    def confirm(self, prompt: str) -> bool:
        print(f"[confirm] {prompt}")
        answer = not self._regress
        print(f"[confirm] -> {'yes' if answer else 'no'}")
        return answer

    def choose(self, decision: "checkpoint.Decision") -> "checkpoint.ChoiceResult":
        print(f"[choose] {decision.surface}")
        for opt in decision.options:
            print(f"  - {opt.label}: {opt.tradeoff}")
        chosen = decision.options[0]
        print(f"[choose] -> {chosen.label} (demo default: first option)")
        return checkpoint.ChoiceResult(chosen_label=chosen.label, rationale="demo run, regressed")


def _cmd_resurface(args: argparse.Namespace) -> int:
    try:
        outcome = resurface(
            builder_id=args.builder_id,
            decision_type=args.decision_type,
            surface=args.surface,
            responder=_ScriptedResumeResponder(regress=args.regress),
            root=Path(args.root),
        )
    except CalibrationError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps(
        {
            "decision_type": outcome.decision_type,
            "held": outcome.held,
            "regressed": outcome.regressed,
            "prior": outcome.prior,
            "new": outcome.new,
            "resealed": outcome.resealed,
            "next_due": outcome.next_due,
        },
        indent=2,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint_calibration.py")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser(
        "resurface",
        help="resurface a previously-sealed decision against a scripted responder",
    )
    r.add_argument("builder_id")
    r.add_argument("decision_type")
    r.add_argument("--surface", required=True)
    r.add_argument("--root", default=str(checkpoint_memory.DEFAULT_CHECKPOINT_ROOT))
    r.add_argument("--regress", action="store_true", help="script the maker as no longer holding the prior seal")
    r.set_defaults(func=_cmd_resurface)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
