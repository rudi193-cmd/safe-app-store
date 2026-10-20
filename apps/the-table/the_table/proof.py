"""proof.py — the end-to-end demonstration: EVERY registered game, each
driven by the SAME game-agnostic GM loop through the SAME uniform
GameSession protocol, each remembered as ``verdict`` rows in the one-script
record (the one chain, flatten F-1), each checked by the one-script's OWN
verifier.

Run with:
    python3 -m the_table.proof        (from apps/the-table/)
    python3 the_table/proof.py        (from apps/the-table/)

It needs the one-script beside the-table (``the_table/host.py``, flatten
F-7): with none, it says why and exits 2, never falling back to a chain of
its own.

Loops over ``registry.games()`` (today: backgammon, bureau, catgrid with its 2- and 3-cat levels and its duel, checkers, crazy_eights, hearts, liars_dice, scene). Every game is
written, one session after another, into ONE fresh throwaway box through a
``OneScriptSink``, run by ``run_session`` with a seeded (deterministic)
``random_policy``, and the proof asserts:
  * each game reached terminal (not a max_turns cap-out)
  * each session's rows are on the record: one ``open``, one per step, one
    ``result``
  * the one-script's ``verify_chain`` and ``verify_anchor`` find no break
  * a copy of the record with one row edited is refused by the same check

Prints a short human-readable section per game (transcript-ish, Result, turn
count, rows written), then the chain's check, the tamper check and one
combined line, and exits 0 only if all of it holds.

DETERMINISM NOTE (why games still run one at a time): `scene` (SceneSession,
over apps/game's engine) now draws from its own SHA-256 stream by default and
no longer reseeds the GLOBAL `random` (game_engine_adapter.py, trap 3; only
`rng_factory=LEGACY` does). `crazy_eights` keeps a private `random.Random`
and `bureau` its own xorshift. The one remaining global user is
`random_policy`'s caller-supplied `random.Random`, and a LEGACY scene's
reseed, so this loop stays conservative. It
`make()`s, runs to completion, and verifies ONE game before moving to the
next -- never two sessions alive and stepping at once.
"""
from __future__ import annotations

import random
import sys

try:
    from . import host
except ImportError:
    # Support `python3 the_table/proof.py` (run as a plain script, no
    # enclosing package) in addition to `python3 -m the_table.proof`.
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from the_table import host

# The games' randomness is the one script's (flatten F-14, F-16): with no one
# script beside, importing them stops here, and main() says why and exits 2.
try:
    from the_table import registry
    from the_table.gm import GMError, random_policy, run_session
    _UNREACHABLE = None
except host.Unreachable as _e:
    _UNREACHABLE = _e

SEED = 7  # deterministic: same seed the throwaway smoke / earlier proof used
MAX_TURNS = 2000  # generous slack over every adapter's own defensive cap


def _play_one_game(box, *, name: str, seed: int, max_turns: int) -> bool:
    """make() a fresh session for ``name``, run it end to end through
    run_session into ``box``'s record, print a short section for it, and
    return whether its rows are all there. Raises (uncaught) on anything that
    should fail the whole proof -- a capped/unterminated game, for instance,
    or a row the one-script refused.
    """
    game = registry.make(name)
    sink = box.sink(game=game, game_name=name)
    policy = random_policy(random.Random(seed))

    # Wrap reset()/step() purely to collect narration lines for the printed
    # transcript below -- run_session itself is still the only thing driving
    # the game; this wrapping observes, it does not participate in turn logic
    # or move selection.
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

    whats = [r.get("what") for r in sink.rows]
    complete = (len(sink.rows) == turns_taken[0] + 2 and whats[0] == "open"
                and whats[-1] == "result" and all(r["who"] == "table" for r in sink.rows))

    transcript_lines = transcript[:5] or ["(no narration recorded)"]
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
    print(f"verdict rows:    {len(sink.rows)} (open, {turns_taken[0]} steps, result)"
          f"{'' if complete else '  -- MISSING ROWS'}")
    print("-" * 60)
    return complete


def _tamper(rows: list) -> list:
    """Edit the first step row's reason, leaving its hash as it was."""
    out, done = [], False
    for r in rows:
        if not done and r.get("kind") == "verdict" and r.get("what") in ("step", "roll"):
            r = {**r, "reason": f"{r.get('reason', '')} (edited)"}
            done = True
        out.append(r)
    return out


def main(argv=None) -> int:
    if _UNREACHABLE is not None:
        print(f"the one-script is unreachable: {_UNREACHABLE}", file=sys.stderr)
        return host.UNREACHABLE
    names = registry.games()
    box = host.box_or_exit()
    try:
        print("=" * 60)
        print(f"THE TABLE — end-to-end proof ({len(names)} games x one GM loop x one record)")
        print(f"record: {box.record_path}")
        print("=" * 60)

        # One game at a time, start to finish -- see the determinism note in
        # the module docstring for why this loop never constructs/interleaves
        # two sessions at once.
        outcomes: dict = {}
        for name in names:
            outcomes[name] = _play_one_game(box, name=name, seed=SEED, max_turns=MAX_TURNS)

        breaks = box.verify()
        tampered = box.verify(box.tampered_copy(_tamper))
        print("=" * 60)
        for name in names:
            print(f"{name}:{' ' * max(1, 14 - len(name))}{'RECORDED' if outcomes[name] else 'FAILED'}")
        print(f"chain:        {'HOLDS' if not breaks else 'BROKEN: ' + '; '.join(breaks[:3])}")
        print(f"tampered:     {'REFUSED (' + tampered[0] + ')' if tampered else 'NOT REFUSED'}")
        all_ok = all(outcomes.values()) and not breaks and bool(tampered)
        print(f"COMBINED:     {'PASS' if all_ok else 'FAIL'}")
        print("=" * 60)
    finally:
        box.close()

    if all_ok:
        print(f"PROOF PASSED: {len(names)} games ({', '.join(names)}), driven through the SAME "
              "GameSession protocol by the SAME GM loop, are each remembered as verdict rows "
              "in the one-script record, whose own verifier holds the chain and refuses an "
              "edited copy -- the protocol is game-agnostic.")
        return 0

    print("PROOF FAILED: see FAILED game(s) and the checks above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
