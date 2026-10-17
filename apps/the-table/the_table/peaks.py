"""peaks.py -- the exact-odds forecaster for an authored the-table world.

PROVENANCE: the pure half of
``willows-grove/seat/willow/experiments/foreshadow-2026-10-16/peaks.py``
(``bucket_probs``, ``action_beats``, ``first_decision``, ``mentions``,
``exact``, ``swing``; lines 46-139 of the experiment), moved here per the
foreshadow handoff of 2026-10-16, Q16 ("Should the experiment scripts become
a the-table module (``apps/the-table/the_table/peaks.py``), or stay here as
measurement?") and box-build SPEC ruling R8 / SPEC-documented C19. The house
already had this: it was built and run as measurement on 2026-10-16, and this
module ports it rather than writing it again (safe-app-store CLAUDE.md rule
11). The experiment's ``measured()`` -- N seeded runs through the real
``StorySession`` -- stays with the experiment; it is the thing this module's
arithmetic is checked against (``tests/test_peaks.py``), not part of it.

WHAT THIS MODULE IS: arithmetic over a world dict. It runs no dice, opens no
file, imports nothing from ``story_session``, and reads nothing private. It
enumerates ``2d6 + stat`` over its 36 outcomes and reads each sum with the
SAME three-way bucket ``StorySession.step`` applies to ``Engine.roll``'s
result -- strong (10+) / weak (7-9) / miss (6-) -- so the odds it states are
the odds the session actually plays. ``bucket()`` below IS that read, kept
here as a function so a test can hold the two side by side.

EXACTNESS: every probability is a ``fractions.Fraction`` until the edge.
``exact()`` returns Fractions; ``distribution()`` converts to ``float`` only
in the list it hands to one-script, because a wager row is JSON. The Fraction
mass over every path is exactly 1; the float mass is 1 to within rounding.

THE WAGER SHAPE: ``distribution()`` returns the ``list[dict]`` one-script's
``Run.wager(wid, distribution=...)`` records and ``reverse._match_distribution``
later lines a sealed outcome up against: each entry ``{"path", "p", "band"}``,
``path`` a ``-``-joined bucket string (``"strong-weak"``), ``p`` a float,
``band`` one of ``likely`` / ``middle`` / ``outlier``. Every path is kept;
nothing is smoothed (``onescript/predict.py:6-7``).

TURN MODEL MIRRORED (not imported): a run plays action beats in script order
until the first decision beat, which halts it -- no policy may seal, so no
path crosses one. The beat at turn ``t`` is rolled by seat ``t % seats`` with
that seat's own stat sheet, exactly as ``StorySession.current_seat()`` rotates
and ``StorySession.reset()`` builds sheets (``base_stat`` fills any stat a
character omits). ``sheets_for()`` is that construction, stated once here.

CLI (the one place this module touches I/O):

    python3 -m the_table.peaks <world.json> [--policy suggested|random] [--wager]

``--wager`` prints the distribution as JSON for ``onescript forecast <id>
--dist -``; without it the full ``exact()`` report prints, floats at the edge.
"""
from __future__ import annotations

import itertools
import math
import re
from fractions import Fraction
from typing import Any

BUCKETS = ("strong", "weak", "miss")
VALENCE = {"strong": 1, "weak": 0, "miss": -1}
POLICIES = ("suggested", "random")

# Band cut-off for ``distribution()``: ``middle`` at or above it, ``outlier``
# below. SPEC-documented §8(e) left the cut silent; 0.05 is the recorded pick.
MIDDLE_FLOOR = Fraction(1, 20)

_DICE = tuple(itertools.product(range(1, 7), repeat=2))  # the 36 outcomes


# -- the roll, read the way StorySession reads it ------------------------------

def bucket(total: int) -> str:
    """StorySession.step's read of a raw ``2d6 + stat`` sum: strong (10+),
    weak (7-9), miss (6-). Kept as a function so the two can be compared."""
    if total >= 10:
        return "strong"
    if total >= 7:
        return "weak"
    return "miss"


def bucket_counts(stat: int) -> dict:
    """How many of the 36 ``2d6`` outcomes land in each bucket at ``stat``."""
    counts = {b: 0 for b in BUCKETS}
    for a, b in _DICE:
        counts[bucket(a + b + stat)] += 1
    return counts


