"""The daily board: one board a day, seeded by the drand beacon nobody can grind.

A day's board is seeded by the randomness of one drand round: the round current
at that day's 00:00 UTC. Nobody, this app included, knows that randomness
before the round fires, so no one can pick a seed that makes the day easy, or
hand out the board before the day starts. Everyone who reads the same round
plays the same board, and anyone can check it from the round alone.

Restated, not imported (catgrid stays in its lane, stdlib-only): the chain,
genesis and period are willow-bot's ``onescript/beacon.py`` (the League of
Entropy default chain, 30 s rounds), and ``seed_id`` is the-table's
``StreamRandom.seed_id`` (first 16 hex of SHA-256 over the seed bytes).
``tests/test_daily.py`` pins them, and compares them with willow-bot's when it
is beside this repo: that test is the named middle for the pair.

The board's seed is the first four bytes of SHA-256 over the randomness, as a
u32: every board seed catgrid takes is a u32 (``rng.Rng``).

Said, not hidden:

* the beacon's BLS signature is not checked: the randomness is what the reader
  says round R is (``BLS_UNVERIFIED``, as willow-bot's beacon says it);
* a reader that fails, or answers for another round, gives no board and says
  why. There is no fallback seed: a daily board from the clock would be one
  someone could know in advance.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date as Date, datetime, timezone

from .board import Board, generate

DRAND = "https://api.drand.sh"
CHAIN = "8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce"
GENESIS, PERIOD = 1595431050, 30
BLS_UNVERIFIED = (
    "the beacon's BLS signature is not checked: the randomness is what the "
    "beacon reader says the round is"
)
_RANDOMNESS = re.compile(r"[0-9a-f]{64}")


def round_for(day: str) -> int:
    """The drand round current at ``day`` (YYYY-MM-DD) 00:00 UTC."""
    d = Date.fromisoformat(day)
    t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
    if t < GENESIS:
        raise ValueError(f"{day} is before the beacon's first round")
    return (t - GENESIS) // PERIOD + 1


def seed_of(randomness: str) -> int:
    """The board seed for a round's randomness: SHA-256's first four bytes."""
    return int.from_bytes(hashlib.sha256(bytes.fromhex(randomness)).digest()[:4], "big")


def seed_id(randomness: str) -> str:
    """the-table's ``StreamRandom.seed_id`` for a hex seed."""
    return hashlib.sha256(bytes.fromhex(randomness)).hexdigest()[:16]


def drand_reader(rnd: int) -> dict:
    """Round ``rnd`` from drand over HTTPS. Raises on any failure (the caller
    says why). BLS is not checked."""
    import json
    import urllib.request

    with urllib.request.urlopen(f"{DRAND}/{CHAIN}/public/{int(rnd)}", timeout=15) as r:
        return json.loads(r.read())


def stamp(day: str, read=drand_reader) -> tuple[dict | None, str]:
    """(stamp, "") for ``day``'s board, or (None, why). A stamp is the round,
    its randomness, and the seed and seed_id they give: all a replay needs."""
    try:
        rnd = round_for(day)
    except ValueError as e:
        return None, str(e)
    try:
        got = read(rnd)
    except Exception as e:  # any failure of the reader: said, never guessed
        return None, f"the beacon could not be read: {type(e).__name__}: {e}"
    if not isinstance(got, dict) or got.get("round") != rnd:
        return None, f"the beacon answered for {got.get('round') if isinstance(got, dict) else got!r}, not round {rnd}"
    r = got.get("randomness")
    if not isinstance(r, str) or not _RANDOMNESS.fullmatch(r):
        return None, f"round {rnd} carries no randomness (64 hex)"
    return {"day": day, "round": rnd, "randomness": r, "seed": seed_of(r),
            "seed_id": seed_id(r), "bls": BLS_UNVERIFIED}, ""


def check(st: dict) -> str:
    """Why this stamp is not ``day``'s, or "" when it holds together: the round
    is the day's, and the seed is the randomness's."""
    try:
        if st["round"] != round_for(st["day"]):
            return f"round {st['round']} is not {st['day']}'s ({round_for(st['day'])})"
        if not _RANDOMNESS.fullmatch(st["randomness"]):
            return "the stamp carries no randomness (64 hex)"
        if st["seed"] != seed_of(st["randomness"]) or st["seed_id"] != seed_id(st["randomness"]):
            return "the seed is not the randomness's: the board was not seeded by the beacon"
    except (KeyError, TypeError, ValueError) as e:
        return f"not a daily stamp ({type(e).__name__}: {e})"
    return ""


def board(st: dict, n: int = 6, k: int = 1) -> Board:
    """The daily board for a stamp that checks out; refuses one that doesn't."""
    why = check(st)
    if why:
        raise ValueError(why)
    return generate(st["seed"], n, k=k)


def main(argv=None) -> int:
    import sys

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
