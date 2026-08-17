"""``GameSession`` over apps/game's dice-resolution engine -- a freeform
narrative scene: a player declares an approach, dice resolve it, the result
is narrated. This is the third adapter (after ``bureau_adapter.py``'s
single-seat exploration and ``crazy_eights_adapter.py``'s 4-seat card game),
and the first one built expressly for the "AI Game Master" side of the-table:
no board, no hand of cards, just beats of declared action -> roll -> outcome.

the-table is the CONSUMER here, the same relationship the other two adapters
have to their sibling apps: it imports ``apps/game/engine_v1_7.py``'s
``Engine`` class, never the reverse, and never modifies anything under
``apps/game``. ``apps/game`` is not installed as a package, so the only way
to reach it is a narrow path shim -- see ``_ensure_game_engine_on_path``
below, the same one-directory-once pattern the other two adapters use for
their own sibling apps (``apps/game-lab/sims`` and ``apps/bureau``
respectively).

REUSE, NOT REIMPLEMENTATION: the only thing this module reuses from
``engine_v1_7.py`` is ``Engine.roll(stat_name)`` -- the 2d6 + stat resolution
rule and its three-way bucketing (``result >= 12`` -> ``"ARCHITECT_ROLL"``,
``result >= 7`` -> ``"SUCCESS_STANDARD"``, else ``"CHAOS_BURST"``). This
adapter does not reimplement that arithmetic; it narrates around it. The
prose itself is this module's own -- ``engine_v1_7.py`` carries no narration
of its own (its only consumer today is a Streamlit UI, ``streamlit_app.py``,
which supplies the words there; the engine module itself is pure mechanics).

THE TRAPS IN ``engine_v1_7.py`` -- and how this adapter avoids every one:

  1. ``Engine.apply_debility``, ``Engine.restore_debility``, and
     ``Engine._save_state`` all write to ``apps/game/engine_state.json`` on
     disk. Writing into another app's directory from here would be a
     data-lane violation (the-table's own SOIL lane is not
     ``apps/game``'s). This adapter NEVER calls any of those three methods,
     ever. When a beat rolls ``CHAOS_BURST``, the debility (the tiny "stat
     drops by 1, floored at -5" rule ``apply_debility`` implements) is
     applied by this adapter directly to ``engine.stats`` -- an in-memory
     dict this adapter itself constructed fresh in ``reset()`` (see trap 2)
     and that nothing in this adapter ever persists. The floor rule is
     copied here (``if stats[internal] > -5: stats[internal] -= 1``) because
     it's one line, not because ``apply_debility`` couldn't be trusted to
     compute it -- it can; it just also writes a file we must never touch.

  2. ``Engine.__init__`` calls ``_load_state()``, which READS
     ``apps/game/engine_state.json`` if present, so a bare ``Engine()``'s
     starting stats depend on whatever is sitting on disk in another app's
     directory -- not reproducible from this adapter's point of view. So
     ``reset(seed)`` constructs ``Engine()`` and immediately OVERWRITES
     ``engine.stats`` with a fresh deterministic dict, every key at
     ``Engine.BASE_STAT`` (currently 2), before any roll happens. Every
     scene therefore starts from the same stat baseline regardless of what
     ``engine_state.json`` contains, or whether it exists at all.

  3. ``Engine.roll`` draws from the GLOBAL ``random`` module
     (``random.randint``), not an owned ``random.Random`` instance -- unlike
     ``crazy_eights_adapter.py``, which deliberately owns its own generator
     precisely to avoid this. There is no way to seed *this* engine per-call
     without touching global state, so ``reset(seed)`` calls
     ``random.seed(seed)`` directly. This is a documented, deliberate
     coupling of ``engine_v1_7.py`` itself (not a design choice made here):
     determinism for a ``SceneSession`` requires (a) seeding the global RNG
     in ``reset()`` and (b) running single-threaded / not interleaving two
     scenes' rolls on the same process without reseeding between them. A
     caller that needs two independent deterministic scenes in one process
     must call ``reset(seed)`` on each immediately before driving it, not
     construct both up front and alternate steps between them.

  4. Importing ``engine_v1_7`` is side-effect-free: the module top level only
     defines constants and the ``Engine`` class body -- no code runs at
     import time. Constructing ``Engine()`` only *reads* (via
     ``_load_state``); nothing is written to disk until ``_save_state`` is
     explicitly called, which this adapter never does. A full scene --
     ``reset`` through a terminal ``step`` -- therefore leaves
     ``apps/game/engine_state.json`` completely untouched (see
     ``tests/test_game_engine_adapter.py``'s
     ``TestGameEngineStateFileUntouched``, which snapshots the file's
     existence/mtime/bytes before a scene and asserts byte-identity, or
     continued absence, after).

STAT NAMING: the engine's public rolling surface takes the four *approach*
names -- Grit, Weird, Cute, Cool -- and maps them internally to the four
*stat* names its state dict actually stores under -- Integrity, Synthesis,
Trust, Efficiency (see ``engine_v1_7.py``'s own ``stat_map`` inside
``roll``/``apply_debility``/``restore_debility``). That mapping is a private
implementation detail inside those methods, not exposed as an importable
constant, so ``_STAT_MAP`` below intentionally duplicates it (four short
string pairs) so this adapter can present approaches by their public names
in ``legal_moves()`` and ``observe()`` while still writing to the correct
key of ``engine.stats`` when applying a debility.

SOFT WINNER HEURISTIC: a freeform scene isn't strictly win/lose the way a
card game or an exploration discrepancy is. ``result()`` carries a
``scores={0: successes}`` tally (successes = ``ARCHITECT_ROLL`` +
``SUCCESS_STANDARD`` beats) and reports ``winners=[0]`` iff
``successes >= chaos_bursts`` -- a documented, deliberately SOFT "did the
scene go well" read, not a hard win condition. A scene with more chaos than
success still produces a complete, valid ``Result``; it just reads as
``winners=[]``, the same "no winner" shape ``crazy_eights_adapter.py`` uses
for a stalled hand.

Turn model (seats = 1, pinned):
  * A scene is a fixed number of beats, set at construction time
    (``SceneSession(beats=6)``, default 6).
  * ``current_seat()`` is always ``0`` until the scene is terminal.
  * ``legal_moves(0)`` (side-effect-free, the SAME four moves every beat,
    computed with no reference to mutable state): the four approaches,
    ``[("act", "Grit"), ("act", "Weird"), ("act", "Cute"), ("act", "Cool")]``.
  * ``step(0, ("act", stat))``: calls ``engine.roll(stat)`` (reading this
    adapter's own freshly-seeded ``engine.stats``), narrates a line keyed to
    the returned status, applies the debility floor rule in-adapter on
    ``CHAOS_BURST`` (trap 1 above), advances the beat counter, and marks the
    scene terminal once ``beats`` beats have been played.
  * Terminal: ``beat_count >= beats``. There is no early termination --
    every scene runs its full fixed length.
  * ``result()``: see SOFT WINNER HEURISTIC above.

Move vocabulary (JSON-serializable tuples, per the pinned contract):
  ("act", "Grit")
  ("act", "Weird")
  ("act", "Cute")
  ("act", "Cool")

Hidden information: none. This is a single-seat scene with no opponent and
nothing to conceal, so ``observe(0)``'s view is simply the full, current,
JSON-serializable machine state: beat progress, all four stat values (by
approach name), the last roll's result and status, the running per-status
tally, and the debility count.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

# Approach name (public, used in moves/views) -> engine's internal stat key
# (the dict key ``engine.stats`` is actually keyed by). Deliberately
# duplicates the private ``stat_map`` inside ``engine_v1_7.py``'s
# ``Engine.roll``/``apply_debility``/``restore_debility`` -- see the STAT
# NAMING section of the module docstring for why.
_STAT_MAP = {"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}

_DEBILITY_FLOOR = -5  # mirrors Engine.apply_debility's own floor, applied in-adapter (trap 1)


def _ensure_game_engine_on_path() -> None:
    """Put apps/game on sys.path so ``from engine_v1_7 import Engine`` works,
    without installing apps/game as a package and without touching anything
    under apps/game itself.

    Resolved relative to this file:
    apps/the-table/the_table/game_engine_adapter.py -> repo root is three
    parents up -> apps/game is the sibling directory holding the module.
    """
    repo_root = Path(__file__).resolve().parents[3]
    game_dir = repo_root / "apps" / "game"
    game_str = str(game_dir)
    if game_str not in sys.path:
        sys.path.insert(0, game_str)


_ensure_game_engine_on_path()

from engine_v1_7 import Engine  # noqa: E402  (import after path shim, on purpose)

from .game_session import Observation, Result

_MOVES = tuple(("act", stat) for stat in _STAT_MAP)  # fixed, side-effect-free every beat


class SceneSession:
    """``GameSession`` adapter over apps/game's ``Engine.roll`` dice rule."""

    seats = 1

    def __init__(self, beats: int = 6) -> None:
        self.beats = beats
        self._engine: Engine | None = None
        self._beat = 0
        self._tally = {"ARCHITECT_ROLL": 0, "SUCCESS_STANDARD": 0, "CHAOS_BURST": 0}
        self._last_result: int | None = None
        self._last_status: str | None = None
        self._debility_count = 0
        self._terminal = False

    # -- GameSession -----------------------------------------------------

    def reset(self, seed: int) -> Observation:
        # Trap 3: Engine.roll draws from the GLOBAL random module -- seed it
        # here so a scene is reproducible from this call forward.
        random.seed(seed)

        # Trap 2: Engine() reads apps/game/engine_state.json via
        # _load_state(); overwrite immediately with a fresh, deterministic
        # baseline so this scene never depends on that file's contents.
        engine = Engine()
        # NOTE: BASE_STAT is a module-level constant in engine_v1_7.py, only
        # exposed as an *instance* attribute (Engine.__init__ sets
        # self.BASE_STAT = BASE_STAT) -- there is no Engine.BASE_STAT class
        # attribute, so read it off the instance we just constructed.
        engine.stats = {internal: engine.BASE_STAT for internal in _STAT_MAP.values()}
        self._engine = engine

        self._beat = 0
        self._tally = {"ARCHITECT_ROLL": 0, "SUCCESS_STANDARD": 0, "CHAOS_BURST": 0}
        self._last_result = None
        self._last_status = None
        self._debility_count = 0
        self._terminal = False

        narration = [
            f"A new scene opens (seed={seed}), {self.beats} beats to play out. "
            f"Declare an approach each beat -- Grit, Weird, Cute, or Cool -- and the dice answer.",
        ]
        return Observation(seat=0, view=self._view(), narration=narration, terminal=False)

    def current_seat(self) -> int:
        self._require_reset()
        return 0

    def observe(self, seat: int) -> Observation:
        self._require_reset()
        self._require_seat(seat)
        return Observation(seat=0, view=self._view(), narration=[], terminal=self._terminal)

    def legal_moves(self, seat: int) -> list:
        """Side-effect-free: the same four approaches every beat, regardless
        of state, until the scene is terminal."""
        self._require_reset()
        self._require_seat(seat)
        if self._terminal:
            return []
        return list(_MOVES)

    def step(self, seat: int, move) -> Observation:
        self._require_reset()
        self._require_seat(seat)
        if self._terminal:
            raise RuntimeError("step() called on a terminal scene")

        if not (isinstance(move, (tuple, list)) and len(move) == 2 and move[0] == "act"
                and move[1] in _STAT_MAP):
            raise ValueError(
                f"unknown move {move!r}; legal moves are "
                f"('act', <'Grit'|'Weird'|'Cute'|'Cool'>)"
            )
        stat = move[1]

        # THE reused rule -- 2d6 + stat, bucketed -- nothing about this
        # arithmetic is reimplemented here.
        result, status = self._engine.roll(stat)
        self._last_result = result
        self._last_status = status
        self._tally[status] += 1

        narration = [self._narrate(stat, result, status)]

        if status == "CHAOS_BURST":
            # Trap 1: apply the debility ourselves, in-adapter, on our own
            # engine.stats dict -- NEVER via Engine.apply_debility (which
            # would _save_state() into apps/game/engine_state.json).
            internal = _STAT_MAP[stat]
            if self._engine.stats[internal] > _DEBILITY_FLOOR:
                self._engine.stats[internal] -= 1
                self._debility_count += 1
                narration.append(
                    f"{stat} takes a hit -- now {self._engine.stats[internal]}."
                )

        self._beat += 1
        if self._beat >= self.beats:
            self._terminal = True
            narration.append(f"The scene closes after {self.beats} beats.")

        return Observation(seat=0, view=self._view(), narration=narration, terminal=self._terminal)

    def is_terminal(self) -> bool:
        self._require_reset()
        return self._terminal

    def result(self) -> Result:
        self._require_reset()
        successes = self._tally["ARCHITECT_ROLL"] + self._tally["SUCCESS_STANDARD"]
        chaos = self._tally["CHAOS_BURST"]
        # Soft heuristic, documented in the module docstring: "did the scene
        # go well", not a hard win condition. A scene with more chaos than
        # success is still a complete, valid Result -- it just has no winner.
        winners = [0] if successes >= chaos else []
        summary = (
            f"{self.beats}-beat scene complete: {successes} successes "
            f"({self._tally['ARCHITECT_ROLL']} architect-roll, "
            f"{self._tally['SUCCESS_STANDARD']} standard), {chaos} chaos burst(s), "
            f"{self._debility_count} debilit{'y' if self._debility_count == 1 else 'ies'} taken. "
            f"Ending stats: {self._display_stats()}."
        )
        return Result(winners=winners, scores={0: successes}, summary=summary)

    # -- internal ----------------------------------------------------------

    def _narrate(self, stat: str, result: int, status: str) -> str:
        if status == "ARCHITECT_ROLL":
            return f"Leaning on {stat} ({result}) -- an architect-level roll. It goes better than planned."
        if status == "SUCCESS_STANDARD":
            return f"Leaning on {stat} ({result}) -- a solid success. It works."
        return f"Leaning on {stat} ({result}) -- a chaos burst. It goes sideways."

    def _display_stats(self) -> dict:
        """Current stats, keyed by their public approach name (Grit/Weird/
        Cute/Cool), not the engine's internal key."""
        return {approach: self._engine.stats[internal] for approach, internal in _STAT_MAP.items()}

    def _view(self) -> dict:
        return {
            "beat": self._beat,
            "beats_total": self.beats,
            "stats": self._display_stats(),
            "last_result": self._last_result,
            "last_status": self._last_status,
            "tally": dict(self._tally),
            "debilities": self._debility_count,
        }

    def _require_reset(self) -> None:
        if self._engine is None:
            raise RuntimeError("reset(seed) must be called before use")

    def _require_seat(self, seat: int) -> None:
        if seat != 0:
            raise ValueError(f"a narrative scene is single-seat; seat must be 0, got {seat!r}")