def bucket_probs(stat: int) -> dict:
    """``{"strong", "weak", "miss"}`` -> ``Fraction``, summing to exactly 1.
    Any integer stat: at ``stat <= -6`` every outcome is a miss, at
    ``stat >= 8`` every outcome is strong."""
    return {k: Fraction(v, 36) for k, v in bucket_counts(stat).items()}


def entropy(p: dict) -> float:
    """Bits of uncertainty in a bucket distribution (float: a reading, not a
    probability)."""
    return -sum(float(v) * math.log2(float(v)) for v in p.values() if v > 0)


# -- the world, read the way StorySession reads it -----------------------------

def sheets_for(world: dict) -> list[dict]:
    """One stat sheet per seated character, in character order, with the
    world's ``base_stat`` filling any stat a character omits -- the same
    construction ``StorySession.reset()`` makes."""
    return [
        {s: c["stats"].get(s, world["base_stat"]) for s in world["stats"]}
        for c in world["characters"]
        if c.get("seat")
    ]


def action_beats(world: dict) -> list[dict]:
    """The beats a run can play before the first decision beat, each a copy
    tagged with its scene index under ``_scene`` (the world is not mutated).
    A world opening on a decision gives ``[]``; a world with no decision
    beat gives every beat."""
    out = []
    for si, sc in enumerate(world.get("scenes", [])):
        for b in sc["beats"]:
            if b["kind"] == "decision":
                return out
            out.append({**b, "_scene": si})
    return out


def first_decision(world: dict) -> dict | None:
    """The first decision beat in script order, or ``None``."""
    for sc in world.get("scenes", []):
        for b in sc["beats"]:
            if b["kind"] == "decision":
                return b
    return None


def aliases(char: dict) -> set[str]:
    name = char["name"].lower()
    bare = re.sub(r"^the\s+", "", name)
    out = {name, bare, char["id"].lower()}
    if bare.split():
        out.add(bare.split()[0])
    return out


def mentions(world: dict, text: str) -> set[str]:
    """The ids of the world's characters named in ``text`` (whole-word, by
    name, bare name, first name or id)."""
    low = text.lower()
    return {
        c["id"]
        for c in world.get("characters", [])
        if any(re.search(rf"\b{re.escape(a)}\b", low) for a in aliases(c))
    }


# -- the odds ------------------------------------------------------------------

def _check_policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES!r}, got {policy!r}")


def beat_probs(world: dict, sheet: dict, beat: dict, policy: str = "suggested") -> dict:
    """The bucket odds for one beat rolled from one seat's ``sheet``.
    ``suggested``: the beat's own ``suggests`` stat. ``random``: the seat
    picks uniformly over ``world["stats"]`` (the experiment's second policy),
    so the odds are the mean of the per-stat odds."""
    _check_policy(policy)
    if policy == "suggested":
        return bucket_probs(sheet[beat["suggests"]])
    stats = world["stats"]
    p = {k: Fraction(0) for k in BUCKETS}
    for s in stats:
        for k, v in bucket_probs(sheet[s]).items():
            p[k] += v / len(stats)
    return p


