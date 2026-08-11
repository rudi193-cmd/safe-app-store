#!/usr/bin/env python3
"""stores/checkpoint_nudge.py — The Forge's mid-session nudge (#67), the last
willow-mcp reuse for the learning loop (docs/design/the-forge.md).

Bite 3 wired `friction_score` (`#66`, the per-turn sycophancy score) into the
seal-time engagement gate. `friction_floor.py`'s OTHER half — `FrictionFloor`,
the windowed detector that flags an episode of low friction under escalation —
is `#67`, and it shipped in willow-mcp UNwired: the reuse-map's note was
"primitive exists, injection timing doesn't." This module is that injection
timing: WHEN to scan and HOW to surface a nudge mid-session without re-alarming
on every re-scan. Two monitors, both a pure SIGNAL that never blocks (the
friction primitive's own ethos), both deterministic and model-free, both run
store-side OUTSIDE the session they watch (D1 — a mirror cannot audit itself):

  * `SessionMirrorMonitor` — the literal `#67` "mirror" nudge. Wraps the
    vendored `FrictionFloor.scan` DIRECTLY (no reimplementation) over the
    build session's maker<->Forge transcript: it flags when the Forge's side
    stops being *other* (no pushback, no outside grounding, mostly echo) WHILE
    the maker is escalating (grandiosity/certainty). The one new thing over
    raw `FrictionFloor` is mid-session use: accumulate turns, re-scan as they
    arrive, and surface each episode's flag exactly ONCE (de-duped by the
    tripping turn index, which is stable under an append-only transcript).
    Note: the Forge's own model side (D7) is still stubbed, so a *live*
    session has few real agent turns to watch yet — same "the machinery is
    real, its D7 input is stubbed" posture bites 0-1 took. The monitor is
    built and tested now; it watches real dialogue the moment D7 lands.

  * `EngagementRunMonitor` — the checkpoint-level companion. It watches the
    stream of per-checkpoint engagement scores bite 3 already produces and
    nudges on a *run* of rubber-stamps ("you've waved through the last few
    decisions"). It MIRRORS `FrictionFloor`'s window / one-flag-per-episode /
    re-arm-on-recovery shape, but over a scalar stream rather than a
    transcript, because the vendored `FrictionFloor.scan` is welded to its own
    two inputs — a role-tagged transcript and an *escalating user* it gates
    on — and a maker rubber-stamping their own design decisions has neither a
    second speaker nor an escalation axis (the rubber-stamping IS the concern,
    with nothing to gate it on). Reusing `scan` here would mean fabricating a
    fake transcript and a fake escalation just to reach its loop; a small
    honest windowed detector over the real scalars is the faithful move. It
    reuses `checkpoint_engagement.RUBBER_STAMP_FLOOR` as its floor, so "a run
    of rubber-stamps" uses the same line a single rubber-stamp does.

Store-side authority (D1), same trust level as the rest of the learning layer:
`apps/the-forge/` never imports this module. The session being watched is an
input to the store, not a peer of it.

Not in scope: persisting nudges to a store (willow-mcp's `FrictionWatcher`
does this to a SOIL collection; a caller here that wants durability can hand
each `Nudge` to whatever store it likes — this module keeps the detector
dependency-free), and `#69`'s devil's-advocate-on-zero-friction (a different
idea in the pile).

Usage (dev CLI):
    python stores/checkpoint_nudge.py mirror --transcript turns.json
    python stores/checkpoint_nudge.py engagement-run --scores 0.1 0.2 0.05
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# The vendored scorer/detector (#66 friction_score + #67 FrictionFloor) and the
# engagement gate (for the shared rubber-stamp floor). Both pure/model-free, so
# this module stays pure too — loaded spec-style like every store-side sibling.
_ff_spec = importlib.util.spec_from_file_location(
    "friction_floor", _REPO / "stores" / "friction_floor.py"
)
friction_floor = importlib.util.module_from_spec(_ff_spec)
sys.modules["friction_floor"] = friction_floor
_ff_spec.loader.exec_module(friction_floor)

_eng_spec = importlib.util.spec_from_file_location(
    "checkpoint_engagement", _REPO / "stores" / "checkpoint_engagement.py"
)
checkpoint_engagement = importlib.util.module_from_spec(_eng_spec)
sys.modules["checkpoint_engagement"] = checkpoint_engagement
_eng_spec.loader.exec_module(checkpoint_engagement)


@dataclass(frozen=True)
class Nudge:
    """A mid-session nudge — human-facing, advisory, never a block.

    `kind`: `"mirror"` (the Forge stopped pushing back while the maker
    escalated) or `"engagement-run"` (a run of rubber-stamped decisions).
    `message`: the text to show a human (for `mirror`, the vendored `Flag`'s
    own message verbatim).
    `at`: where it tripped — the transcript turn index (`mirror`) or the
    checkpoint index in the session (`engagement-run`).
    `detail`: kind-specific metadata a caller can log without re-deriving.
    """

    kind: str
    message: str
    at: int
    detail: dict = field(default_factory=dict)


# ── the literal #67: the mirror detector, wired for mid-session ──────────────

class SessionMirrorMonitor:
    """Mid-session wrapper around the vendored `FrictionFloor`. Accumulate the
    maker<->Forge transcript with `add_turn`, then `check()` returns any NEW
    nudge since the last check — each episode's flag surfaced exactly once.

    The dedup key is the flag's `at_turn` (the tripping agent turn's transcript
    index). That is stable precisely because the transcript is append-only:
    earlier indices never shift as turns arrive, so an episode that tripped at
    turn 7 stays "flag #7" on every subsequent re-scan and is suppressed after
    the first surface. `FrictionFloor` itself already emits one flag per episode
    within a single scan and re-arms when friction recovers; this only adds the
    ACROSS-scan dedup a growing transcript needs."""

    def __init__(self, window: int = 4, floor: float = 0.35, escalation_trigger: float = 0.5):
        self._ff = friction_floor.FrictionFloor(
            window=window, floor=floor, escalation_trigger=escalation_trigger
        )
        self._turns: list = []
        self._surfaced: set[int] = set()

    def add_turn(self, role: str, text: str, ts: float | None = None) -> "SessionMirrorMonitor":
        """Append one session turn. `role` is `"user"` (the maker) or
        `"agent"` (the Forge's side); anything else `FrictionFloor` ignores.
        Returns self so calls chain."""
        self._turns.append(friction_floor.Turn(role=role, text=text, ts=ts))
        return self

    def check(self) -> list[Nudge]:
        """Re-scan the accumulated transcript; return only nudges not surfaced
        before. Empty list when nothing new tripped — the common, quiet case."""
        out: list[Nudge] = []
        for flag in self._ff.scan(self._turns):
            if flag.at_turn in self._surfaced:
                continue
            self._surfaced.add(flag.at_turn)
            out.append(Nudge(
                kind="mirror",
                message=flag.message,
                at=flag.at_turn,
                detail={
                    "streak": flag.streak,
                    "mean_friction": flag.mean_friction,
                    "escalation": flag.escalation,
                    "low_turns": list(flag.low_turns),
                },
            ))
        return out


# ── the checkpoint-level companion: a run of rubber-stamps ───────────────────

class EngagementRunMonitor:
    """Watches the per-checkpoint engagement stream and nudges on a run of
    rubber-stamps. `observe(engagement)` once per checkpoint, in order;
    returns a `Nudge` when the last `window` MEASURED readings average below
    the floor (and no nudge is already standing for this episode), else None.

    Mirrors `FrictionFloor`'s own shape — a `window`-wide mean, one nudge per
    episode, re-armed once the mean climbs back to/above the floor — but over
    scalars, for the reasons in the module docstring. `engagement is None`
    (an auto/recognize confirm or a deferral — no rationale to score) is
    SKIPPED: it is not a rubber-stamp, so it neither fills the window nor
    breaks a run; only genuinely-measured rationales move this detector.

    `floor` defaults to `checkpoint_engagement.RUBBER_STAMP_FLOOR`, so a *run*
    of rubber-stamps is judged by the same line a single one is (bite 3)."""

    def __init__(self, window: int = 3, floor: float | None = None):
        if window < 2:
            raise ValueError("window must be >= 2 — a 'run' needs at least two")
        self.window = window
        self.floor = checkpoint_engagement.RUBBER_STAMP_FLOOR if floor is None else floor
        self._measured: list[float] = []
        self._alarmed = False
        self._index = -1  # checkpoint index of the most recent observe()

    def observe(self, engagement: float | None) -> Nudge | None:
        """Record one checkpoint's engagement reading; maybe nudge. See class
        docstring for the None-skip and re-arm semantics."""
        self._index += 1
        if engagement is None:
            return None  # no rationale to score — not a rubber-stamp, skip
        self._measured.append(engagement)
        if len(self._measured) < self.window:
            return None
        mean = sum(self._measured[-self.window:]) / self.window
        if mean < self.floor:
            if self._alarmed:
                return None  # one nudge per episode
            self._alarmed = True
            return Nudge(
                kind="engagement-run",
                message=(
                    f"The last {self.window} decisions averaged engagement {mean:.2f} "
                    f"(floor {self.floor}). That is a run of thin, wave-it-through "
                    f"rationales — worth slowing down: are you deciding these, or "
                    f"rubber-stamping them?"
                ),
                at=self._index,
                detail={"mean_engagement": round(mean, 3), "window": self.window, "floor": self.floor},
            )
        # mean back at/above the floor — episode over, re-arm for the next run
        self._alarmed = False
        return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_mirror(args: argparse.Namespace) -> int:
    try:
        turns = json.loads(Path(args.transcript).read_text())
    except (OSError, ValueError) as e:
        print(f"could not read transcript {args.transcript!r}: {e}", file=sys.stderr)
        return 1
    m = SessionMirrorMonitor()
    for t in turns:
        m.add_turn(t.get("role"), t.get("text", ""), t.get("ts"))
    nudges = m.check()
    print(json.dumps([{"kind": n.kind, "at": n.at, "message": n.message, "detail": n.detail} for n in nudges], indent=2))
    return 0


def _cmd_engagement_run(args: argparse.Namespace) -> int:
    m = EngagementRunMonitor(window=args.window)
    fired = []
    for raw in args.scores:
        score = None if raw.lower() in ("none", "-") else float(raw)
        n = m.observe(score)
        if n is not None:
            fired.append({"kind": n.kind, "at": n.at, "message": n.message, "detail": n.detail})
    print(json.dumps(fired, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint_nudge.py")
    sub = p.add_subparsers(dest="command", required=True)

    mir = sub.add_parser("mirror", help="scan a maker<->Forge transcript for the #67 mirror nudge")
    mir.add_argument("--transcript", required=True, help="JSON: [{role, text, ts?}, ...]")
    mir.set_defaults(func=_cmd_mirror)

    run = sub.add_parser("engagement-run", help="feed a sequence of engagement scores; nudge on a run of rubber-stamps")
    run.add_argument("scores", nargs="+", help="engagement scores in [0,1], or 'none' for an unmeasured checkpoint")
    run.add_argument("--window", type=int, default=3)
    run.set_defaults(func=_cmd_engagement_run)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
