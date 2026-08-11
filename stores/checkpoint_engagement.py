#!/usr/bin/env python3
"""stores/checkpoint_engagement.py — The Forge's engagement gate, bite 3 of
the learning layer (docs/design/the-forge.md, "Verification-as-learning").

D8's checkpoint (bite 1) makes a maker *decide* instead of letting the model
decide for them; D9's whole thesis is that the deciding has to be REAL, not a
rubber-stamp. This module is the non-circular "did they actually decide, or
just wave it through" signal AT SEAL-TIME — `#66` in willow-mcp's idea pile,
already shipped there as the sycophancy scorer this module REUSES rather than
rebuilds (rule 11).

**What it reuses, and why it is a reuse not a rebuild.** The scorer is
`stores/friction_floor.py`, vendored byte-for-byte from willow-mcp (itself a
vendor of willow-gate, all three Apache-2.0 — see that file's header). Its
`friction_score(text, context)` measures how much a turn is *other* — pushes
back, grounds itself against something outside the prompt, adds unechoed
content, asks — on [0,1]. willow-mcp points it at an AGENT's turns to catch
the agent mirroring a user. The Forge points the SAME scorer at the MAKER's
own rationale for a checkpoint decision: a rationale that just echoes the
prompt, or says "yes, sounds good," scores near 0 (a rubber-stamp); a
rationale that gives grounded reasons scores high (a real decision). Nothing
here re-derives that measure — it wraps it and names it for the checkpoint.

**Four honest properties, carried verbatim from the primitive's own design —
do not overclaim:**
  * **A SIGNAL, not a verdict. It never blocks.** `run_checkpoint` seals the
    maker's answer whether the rationale is thin or rich; this only annotates
    the outcome (`engagement`, `rubber_stamp`) so a human — and the FSRS
    scheduler (below) — can see it. A gate that blocked a seal on a
    low score would be exactly the frictionless-in-reverse coercion the
    friction primitive refuses to become.
  * **Deterministic and MODEL-FREE.** No LLM, no egress, pure stdlib (via the
    vendored scorer). Safe to run store-side on the trust boundary: it cannot
    leak, and a sandboxed build cannot game a scorer that never runs inside it.
  * **It runs OUTSIDE the party it watches.** willow-mcp's constraint is "a
    mirror cannot audit itself." Here the watched party is the MAKER's
    rationale and the watcher is the STORE — genuinely outside the maker, and
    outside the sandboxed build entirely (D1). This is not the maker scanning
    themselves; it is the store scoring an input.
  * **It fails LOUD, not open.** An empty or unrecognized rationale scores
    toward 0 (flagged), never toward "fine." A conservative scorer that reads
    a genuine one-line reason as thin is the intended bias — see the primitive
    for the lexicon-tuning caveat; the answer is to tune the lexicon, not to
    make silence pass.

**How this feeds the rest of the loop.** `checkpoint_schedule.grade(outcome,
engagement=...)` (bite 2's FSRS fold-in) already accepts an engagement lever:
a held decision the maker barely engaged with grades `Hard` (resurface
sooner), a re-argued one grades `Easy` (push it out). `RUBBER_STAMP_FLOOR`
below is the SAME line grade() uses for its Hard cutoff (0.34), so
"rubber_stamp" and "would grade Hard" can never disagree. Bite 3 makes the
PRODUCER of that engagement signal exist; wiring it onto a *resurface-held*
review (asking "it still holds — why?") is the next increment, called out in
the design doc, not folded in here.

Store-side authority (D1), same trust level as the rest of the learning layer:
`apps/the-forge/` never imports this module. The maker being scored is an
input to the store, not a peer of it.

Not in scope: `#67`'s mid-session mirror NUDGE (re-prompting the maker when a
rationale is thin). The reuse-map flagged `#67` as partial in willow-mcp — the
`FrictionFloor` transcript scanner exists (also in the vendored file) but the
injection timing does not. A single non-blocking nudge is a natural next
increment on top of this signal; this bite ships the signal, honestly, and
stops there rather than half-shipping the timing.

Usage (dev CLI):
    python stores/checkpoint_engagement.py score --rationale "..." --surface "..."
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# The vendored, pure-stdlib scorer — loaded spec-style like every other
# store-side sibling loads its dependency, and for the same reason (stores/ is
# a directory of standalone scripts, not an installed package).
_ff_spec = importlib.util.spec_from_file_location(
    "friction_floor", _REPO / "stores" / "friction_floor.py"
)
friction_floor = importlib.util.module_from_spec(_ff_spec)
sys.modules["friction_floor"] = friction_floor
_ff_spec.loader.exec_module(friction_floor)

# The same line checkpoint_schedule.grade() uses for its Hard cutoff — see
# module docstring. Below this, a held decision's rationale is thin enough that
# the FSRS grade drops from Good to Hard (resurface sooner). One threshold,
# referenced from both places, so the "rubber_stamp" flag and the grade band
# are provably the same decision.
RUBBER_STAMP_FLOOR = 0.34


class EngagementError(Exception):
    """This module's own refusal — a `rationale`/`context` that is not text to
    score. Never a re-wrap of anything the vendored scorer raises (it doesn't;
    it's total over strings)."""


def engagement_score(rationale: str, context: str) -> float:
    """[0,1]. How substantively the MAKER's `rationale` engages the decision
    `context` (the surface/prompt they were answering) — a thin reuse of the
    vendored `friction_score`. Higher = a real decision (grounded, adds
    reasons, diverges from the prompt); near 0 = a rubber-stamp (echo, or
    silence). Deterministic and model-free.

    Refuses non-string input with `EngagementError` rather than letting the
    scorer coerce or crash on it — a caller handing a non-string rationale is
    a bug worth naming, not a 0.0 to be silently absorbed."""
    if not isinstance(rationale, str) or not isinstance(context, str):
        raise EngagementError(
            "engagement_score needs (rationale: str, context: str); got "
            f"({type(rationale).__name__}, {type(context).__name__})"
        )
    return friction_floor.friction_score(rationale, context)


def is_rubber_stamp(rationale: str, context: str, *, floor: float = RUBBER_STAMP_FLOOR) -> bool:
    """True iff the rationale scores below `floor` — a rubber-stamp. A SIGNAL,
    not a gate: nothing in this module or `run_checkpoint` blocks on a True.
    Default `floor` is `RUBBER_STAMP_FLOOR` (aligned to grade()'s Hard cutoff);
    a caller can raise/lower it for a stricter or looser read."""
    return engagement_score(rationale, context) < floor


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_score(args: argparse.Namespace) -> int:
    try:
        score = engagement_score(args.rationale, args.surface)
    except EngagementError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps(
        {
            "engagement": round(score, 3),
            "rubber_stamp": score < args.floor,
            "floor": args.floor,
        },
        indent=2,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint_engagement.py")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("score", help="score a maker's rationale against the decision surface")
    s.add_argument("--rationale", required=True)
    s.add_argument("--surface", required=True)
    s.add_argument("--floor", type=float, default=RUBBER_STAMP_FLOOR)
    s.set_defaults(func=_cmd_score)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