def exact(world: dict, sheets: list[dict] | None = None, policy: str = "suggested") -> dict:
    """Every path through the action beats before the first decision, with
    its exact probability.

    ``sheets``: one stat sheet per seated character (``sheets_for(world)``
    when omitted); the beat at turn ``t`` is rolled by seat ``t % len(sheets)``
    as ``StorySession`` rotates.

    Returns ``{"per_beat": {beat_id: {bucket: Fraction}}, "paths": [...]}``,
    paths sorted by probability descending (stable, so ties keep
    enumeration order). Each path carries ``path`` (``"strong-weak"``), ``p``
    (``Fraction``), ``curve`` (running valence), ``firsts`` (which outcome
    first introduces which characters), ``met`` (every character known by
    the end) and ``held`` (strong >= miss, ``result()``'s own verdict rule).
    A world with no action beat before its first decision yields one path,
    ``""``, with ``p == 1``.
    """
    _check_policy(policy)
    if sheets is None:
        sheets = sheets_for(world)
    beats = action_beats(world)
    if beats and not sheets:
        raise ValueError("a world with action beats needs at least one seated character")

    per_beat = {}
    for t, b in enumerate(beats):
        per_beat[b["id"]] = beat_probs(world, sheets[t % len(sheets)], b, policy)

    scenes = world.get("scenes", [])
    opening = " ".join([world.get("setting", "")] + (scenes[0]["opening"] if scenes else []))
    known0 = mentions(world, opening)

    paths = []
    for combo in itertools.product(BUCKETS, repeat=len(beats)):
        prob = Fraction(1)
        for b, k in zip(beats, combo):
            prob *= per_beat[b["id"]][k]
        curve, level, known, firsts = [], 0, set(known0), []
        scene_at = 0
        for b, k in zip(beats, combo):
            if b["_scene"] != scene_at:  # crossing into a new scene: its opening is seen
                scene_at = b["_scene"]
                known |= mentions(world, " ".join(scenes[scene_at]["opening"]))
            level += VALENCE[k]
            curve.append(level)
            new = mentions(world, b["outcomes"][k]) - known
            known |= new
            if new:
                firsts.append({"beat": b["id"], "bucket": k, "introduces": sorted(new)})
        paths.append({
            "path": "-".join(combo),
            "p": prob,
            "curve": curve,
            "firsts": firsts,
            "met": sorted(known),
            "held": combo.count("strong") >= combo.count("miss"),
        })
    paths.sort(key=lambda x: -x["p"])
    return {"per_beat": per_beat, "paths": paths}


def swing(world: dict, beat: dict, p: dict) -> dict:
    """How much the roll at this beat changes what comes after it (a reading
    in floats, rounded for the eye)."""
    intro = {k: sorted(mentions(world, beat["outcomes"][k])) for k in BUCKETS}
    distinct_casts = len({tuple(v) for v in intro.values()})
    return {
        "entropy_bits": round(entropy(p), 3),
        "max_bits": round(math.log2(3), 3),
        "outcome_casts": intro,
        "cast_diverges": distinct_casts > 1,
        "p_strong": round(float(p["strong"]), 3),
        "p_weak": round(float(p["weak"]), 3),
        "p_miss": round(float(p["miss"]), 3),
    }


def band_of(p: Fraction, top: Fraction) -> str:
    """``likely`` at the top probability, ``middle`` at or above
    ``MIDDLE_FLOOR``, ``outlier`` below."""
    if p == top:
        return "likely"
    if p >= MIDDLE_FLOOR:
        return "middle"
    return "outlier"


def distribution(
    world: dict,
    sheets: list[dict] | None = None,
    policy: str = "suggested",
    *,
    top: int | None = None,
) -> list[dict]:
    """The one-script wager ``distribution``: ``[{"path", "p", "band"}, ...]``
    in probability order, ``p`` a float (the one edge where Fractions leave),
    ``band`` from ``band_of``. Every path at the top probability is
    ``likely`` (a tie is two likely paths, not one likely and one middle).
    All paths are kept unless ``top`` is given, which keeps only the first
    ``top`` entries -- the mass then no longer sums to 1, and a sealed outcome
    down a dropped path escalates to the human in ``reverse.reconcile_wagers``
    rather than reconciling."""
    paths = exact(world, sheets, policy)["paths"]
    top_p = paths[0]["p"]
    out = [{"path": x["path"], "p": float(x["p"]), "band": band_of(x["p"], top_p)} for x in paths]
    if top is not None:
        if not isinstance(top, int) or isinstance(top, bool) or top < 1:
            raise ValueError(f"top must be a positive int, got {top!r}")
        out = out[:top]
    return out


# -- CLI: the one place this module touches I/O -------------------------------

def _floated(x: Any) -> Any:
    if isinstance(x, Fraction):
        return float(x)
    if isinstance(x, dict):
        return {k: _floated(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_floated(v) for v in x]
    return x


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    from .worlds import load_world

    ap = argparse.ArgumentParser(prog="python3 -m the_table.peaks")
    ap.add_argument("world", help="path to a world JSON file")
    ap.add_argument("--policy", choices=POLICIES, default="suggested")
    ap.add_argument("--wager", action="store_true",
                    help="print only the one-script wager distribution")
    ap.add_argument("--top", type=int, default=None)
    args = ap.parse_args(argv)
    world = load_world(args.world)
    if args.wager:
        print(json.dumps(distribution(world, policy=args.policy, top=args.top), indent=1))
    else:
        print(json.dumps(_floated(exact(world, policy=args.policy)), indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
