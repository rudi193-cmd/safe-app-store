"""proof.py — the end-to-end demonstration: EVERY registered game, each
driven by the SAME game-agnostic GM loop through the SAME uniform
GameSession protocol, each remembered in its own tamper-evident
ai-game-master ledger, each validated by ai-game-master's OWN verifier.

Run with:
    python3 -m the_table.proof        (from apps/the-table/)
    python3 the_table/proof.py        (from apps/the-table/)

Loops over ``registry.games()`` (today: bureau, crazy_eights, scene). For
each name it ``make()``s a fresh session, wires it to a fresh temp
``LedgerSink`` box, runs ``run_session`` with a seeded (deterministic)
``random_policy``, and asserts:
  * the game reached terminal (not a max_turns cap-out)
  * ai-game-master's own verify_ledger.py accepts the resulting chain

Prints a short human-readable section per game (transcript-ish, Result, turn
count, chain head, verify result), then one combined line, and exits 0 only
if EVERY registered game verifies clean.

DETERMINISM NOTE (why games run one at a time, never interleaved): the
`scene` game (SceneSession, over apps/game's engine) reseeds the GLOBAL
`random` module in its own `reset()` -- see game_engine_adapter.py's module
docstring, trap 3. `crazy_eights` and `bureau` each own a private
`random.Random(seed)` and are unaffected by that, but the reverse is not
true: constructing every session up front and stepping them in an
interleaved order would let `scene`'s reseed land between two of another
game's `random_policy` draws (`random_policy` draws from the SAME global
module `random.seed()` reseeds) and silently perturb it. So this loop
`make()`s, runs to completion, and verifies ONE game before moving to the
next -- never two sessions alive and stepping at once.
"""
from __future__ import annotations

import random
import shutil
import sys
import tempfile

try:
    from . import registry
    from .gm import GMError, random_policy, run_session
    from .ledger_sink import LedgerSink
except ImportError:
    # Support `python3 the_table/proof.py` (run as a plain script, no
    # enclosing package) in addition to `python3 -m the_table.proof`.
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from the_table import registry
    from the_table.gm import GMError, random_policy, run_session
    from the_table.ledger_sink import LedgerSink

SEED = 7  # deterministic: same seed the throwaway smoke / earlier proof used
MAX_TURNS = 2000  # generous slack over every adapter's own defensive cap


def _play_one_game(*, name: str, seed: int, max_turns: int) -> bool:
    """make() a fresh session for ``name``, run it end to end through
    run_session + a fresh LedgerSink box, print a short section for it, and
    return whether the ledger verified clean. Raises (uncaught) on anything
    that should fail the whole proof other than a failed verify -- a
    capped/unterminated game, for instance.
    """
    game = registry.make(name)
    box_dir = tempfile.mkdtemp(prefix=f"the-table-proof-{name}-")
    sink = LedgerSink(box_dir=box_dir)
    try:
        policy = random_policy(random.Random(seed))

        # Wrap reset()/step() purely to collect narration lines for the
        # printed transcript below -- run_session itself is still the only
        # thing driving the game; this wrapping observes, it does not
        # participate in turn logic or move selection.
        transcript: list = []
        turns_taken = [0]
        _orig_reset, _orig_step = game.reset, game.step

        def _reset_and_record(seed_):
            obs = _orig_reset(seed_)
            transcript.extend(obs.narration)
            return obs

        def _step_and_record(seat, move):
            obs = _orig_step(seat, move)
            transcript.extend(obs.narration)
            turns_taken[0] += 1
            return obs

        game.reset, game.step = _reset_and_record, _step_and_record

        try:
            result = run_session(
                game,
                policy,
                seed=seed,
                sink=sink,
                max_turns=max_turns,
                session_id=f"proof-{name}-seed-{seed}",
            )
        except GMError as exc:
            print(f"FAIL ({name}): {exc}", file=sys.stderr)
            return False

        # The crux: the game actually finished, not merely stopped.
        assert game.is_terminal(), f"{name}: proof requires the game to reach a real terminal state"

        transcript_lines = transcript[:5] or ["(no narration recorded)"]

        verified = sink.verify()

        print("-" * 60)
        print(f"GAME: {name} — {registry.describe(name)}")
        print("-" * 60)
        print(f"seats:           {game.seats}")
        print(f"seed:            {seed}")
        print(f"terminal reached: {game.is_terminal()}")
        print(f"turns taken:     {turns_taken[0]}")
        print("transcript (first 5 narration lines seen):")
        for line in transcript_lines:
            print(f"  | {line}")
        print(f"result.summary:  {result.summary}")
        print(f"result.winners:  {result.winners}")
        print(f"result.scores:   {result.scores}")
        print(f"chain head:      {sink.head()}")
        print(f"ledger verify():  {verified}")
        print("-" * 60)

        return verified
    finally:
        sink.close()
        shutil.rmtree(box_dir, ignore_errors=True)


def main() -> int:
    names = registry.games()

    print("=" * 60)
    print(f"THE TABLE — end-to-end proof ({len(names)} games x one GM loop x one ledger sink)")
    print("=" * 60)

    # One game at a time, start to finish -- see the determinism note in the
    # module docstring for why this loop never constructs/interleaves two
    # sessions at once.
    outcomes: dict = {}
    for name in names:
        outcomes[name] = _play_one_game(name=name, seed=SEED, max_turns=MAX_TURNS)

    print("=" * 60)
    for name in names:
        print(f"{name}:{' ' * max(1, 14 - len(name))}{'VERIFIED' if outcomes[name] else 'FAILED'}")
    all_ok = all(outcomes.values())
    print(f"COMBINED:     {'PASS' if all_ok else 'FAIL'}")
    print("=" * 60)

    if all_ok:
        print(f"PROOF PASSED: {len(names)} games ({', '.join(names)}), driven through the SAME "
              "GameSession protocol by the SAME GM loop, are each remembered in a "
              "tamper-evident ai-game-master ledger and validated by ai-game-master's "
              "own verifier -- the protocol is game-agnostic.")
        return 0

    print("PROOF FAILED: see FAILED game(s) above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
