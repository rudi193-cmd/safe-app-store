"""The daily board: one board a day, seeded by the drand beacon nobody can grind.

A day's board is seeded by the randomness of one drand round: the round current
at that day's 00:00 UTC. Nobody, this app included, knows that randomness
before the round fires, so no one can pick a seed that makes the day easy, or
hand out the board before the day starts. Everyone who reads the same round
plays the same board, and anyone can check it from the round alone.

The beacon is the one script's (flatten F-14, F-16): the chain, the day's
round, the u32 seed (SHA-256's first four bytes over the randomness), the
seed id, the reader, the stamp and its check all live in willow-bot's
``onescript/beacon.py``, and this module takes them from the one script beside
safe-app-store (``$ONESCRIPT_HOME``, else ``<repos>/willow-bot/one-script``).
With none beside, importing this says why and stops; there is no fallback seed.
What stays here is catgrid's: turning a stamp into a board.

Said, not hidden: the beacon's BLS signature is not checked (``BLS_UNVERIFIED``);
a reader that fails, or answers for another round, gives no board and says why.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from .board import Board, generate


def _beacon():
    home = Path(os.environ.get("ONESCRIPT_HOME")
                or Path(__file__).resolve().parents[4] / "willow-bot" / "one-script")
    if not (home / "onescript" / "beacon.py").is_file():
        raise ImportError(f"catgrid's daily board needs the one script's beacon: no one-script at "
                          f"{home} (set ONESCRIPT_HOME)")
    if str(home) not in sys.path:
        sys.path.insert(0, str(home))
    return importlib.import_module("onescript.beacon")


_b = _beacon()
DRAND, CHAIN, GENESIS, PERIOD = _b.DRAND, _b.CHAIN, _b.GENESIS, _b.PERIOD
BLS_UNVERIFIED = _b.BLS_UNVERIFIED
round_for = _b.round_for
seed_of = _b.seed_u32
seed_id = _b.seed_id
drand_reader = _b.drand_reader
stamp = _b.day_stamp
check = _b.check_day_stamp


def board(st: dict, n: int = 6, k: int = 1) -> Board:
    """The daily board for a stamp that checks out; refuses one that doesn't."""
    why = check(st)
    if why:
        raise ValueError(why)
    return generate(st["seed"], n, k=k)


def main(argv=None) -> int:
    from datetime import datetime, timezone

    args = list(sys.argv[1:] if argv is None else argv)
    day = args[0] if args else datetime.now(timezone.utc).date().isoformat()
    st, why = stamp(day)
    if st is None:
        print(f"no daily board for {day}: {why}")
        return 1
    from .play import Game

    print(f"{day}: drand round {st['round']}, seed {st['seed']} ({st['bls']})")
    print(Game(board(st), st["seed"]).render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
