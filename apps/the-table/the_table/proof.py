"""proof.py — the end-to-end demonstration: bureau, driven by the GM loop
through the uniform GameSession protocol, remembered in a tamper-evident
ai-game-master ledger and validated by ai-game-master's OWN verifier.

Run with:
    python3 -m the_table.proof        (from apps/the-table/)
    python3 the_table/proof.py        (from apps/the-table/)

Wires BureauSession + a LedgerSink pointed at a fresh temp box dir, runs
run_session with a seeded (deterministic) random_policy, and asserts:
  * the game reached terminal (not a max_turns cap-out)
  * ai-game-master's own verify_ledger.py accepts the resulting chain

Prints a short human-readable transcript and exits 0 on success, nonzero
(via the uncaught exception / assertion) on any failure.
"""
from __future__ import annotations

import random
import shutil
import sys
import tempfile

try:
    from .bureau_adapter import BureauSession
    from .gm import GMError, random_policy, run_session
    from .ledger_sink import LedgerSink
except ImportError:
    # Support `python3 the_table/proof.py` (run as a plain script, no
    # enclosing package) in addition to `python3 -m the_table.proof`.
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from the_table.bureau_adapter import BureauSession
    from the_table.gm import GMError, random_policy, run_session
    from the_table.ledger_sink import LedgerSink

SEED = 7          # deterministic: same seed the throwaway smoke used
MAX_TURNS = 500    # matches the headroom test_bureau_adapter.py's STEP_CAP uses


def main() -> int:
    box_dir = tempfile.mkdtemp(prefix="the-table-proof-")
    sink = LedgerSink(box_dir=box_dir)
    try:
        game = BureauSession()
        policy = random_policy(random.Random(SEED))

        # Wrap reset()/step() purely to collect narration lines for the
        # printed transcript below -- run_session itself is still the only
        # thing driving the game; this wrapping observes, it does not
        # participate in turn logic or move selection.
        transcript: list = []
        turns_taken = [0]
        _orig_reset, _orig_step = game.reset, game.step

        def _reset_and_record(seed: int):
            obs = _orig_reset(seed)
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
                seed=SEED,
                sink=sink,
                max_turns=MAX_TURNS,
                session_id=f"proof-seed-{SEED}",
            )
        except GMError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

        # The crux: the game actually finished, not merely stopped.
        assert game.is_terminal(), "proof requires the game to reach a real terminal state"

        transcript_lines = transcript[:5] or ["(no narration recorded)"]

        verified = sink.verify()

        print("=" * 60)
        print("THE TABLE — end-to-end proof (bureau x GM loop x ledger)")
        print("=" * 60)
        print(f"seed:            {SEED}")
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
        print("=" * 60)

        assert verified is True, "ai-game-master's own verify_ledger.py must accept the chain"

        print("PROOF PASSED: bureau, driven through GameSession by the GM loop, "
              "is remembered in a tamper-evident ai-game-master ledger and "
              "validated by ai-game-master's own verifier.")
        return 0
    finally:
        sink.close()
        shutil.rmtree(box_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
