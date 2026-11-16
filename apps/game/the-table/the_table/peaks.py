"""peaks.py -- the table's name for the one script's odds (flatten F-14).

The exact-odds forecaster for an authored world -- the 36 outcomes of 2d6,
the strong / weak / miss buckets, a world's exact path distribution and its
likely / middle / outlier bands -- lives in the one script's
``onescript/odds.py``, which reads world dicts and touches no I/O. Every name
it has is this module's too (the table's callers read ``peaks.bucket``,
``peaks.world_key`` ... as before), and the one piece that is the table's
stays here: loading a world from disk, for the CLI

    python3 -m the_table.peaks <world.json> [--policy suggested|random] [--wager]

``--wager`` prints the distribution as JSON for ``onescript forecast <id>
--dist -``; without it the full ``exact()`` report prints, floats at the edge.

NAMING THE OUTCOME: a sealed outcome names its entry by ``path_index`` or by
its FULL path string (e.g. ``strong-weak-miss``); one-script matches a partial
string to the first entry containing it, so never seal a partial path.

With no one script beside, importing this raises ``host.Unreachable`` and
says why (F-16).
"""
from __future__ import annotations

from .host import onescript_module

_odds = onescript_module("odds")
# the one script's names, as this module's (one copy, F-16)
globals().update({k: v for k, v in vars(_odds).items() if not k.startswith("__")})


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    from .worlds import load_world

    ap = argparse.ArgumentParser(
        prog="python3 -m the_table.peaks",
        description="Exact 2d6+stat odds over a the-table world's action beats "
                    "before its first decision.",
        epilog="A sealed outcome must name its entry by path_index or by the FULL "
               "path string (e.g. 'strong-weak-miss'); one-script matches a partial "
               "string to the first entry containing it, so never seal a partial path.",
    )
    ap.add_argument("world", help="path to a world JSON file")
    ap.add_argument("--policy", choices=_odds.POLICIES, default="suggested",
                    help="suggested: each beat's own stat; random: uniform over the world's stats")
    ap.add_argument("--wager", action="store_true",
                    help="print only the one-script wager distribution "
                         "([{path, p, band}], every path, mass 1), for "
                         "`onescript forecast <id> --dist -`")
    ap.add_argument("--top", type=int, default=None,
                    help="keep only the first N entries (mass then < 1; one-script "
                         "refuses such a forecast -- for reading, not wagering)")
    args = ap.parse_args(argv)
    world = load_world(args.world)
    if args.wager:
        print(json.dumps(_odds.distribution(world, policy=args.policy, top=args.top), indent=1))
    else:
        print(json.dumps(_odds._floated(_odds.exact(world, policy=args.policy)), indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
