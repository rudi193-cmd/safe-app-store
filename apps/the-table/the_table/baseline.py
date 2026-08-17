"""baseline.py — play every registered game many times and measure what falls out.

The parallel to game-lab's baselines, for the-table's spine: a reproducible,
seeded run over the registry, reporting the distributions that only appear at
volume (turn-order edges, ending biases, stat drift). Every number a report
prints traces to a real run of this file — nothing here is estimated.

It drives each game through the SAME GameSession surface the GM driver uses
(``reset`` / ``current_seat`` / ``legal_moves`` / ``step`` / ``is_terminal`` /
``result``), with a seeded random policy, and reads back only PUBLIC surfaces —
``result()`` and the final ``observe(0).view`` — never a game's private state.
So a game is measured exactly as a player (or the GM) would experience it.

Reproducibility: round ``i`` uses ``reset(i)`` and a policy drawn from
``random.Random(i)``. Same rounds -> same numbers, on any machine. (The scene
game reuses apps/game's engine, which seeds the *global* RNG in ``reset`` — one
more reason rounds are played one at a time, start to finish, never interleaved.)

Run it:
    python3 -m the_table.baseline            # N=500 (the committed baseline)
    python3 -m the_table.baseline 1000       # any N
"""
from __future__ import annotations

import random
import statistics
import sys

from . import registry

DEFAULT_ROUNDS = 500
CAP = 5000  # per-round step ceiling; a round that hits it is counted "unresolved"


def _play(name: str, seed: int, cap: int = CAP):
    """Play one round. Returns (turns, terminal, result, final_view)."""
    game = registry.make(name)
    policy = random.Random(seed)
    game.reset(seed)
    turns = 0
    while not game.is_terminal() and turns < cap:
        s = game.current_seat()
        game.step(s, policy.choice(list(game.legal_moves(s))))
        turns += 1
    # Final public view (seat 0 exists in every game); safe to read at terminal.
    return turns, game.is_terminal(), game.result(), game.observe(0).view


def _turn_stats(xs: list) -> dict:
    return {
        "min": min(xs),
        "median": int(statistics.median(xs)),
        "mean": round(statistics.mean(xs), 1),
        "max": max(xs),
    }


def run_baseline(rounds: int = DEFAULT_ROUNDS, cap: int = CAP) -> dict:
    """Play every registered game ``rounds`` times; return structured stats.

    The core stats are generic (every game): turns, unresolved (cap hits),
    win distribution by seat, and no-winner count. A few per-game extras are
    derived from the same public ``result()``/``view`` — the seat a card game
    favors, the ending a scene lands on — and stored raw for the report.
    """
    out = {}
    for name in registry.games():
        turns_all, unresolved = [], 0
        wins_by_seat: dict = {}
        no_winner = 0
        summaries: dict = {}          # Result.summary keyword -> count
        beat_status: dict = {}        # scene: aggregated view["tally"]
        success_hist: dict = {}       # scene: successes-per-round histogram
        debilities: list = []         # scene: view["debilities"] per round

        for seed in range(rounds):
            turns, terminal, res, view = _play(name, seed, cap)
            turns_all.append(turns)
            if not terminal:
                unresolved += 1
            if res.winners:
                for w in res.winners:
                    wins_by_seat[w] = wins_by_seat.get(w, 0) + 1
            else:
                no_winner += 1

            # per-game extras, all from public surfaces
            if "enrolled" in res.summary:
                summaries["enrolled"] = summaries.get("enrolled", 0) + 1
            elif "voided" in res.summary:
                summaries["voided"] = summaries.get("voided", 0) + 1
            if isinstance(view, dict) and "tally" in view:  # scene exposes a status tally
                for st, c in view["tally"].items():
                    beat_status[st] = beat_status.get(st, 0) + c
                succ = res.scores.get(0, 0)
                success_hist[succ] = success_hist.get(succ, 0) + 1
                if "debilities" in view:
                    debilities.append(view["debilities"])

        rec = {
            "rounds": rounds,
            "turns": _turn_stats(turns_all),
            "unresolved": unresolved,
            "wins_by_seat": {k: wins_by_seat.get(k, 0) for k in sorted(wins_by_seat)},
            "no_winner": no_winner,
        }
        if summaries:
            rec["endings"] = summaries
        if beat_status:
            rec["beat_status"] = beat_status
            rec["success_hist"] = success_hist
            rec["debilities"] = _turn_stats(debilities)
        out[name] = rec
    return out


def format_report(data: dict, rounds: int) -> str:
    lines = []
    lines.append("=" * 66)
    lines.append(f"THE TABLE — baselines · {rounds} rounds/game · random policy · seeds 0..{rounds - 1}")
    lines.append("=" * 66)
    for name, rec in data.items():
        t = rec["turns"]
        lines.append(f"\n▸ {name}  ({registry.describe(name)})")
        cap_note = f"   ·   {rec['unresolved']} hit the {CAP} cap" if rec["unresolved"] else ""
        lines.append(f"    turns/round: min {t['min']} · median {t['median']} · "
                     f"mean {t['mean']} · max {t['max']}{cap_note}")
        if len(rec["wins_by_seat"]) > 1:  # multi-seat: show the turn-order distribution
            top = max(rec["wins_by_seat"].values())
            lines.append("    win distribution (turn order):")
            for seat, w in rec["wins_by_seat"].items():
                bar = "█" * round(40 * w / top)
                lines.append(f"       seat {seat}: {w:4d}  {100 * w / rounds:5.1f}%  {bar}")
            lines.append(f"    no winner (stall): {rec['no_winner']}  ({100 * rec['no_winner'] / rounds:.1f}%)")
        if "endings" in rec:
            for k, v in rec["endings"].items():
                lines.append(f"       {k:11s}: {v:4d}  {100 * v / rounds:5.1f}%")
        if "beat_status" in rec:
            beats = sum(rec["beat_status"].values())
            lines.append(f"    beat outcomes across {beats} beats:")
            for st, c in rec["beat_status"].items():
                lines.append(f"       {st:16s}: {c:5d}  {100 * c / beats:5.1f}%")
            hist = [rec["success_hist"].get(i, 0) for i in range(7)]
            d = rec["debilities"]
            lines.append(f"    successes per 6-beat scene (0..6): {hist}")
            lines.append(f"    debilities/scene: min {d['min']} · median {d['median']} · "
                         f"mean {d['mean']} · max {d['max']}")
            went_well = sum(rec["wins_by_seat"].values())
            lines.append(f"    scene 'went well' (successes>=chaos): {went_well}  "
                         f"({100 * went_well / rounds:.1f}%)")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    rounds = int(argv[0]) if argv else DEFAULT_ROUNDS
    print(format_report(run_baseline(rounds), rounds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
