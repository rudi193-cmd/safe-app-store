#!/usr/bin/env python3
"""stores/checkpoint_schedule.py — The Forge's review scheduler, the FSRS
fold-in that finishes bite 2's deferred "is it due for review" half
(docs/design/the-forge-fsrs.md, 2026-08-11).

Bite 2 (`stores/checkpoint_calibration.py`) shipped `is_due` as a fixed-
interval, stdlib-only PLACEHOLDER, explicitly waiting for the Apache-compat
reuse-map to name a real scheduler. It named **py-fsrs** (PyPI `fsrs`, MIT,
sole transitive dep `typing-extensions`) — the same spaced-repetition library
D9 recorded at the very start. This module is that scheduler, and nothing
else: it does NOT resurface a decision, ask the maker anything, or decide
what a decision is — `checkpoint_calibration.resurface` calls into here after
it already has a held/regressed outcome in hand.

Store-side authority (D1), same trust level as `checkpoint_calibration.py` /
`checkpoint_memory.py`: a builder's review schedule is calibration state a
sandboxed `apps/` build has no business reading or writing about itself.
`apps/the-forge/` never imports this module.

**Where a card lives (D-FSRS-1): a Forge-owned sidecar, keyed by the Nestor
`pair_id`, NOT inside the signed Nestor seal.** A Nestor seal is a signed,
human-witnessed commitment; an FSRS card is mutable scheduling bookkeeping
that changes on every review. Writing mutable state into a signed envelope
would break the signature on each review, so it never belonged there. The
schedule is the Forge's own lane (D6), so it lives in this module's own
per-builder file — `<root>/<builder_id>.schedule.json`, one JSON object
mapping `pair_id -> card blob`, under the SAME checkpoint root
`checkpoint_memory` uses, but never touching Nestor's store. Keying on
`pair_id` (the decision's stable identity in Nestor, verified stable across a
held→regressed→held cycle — see the design doc's build-time refinement note)
means one card follows a decision through every review, so a regression
grading that same card `Again` (below) falls out for free and the
surface-rewording question never has to be answered.

**The grade map (D-FSRS-2): held -> Good, regressed -> Again.** `resurface`
produces exactly two outcomes today; they map to the two FSRS ratings that
mean the same thing (Good graduates the interval, Again is a lapse/reset —
exactly what a changed mind is). `Hard`/`Easy` (how *confidently* a memory was
recalled) are deliberately RESERVED for bite 3's engagement/friction signal
(`#66`/`#67`) — `grade(outcome, engagement=...)` already accepts it, but bite
2 never passes it. This stays non-circular: it grades whether the maker still
holds THEIR OWN decision (a behavioral fact they report), never whether a
model thinks the decision was correct.

**Soft FSRS (D-FSRS-4, settled soft), mirroring soft-Nestor.** `fsrs` is a
soft dependency: `_fsrs()` imports it lazily and caches success;
`fsrs_available()` reports without raising. When it is present, `record_review`
and `is_due` use real FSRS. When it is ABSENT, they degrade to a fixed-
interval fallback (a held review grows the interval, a regression resets it) —
the resurface flow itself never depends on a heavy install, the same posture
bite 1 set for Nestor. Both scheduler kinds emit a card dict carrying a `due`
ISO field, so `is_due`/`due_at` read either kind identically; the `kind` field
(`"fsrs"` / `"fixed"`) records which produced it, and `record_review` starts a
fresh card rather than trusting a blob the other kind wrote.

Not in scope: resurfacing (that is `checkpoint_calibration.resurface`), bite 3's
engagement grade (the `Hard`/`Easy` half of the seam above), and any UI over
"here are your due decisions."

Usage (dev CLI):
    python stores/checkpoint_schedule.py review <builder_id> <pair_id> \\
        --outcome held|regressed [--root DIR]
    python stores/checkpoint_schedule.py due <builder_id> <pair_id> [--root DIR]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Reuse checkpoint_memory's own already-validated pieces — its DEFAULT root and
# its `_check_builder_id` (which itself delegates to principal.py). Loaded the
# same spec_from_file_location way checkpoint_calibration loads checkpoint, so
# there is one source for the builder-id charset and the checkpoint root, not a
# second copy that could drift. checkpoint_memory is soft-Nestor at import, so
# importing it here does NOT pull in Nestor.
_cm_spec = importlib.util.spec_from_file_location(
    "checkpoint_memory", _REPO / "stores" / "checkpoint_memory.py"
)
checkpoint_memory = importlib.util.module_from_spec(_cm_spec)
sys.modules["checkpoint_memory"] = checkpoint_memory
_cm_spec.loader.exec_module(checkpoint_memory)

DEFAULT_CHECKPOINT_ROOT = checkpoint_memory.DEFAULT_CHECKPOINT_ROOT

OUTCOME_HELD = "held"
OUTCOME_REGRESSED = "regressed"

# FSRS Rating integer values (Again=1, Hard=2, Good=3, Easy=4) — used as the
# grade() return so grade() has no dependency on `fsrs` being importable; the
# FSRS path below converts an int back to a `Rating` via `Rating(int)`.
_RATING_AGAIN = 1
_RATING_HARD = 2
_RATING_GOOD = 3
_RATING_EASY = 4

# Fixed-interval fallback constants (only reached when `fsrs` is absent).
FIXED_BASE_INTERVAL_DAYS = 1.0
FIXED_MAX_INTERVAL_DAYS = 365.0


class ScheduleError(Exception):
    """Fail-closed refusal from this module — a bad `builder_id`, an unknown
    outcome, or a card file that did not honor its own shape. Never a re-wrap
    of a Nestor or FSRS internal error a caller should see directly."""


# ── FSRS: a soft dependency (lazy import, cached) ───────────────────────────
#
# Same import strategy checkpoint_memory uses for Nestor — see its "SOFT
# dependency at IMPORT time" section. Caches SUCCESS only, so a test that
# blocks `fsrs` via a meta-path finder after import still observes the new
# failure (mirrors the soft-Nestor degraded test).

_FSRS_MISSING_MSG = (
    "stores/checkpoint_schedule.py's real scheduler needs `fsrs` (PyPI, MIT), "
    "which is a soft/optional dependency (docs/design/the-forge-fsrs.md, "
    "D-FSRS-4). Install it with `pip install fsrs` for real spaced-repetition "
    "scheduling; without it, this module degrades to a fixed-interval fallback."
)

_fsrs_cache: "types.SimpleNamespace | None" = None


def _fsrs() -> "types.SimpleNamespace":
    """Import `fsrs` on first real use and cache it. Raises `ScheduleError`
    (never a bare `ImportError`) so a caller never needs to `import fsrs`
    itself — but note that, unlike Nestor for `checkpoint_memory`, no
    OPERATION here hard-requires FSRS: `record_review`/`is_due` fall back to
    fixed intervals when this raises, rather than refusing (D-FSRS-4)."""
    global _fsrs_cache
    if _fsrs_cache is None:
        try:
            from fsrs import Card, Rating, Scheduler
        except ImportError as e:
            raise ScheduleError(_FSRS_MISSING_MSG) from e
        _fsrs_cache = types.SimpleNamespace(Card=Card, Rating=Rating, Scheduler=Scheduler)
    return _fsrs_cache


def fsrs_available() -> bool:
    """True if `fsrs` can be imported right now, False otherwise — never
    raises. Callers use it to decide whether scheduling is real FSRS or the
    fixed-interval fallback; the module itself checks it inside
    `record_review`, so a caller does not have to."""
    try:
        _fsrs()
    except ScheduleError:
        return False
    return True


# ── the grade map (D-FSRS-2) ────────────────────────────────────────────────

def grade(outcome: str, engagement: float | None = None) -> int:
    """Map a resurface outcome to an FSRS rating integer (Again=1 .. Easy=4).

    Bite 2 only ever calls this with `engagement=None`:
      * `held`      -> Good (3)  — graduate the interval
      * `regressed` -> Again (1) — a lapse; FSRS resets stability

    The `engagement` parameter is the RESERVED seam for bite 3's
    friction/mirror signal (`#66`/`#67`): a held decision the maker barely
    re-engaged with is a weaker hold (Hard, resurface sooner) than one they
    re-argued (Easy, push it out). Implemented but dormant — nothing in bite 2
    passes a non-None engagement. A regression is `Again` regardless of
    engagement: you did not hold it, so how hard you thought about it doesn't
    enter. Kept non-circular by construction — see module docstring."""
    if outcome == OUTCOME_REGRESSED:
        return _RATING_AGAIN
    if outcome == OUTCOME_HELD:
        if engagement is None:
            return _RATING_GOOD
        if engagement < 0.34:
            return _RATING_HARD
        if engagement > 0.66:
            return _RATING_EASY
        return _RATING_GOOD
    raise ScheduleError(
        f"unknown resurface outcome {outcome!r} — expected "
        f"{OUTCOME_HELD!r} or {OUTCOME_REGRESSED!r}"
    )


# ── record a review -> a new card blob ──────────────────────────────────────

def record_review(
    prior_card: dict | None,
    outcome: str,
    now: datetime,
    *,
    engagement: float | None = None,
) -> dict:
    """Advance the schedule for one decision after a resurface. `prior_card`
    is the last blob this module wrote for that decision (or None for a
    decision reviewed for the first time). `now` is injected, never read from
    the wall clock in here (D-FSRS-3) — `resurface` fills it at its boundary.
    Returns a new card blob (always carrying a `due` ISO field and a `kind`).

    Real FSRS when `fsrs_available()`, else the fixed-interval fallback
    (D-FSRS-4). `grade()` validates `outcome` for both paths."""
    rating_int = grade(outcome, engagement)  # raises ScheduleError on a bad outcome

    if fsrs_available():
        fsrs = _fsrs()
        card = None
        if prior_card and prior_card.get("kind") == "fsrs" and isinstance(prior_card.get("card"), dict):
            try:
                card = fsrs.Card.from_dict(prior_card["card"])
            except Exception:  # noqa: BLE001 — a blob we can't parse is a fresh start, not a crash
                card = None
        if card is None:
            card = fsrs.Card()
        scheduler = fsrs.Scheduler()
        card, _log = scheduler.review_card(card, fsrs.Rating(rating_int), review_datetime=now)
        return {"kind": "fsrs", "card": card.to_dict(), "due": card.due.isoformat()}

    # ── fixed-interval fallback ──────────────────────────────────────────────
    prev_interval = 0.0
    if prior_card and prior_card.get("kind") == "fixed":
        try:
            prev_interval = float(prior_card.get("interval_days", 0.0))
        except (TypeError, ValueError):
            prev_interval = 0.0
    if outcome == OUTCOME_HELD:
        # first hold from nothing -> base; each subsequent hold doubles, capped
        interval = FIXED_BASE_INTERVAL_DAYS if prev_interval <= 0 else min(prev_interval * 2, FIXED_MAX_INTERVAL_DAYS)
    else:  # regressed
        interval = FIXED_BASE_INTERVAL_DAYS
    due = now + timedelta(days=interval)
    return {
        "kind": "fixed",
        "interval_days": interval,
        "last_review": now.isoformat(),
        "due": due.isoformat(),
    }


# ── read the schedule ────────────────────────────────────────────────────────

def due_at(card_dict: dict) -> datetime:
    """The next review time this card is due, parsed from its `due` field —
    written by either scheduler kind, read the same way."""
    try:
        return datetime.fromisoformat(card_dict["due"])
    except (KeyError, TypeError, ValueError) as e:
        raise ScheduleError(f"card has no parseable 'due' field: {card_dict!r}") from e


def is_due(card_dict: dict, now: datetime) -> bool:
    """True iff `now` is at or past this card's `due` time. `now` injected
    (D-FSRS-3). Replaces bite 2's fixed-interval `is_due(last, now,
    interval_days)` placeholder — the interval is now the card's own output,
    not a caller-supplied scalar, so the signature changed (the placeholder
    had no callers but its own tests; see the design doc)."""
    return now >= due_at(card_dict)


# ── the sidecar: one JSON file per builder, keyed by pair_id ─────────────────

def schedule_path(builder_id: str, root: Path = DEFAULT_CHECKPOINT_ROOT) -> Path:
    """`builder_id`'s own schedule file — `<root>/<builder_id>.schedule.json`.
    Validates `builder_id` through checkpoint_memory's own `_check_builder_id`
    (path-safe charset), and refuses a symlinked root, exactly as
    `checkpoint_memory.checkpoint_db_path` does — the schedule sits beside the
    Nestor db, under the same one-component-per-builder boundary."""
    try:
        builder_id = checkpoint_memory._check_builder_id(builder_id)
    except checkpoint_memory.CheckpointMemoryError as e:
        raise ScheduleError(f"builder_id rejected: {e}") from e
    root = Path(root)
    if root.is_symlink():
        raise ScheduleError(f"refusing to use a symlinked checkpoint root: {root}")
    return root / f"{builder_id}.schedule.json"


def _load_all(builder_id: str, root: Path) -> dict:
    path = schedule_path(builder_id, root=root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ScheduleError(f"schedule file for {builder_id!r} is unreadable: {e}") from e
    if not isinstance(data, dict):
        raise ScheduleError(f"schedule file for {builder_id!r} is not a JSON object")
    return data


def load_card(builder_id: str, card_id: str, root: Path = DEFAULT_CHECKPOINT_ROOT) -> dict | None:
    """The card blob previously saved for `(builder_id, card_id)`, or None if
    none was. `card_id` is the decision's Nestor `pair_id`."""
    return _load_all(builder_id, root).get(card_id)


def save_card(
    builder_id: str, card_id: str, card_dict: dict, root: Path = DEFAULT_CHECKPOINT_ROOT
) -> None:
    """Persist `card_dict` under `(builder_id, card_id)`. Creates the root
    0700 and the file 0600, matching every other dev-only store in this
    directory (`.principals/`, `.sessions/`, `.checkpoints/`)."""
    if not isinstance(card_id, str) or not card_id:
        raise ScheduleError("card_id (a Nestor pair_id) must be a non-empty str")
    path = schedule_path(builder_id, root=root)  # validates builder_id + root
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    data = _load_all(builder_id, root)
    data[card_id] = card_dict
    # write-then-rename would be nicer, but the sibling stores here write in
    # place too; a torn write is a dev-only-store risk this matches, not
    # widens. Written 0600 the same moment it is created.
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.chmod(path, 0o600)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_review(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    try:
        prior = load_card(args.builder_id, args.pair_id, root=Path(args.root))
        card = record_review(prior, args.outcome, now)
        save_card(args.builder_id, args.pair_id, card, root=Path(args.root))
    except ScheduleError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"kind": card["kind"], "due": card["due"], "fsrs": fsrs_available()}, indent=2))
    return 0


def _cmd_due(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    try:
        card = load_card(args.builder_id, args.pair_id, root=Path(args.root))
        if card is None:
            print(f"no schedule yet for pair_id={args.pair_id!r} — never reviewed", file=sys.stderr)
            return 1
        due = is_due(card, now)
    except ScheduleError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"due_at": card["due"], "is_due": due}, indent=2))
    return 0 if due else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="checkpoint_schedule.py")
    p.add_argument("--root", default=str(DEFAULT_CHECKPOINT_ROOT))
    sub = p.add_subparsers(dest="command", required=True)

    rv = sub.add_parser("review", help="record a held/regressed review, advancing the schedule")
    rv.add_argument("builder_id")
    rv.add_argument("pair_id", help="the decision's Nestor pair_id")
    rv.add_argument("--outcome", required=True, choices=[OUTCOME_HELD, OUTCOME_REGRESSED])
    rv.set_defaults(func=_cmd_review)

    du = sub.add_parser("due", help="is this decision due for review now")
    du.add_argument("builder_id")
    du.add_argument("pair_id")
    du.set_defaults(func=_cmd_due)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
