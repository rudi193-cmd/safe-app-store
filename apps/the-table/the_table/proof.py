"""proof.py — the end-to-end demonstration: TWO games, bureau and crazy
eights, each driven by the SAME game-agnostic GM loop through the SAME
uniform GameSession protocol, each remembered in its own tamper-evident
ai-game-master ledger, each validated by ai-game-master's OWN verifier.

Run with:
    python3 -m the_table.proof        (from apps/the-table/)
    python3 the_table/proof.py        (from apps/the-table/)

Wires each game + a LedgerSink pointed at its own fresh temp box dir, runs
run_session with a seeded (deterministic) random_policy, and asserts per game:
  * the game reached terminal (not a max_turns cap-out)
  * ai-game-master's own verify_ledger.py accepts the resulting chain

Prints a short human-readable section per game (transcript-ish, Result, turn
count, chain head, verify result), then one combined line, and exits 0 only
if BOTH games verify clean.

Bureau's own proof behavior (seed, cap, transcript style, assertions) is
unchanged from the walking skeleton's first slice -- crazy_eights is added
alongside it, through the identical run_session/LedgerSink, unmodified.
"""
from __future__ import annotations

import random
import shutil
import sys
import tempfile

try:
    from .bureau_adapter import BureauSession
    from .crazy_eights_adapter import CrazyEightsSession
    from .gm import GMError, random_policy, run_session
    from .ledger_sink import LedgerSink
except ImportError:
    # Support `python3 the_table/proof.py` (run as a plain script, no
    # enclosing package) in addition to `python3 -m the_table.proof`.
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from the_table.bureau_adapter import BureauSession
    from the_table.crazy_eights_adapter import CrazyEightsSession
    from the_table.gm import GMError, random_policy, run_session
    from the_table.ledger_sink import LedgerSink

BUREAU_SEED = 7          # deterministic: same seed the throwaway smoke used
BUREAU_MAX_TURNS = 500   # matches the headroom test_bureau_adapter.py's STEP_CAP uses

CRAZY_EIGHTS_SEED = 7    # deterministic
CRAZY_EIGHTS_MAX_TURNS = 2000  # generous slack over the adapter's own defensive cap (1000)


def _play_one_game(*, title: str, game, session_id: str, seed: int, max_turns: int) -> bool:
    """Run one GameSession end to end through run_session + a fresh LedgerSink
    box, print a short section for it, and return whether the ledger verified
    clean. Raises (uncaught) on anything that should fail the whole proof
    other than a failed verify -- a capped/unterminated game, for instance.
    """
    box_dir = tempfile.mkdtemp(prefix="the-table-proof-")
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
                session_id=session_id,
            )
        except GMError as exc:
            print(f"FAIL ({title}): {exc}", file=sys.stderr)
            return False

        # The crux: the game actually finished, not merely stopped.
        assert game.is_terminal(), f"{title}: proof requires the game to reach a real terminal state"

        transcript_lines = transcript[:5] or ["(no narration recorded)"]

        verified = sink.verify()

        print("-" * 60)
        print(title)
        print("-" * 60)
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
    print("=" * 60)
    print("THE TABLE — end-to-end proof (two games x one GM loop x one ledger sink)")
    print("=" * 60)

    bureau_ok = _play_one_game(
        title="GAME 1: bureau (single-seat) — BureauSession",
        game=BureauSession(),
        session_id=f"proof-bureau-seed-{BUREAU_SEED}",
        seed=BUREAU_SEED,
        max_turns=BUREAU_MAX_TURNS,
    )

    crazy_eights_ok = _play_one_game(
        title="GAME 2: crazy eights (4-seat, hidden info) — CrazyEightsSession",
        game=CrazyEightsSession(),
        session_id=f"proof-crazy-eights-seed-{CRAZY_EIGHTS_SEED}",
        seed=CRAZY_EIGHTS_SEED,
        max_turns=CRAZY_EIGHTS_MAX_TURNS,
    )

    print("=" * 60)
    print(f"bureau:       {'VERIFIED' if bureau_ok else 'FAILED'}")
    print(f"crazy_eights: {'VERIFIED' if crazy_eights_ok else 'FAILED'}")
    both_ok = bureau_ok and crazy_eights_ok
    print(f"COMBINED:     {'PASS' if both_ok else 'FAIL'}")
    print("=" * 60)

    if both_ok:
        print("PROOF PASSED: two different games, driven through the SAME GameSession "
              "protocol by the SAME GM loop, are each remembered in a tamper-evident "
              "ai-game-master ledger and validated by ai-game-master's own verifier -- "
              "the protocol is game-agnostic.")
        return 0

    print("PROOF FAILED: see FAILED game(s) above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
