"""Driver: run all eleven added engines (deduction/bluffing + Hoyle) at N=500,
both policies, and print one JSON blob. This is the reproducer behind
`baselines/runlog-added-games.md` — run it and you regenerate those numbers
(unseeded, so counts wobble run-to-run; the structural findings are stable).

    python3 run_added_games.py
"""
import json
import importlib

GAMES = [
    "coup", "skull", "liars_dice", "cheat", "werewolf",
    "cribbage", "go_fish", "hearts", "crazy_eights", "spades", "war",
]


def main(N=500):
    out = {}
    for name in GAMES:
        mod = importlib.import_module(name)
        out[name] = {p: mod.run(p, N) for p in ("random", "john")}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
