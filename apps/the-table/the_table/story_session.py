"""story_session.py -- StorySession: the story side of the-table.

``StorySession`` plays an authored world (``worlds.py``) through the SAME
``GameSession`` spine ``SceneSession``/``BureauSession``/``CrazyEightsSession``
already implement -- the-table's driver (``gm.py``) and ledger
(``ledger_sink.py``) run it unchanged, no new plumbing. It is the FOURTH
adapter, and the first one that isn't a fixed-length freeform scene or a
board/card game: a world is a script -- an ordered list of scenes, each an
ordered list of beats -- and playing it means walking that script.

THE ONE NEW MECHANIC, and the whole point of this module: a beat can be a
**decision** -- the machine PROPOSES a fact (``beat["proposes"]``) -- and a
decision beat is not resolved by rolling dice or picking an approach. It is
resolved only by ``seal(fact_id, by, ...)``, and ``seal()`` REFUSES unless
``by`` is a real, named human (checked against ``NOT_A_PERSON`` below). There
is no other path through a decision beat:

  * ``legal_moves(seat)`` on a decision beat is ``[]`` -- no move exists for
    a policy (random, greedy, or an LLM) to pick that would advance it.
  * ``step(seat, move)`` on a decision beat RAISES -- there is nothing to
    step; a decision beat is not a move-and-roll beat.
  * The ONLY code path that advances a decision beat is ``seal()``, and
    ``seal()`` is the ONLY method in this module that mutates past one.

So "the machine may PROPOSE, but it HALTS until a named human SEALS it" is
not a policy this module *asks* callers to respect -- it is structural: there
is no move in the vocabulary that does it, the same way ``registry.py``'s own
philosophy makes "run every game the same way" structural rather than a
convention every caller has to remember.

REUSE, NOT REIMPLEMENTATION -- the dice: this module reuses
``apps/game``'s ``Engine.roll(stat_name)`` for the *arithmetic* of an action
beat (2d6 + stat) the same way ``game_engine_adapter.py``'s ``SceneSession``
does, and avoids every trap that module's docstring documents:
  * never call ``apply_debility``/``restore_debility``/``_save_state`` (all
    three write ``apps/game/engine_state.json`` -- a different app's data
    lane);
  * ``engine.stats`` is overridden fresh from THIS module's own per-seat
    character sheet before every roll, never read from
    ``engine_state.json``;
  * the global ``random`` module is seeded once, in ``reset(seed)``
    (``Engine.roll`` draws from it directly, not an owned generator -- see
    ``game_engine_adapter.py``'s trap #3 for why this is a documented
    coupling of ``engine_v1_7.py`` itself, not a choice made here).
The sys.path shim that makes ``apps/game`` importable
(``_ensure_game_engine_on_path``) is reused directly from
``game_engine_adapter.py`` rather than duplicated -- one shim, one place.

WHAT IS *NOT* REUSED, ON PURPOSE -- the bucketing: ``Engine.roll`` returns
its own status (``ARCHITECT_ROLL`` >=12 / ``SUCCESS_STANDARD`` >=7 /
``CHAOS_BURST`` <7), tuned for ``SceneSession``'s narration. The design this
module implements calls for a different, PbtA-style three-way read of the
SAME raw ``2d6 + stat`` sum: **strong (10+) / weak (7-9) / miss (6-)** --
see the pinned contract's beat ``outcomes`` shape (``strong``/``weak``/
``miss`` keys, not architect/standard/chaos). So this module reuses
``Engine.roll`` for the dice arithmetic (never reimplementing 2d6 addition
or drawing its own random numbers) and applies its OWN bucket boundaries to
the result it gets back, rather than reusing ``Engine.roll``'s status
string. Nothing about ``2d6 + stat`` is reimplemented; only the *narrative
reading* of the sum differs, because the two adapters narrate two different
games.

STAT NAMING: mirrors ``game_engine_adapter.py``'s own duplicated
``_STAT_MAP`` for the same reason that module gives (``engine_v1_7.py``'s
mapping is private, embedded inside ``Engine.roll`` itself, not an
importable constant). Generalized here: a world using the canonical four
approach names (Grit/Weird/Cute/Cool, as ``worlds/hasbeen.json`` does)
resolves through the map to the engine's internal keys exactly the way
``SceneSession`` does; a world using ANY other stat names passes through
unchanged, because ``Engine.roll``'s own internal ``stat_map.get(name,
name)`` already falls back to the raw name for anything it doesn't
recognize. Nothing here hardcodes Hasbeen -- see ``worlds.py``.

TURN MODEL: a world may seat more than one character (unlike the three
existing single/four-seat adapters, seat count is WORLD-DEFINED --
``seats = len([c for c in characters if c["seat"]])``). ``current_seat()``
rotates simply, one seat per completed beat: ``turn_count % seats``. Every
completed beat -- whether an action beat resolved by ``step()`` or a
decision beat resolved by ``seal()`` -- advances the turn counter and the
scene/beat pointer identically (see ``_advance()``), so seat rotation does
not depend on which kind of beat just resolved.

THE PLAYERS ARE NEVER RECORDED: this module keeps a scored-beat tally and a
record of SEALED FACTS (fact_id, who sealed it, verdict, reason) for
``result()`` -- never attendance, never a per-person log of who played which
seat or made which roll. Persisting a sealed fact anywhere durable (a vault,
a timeline) is later work, out of scope here -- ``seal()`` only records into
this session's own in-memory state, which is discarded when the session is.

Turn model, mechanically:
  * ``reset(seed)`` seeds the global RNG, positions at scene 0 / beat 0,
    builds one stat sheet per seated character (world's ``base_stat`` fills
    in any stat a character's own ``stats`` dict omits).
  * ``legal_moves(seat)`` on an action beat: ``[("act", stat), ...]`` for
    every stat the world defines (order preserved from ``world["stats"]``),
    the same for every seat -- ``step()`` (not ``legal_moves()``) is what
    enforces turn order, matching ``crazy_eights_adapter.py``'s own split
    between "what could this seat play" and "is it this seat's turn".
    On a decision beat: ``[]``, for every seat, always.
  * ``step(seat, move)``: only legal on an action beat, and only for
    ``current_seat()``. Rolls ``("act", stat)`` via ``Engine.roll``,
    buckets strong/weak/miss, narrates from the beat's own ``outcomes``,
    tallies the bucket, advances to the next beat (and next scene, narrating
    its ``opening`` lines, if the scene's beats are exhausted).
  * ``pending_seal()`` / ``seal(...)``: see the module-level docstring above
    -- the one new mechanic.
  * Terminal: every scene's every beat has been resolved (stepped or
    sealed). An unsealed decision beat blocks; it is never terminal.
  * ``result()``: ``winners=[]`` always (a story isn't won); ``scores`` is
    the strong/weak/miss tally; ``summary`` reports the tally, every sealed
    decision and who sealed it, and a short closing read.

Move vocabulary (JSON-serializable tuples, per the pinned contract):
  ("act", <any of world["stats"]>)

Hidden information: none by design at this size -- ``observe(seat)`` returns
only ``seat``'s own character/stats plus the shared, public scene/beat state
(current scene id/title, current beat's prompt, and ``pending_seal()``,
which is about the WORLD's canon, not any seat's private data). No other
seat's stats or identity appear in a given seat's view.
"""
from __future__ import annotations

import random
import re
from typing import Any, Optional

from .game_engine_adapter import _ensure_game_engine_on_path
from .game_session import Observation, Result
from .worlds import load_world

_ensure_game_engine_on_path()

from engine_v1_7 import Engine  # noqa: E402  (import after path shim, on purpose)

# Duplicates engine_v1_7.py's own private stat_map (see the STAT NAMING
# section of the module docstring above for why this is a deliberate
# duplication, not an oversight -- game_engine_adapter.py duplicates the
# identical four pairs for the identical reason).
_ENGINE_STAT_MAP = {"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}

# Mirrors apps/ai-game-master/bootstrap/verify_ledger.py's NOT_A_PERSON
# constant EXACTLY (that file's own header notes it is itself pattern-ported
# from terpsi-music's records/sealing.py _NOT_A_PERSON -- this is one more
# link in the same chain, duplicated rather than imported because
# apps/ai-game-master is off-limits to import from here per this module's
# scope: the-table is not wired to the vault yet, only mirroring its
# covenant). ``_is_not_a_person()`` below compares this set
# case-insensitively and whitespace-stripped, the same way verify_canon() in
# that file compares ``sealed_by`` -- and additionally tokenizes ``by`` on
# non-alphanumeric runs so a compound machine-looking id (``the-machine``,
# ``claude-agent``) is caught too, not just an exact match against one of
# these bare words.
NOT_A_PERSON = {
    "", "system", "machine", "ai", "gm", "dm-bot", "assistant",
    "claude", "model", "auto", "none", "null",
}

_BUCKETS = ("strong", "weak", "miss")


def _is_not_a_person(by: str) -> bool:
    """True if ``by`` is empty, or IS (or contains, as a whole token) a
    ``NOT_A_PERSON`` name -- refusing not just an exact machine id but the
    compounds a machine-generated signer name tends to take (``the-machine``,
    ``ai-bot``, ``claude-agent``). Case-insensitive, whitespace-stripped,
    tokenized on runs of non-alphanumeric characters (``-``, ``_``, spaces)
    the same way a signer id would naturally be word-split. A real person's
    name is vanishingly unlikely to collide with one of these short,
    deliberately machine-flavored tokens; a person named exactly one of them
    is refused here too and must sign under a fuller name -- the fleet
    covenant this mirrors treats that as the correct, conservative default,
    not a false positive worth relaxing the check for."""
    who = (by or "").strip().lower()
    if who in NOT_A_PERSON:
        return True
    tokens = [t for t in re.split(r"[^a-z0-9]+", who) if t]
    return any(t in NOT_A_PERSON for t in tokens)


class StorySession:
    """``GameSession`` over an authored world, plus the propose/seal seam."""

    def __init__(self, world_path) -> None:
        self.world = load_world(world_path)
        self._seated = [c for c in self.world["characters"] if c["seat"]]
        self.seats: int = len(self._seated)

        self._engine: Optional[Engine] = None
        self._seat_stats: list = []
        self._scene_idx = 0
        self._beat_idx = 0
        self._turn = 0
        self._tally = {b: 0 for b in _BUCKETS}
        self._seals: dict = {}
        self._seal_order: list = []
        self._terminal = False

    # -- GameSession -------------------------------------------------------

    def reset(self, seed: int) -> Observation:
        # Trap 3 (game_engine_adapter.py): Engine.roll draws from the GLOBAL
        # random module -- seed it here so a story is reproducible from this
        # call forward.
        random.seed(seed)

        # Trap 2: Engine() reads apps/game/engine_state.json via
        # _load_state(); this module never reads that dict -- engine.stats
        # is overwritten fresh from our own per-seat sheet before every roll
        # (see step()) -- so what Engine() happens to load here is inert.
        self._engine = Engine()

        self._seat_stats = [
            {stat: char["stats"].get(stat, self.world["base_stat"]) for stat in self.world["stats"]}
            for char in self._seated
        ]
        self._scene_idx = 0
        self._beat_idx = 0
        self._turn = 0
        self._tally = {b: 0 for b in _BUCKETS}
        self._seals = {}
        self._seal_order = []
        self._terminal = False

        scene = self._current_scene()
        narration = [f"{self.world['title']} begins (seed={seed}).", self.world["setting"]]
        narration.extend(scene["opening"])

        seat = self.current_seat()
        return Observation(seat=seat, view=self._view(seat), narration=narration, terminal=False)

    def current_seat(self) -> int:
        self._require_reset()
        return self._turn % self.seats

    def observe(self, seat: int) -> Observation:
        self._require_reset()
        self._require_seat(seat)
        return Observation(seat=seat, view=self._view(seat), narration=[], terminal=self._terminal)

    def legal_moves(self, seat: int) -> list:
        """Side-effect-free. The four (or however many the world defines)
        approaches on an action beat, for every seat alike -- ``step()`` is
        what enforces whose turn it is, matching
        ``crazy_eights_adapter.py``'s own split. ``[]`` on a decision beat,
        for every seat, always: no move exists that advances one."""
        self._require_reset()
        self._require_seat(seat)
        if self._terminal:
            return []
        if self._current_beat()["kind"] == "decision":
            return []
        return [("act", stat) for stat in self.world["stats"]]

    def step(self, seat: int, move: Any) -> Observation:
        self._require_reset()
        self._require_seat(seat)
        if self._terminal:
            raise RuntimeError("step() called on a terminal story")
        if seat != self.current_seat():
            raise ValueError(f"it is seat {self.current_seat()}'s turn, not {seat!r}")

        beat = self._current_beat()
        if beat["kind"] == "decision":
            raise RuntimeError(
                f"step() called on a decision beat ({beat['id']!r}) -- nothing to "
                f"step; only seal(fact_id, by=<a named human>) can advance past it"
            )

        if not (isinstance(move, (tuple, list)) and len(move) == 2 and move[0] == "act"
                and move[1] in self.world["stats"]):
            raise ValueError(
                f"unknown move {move!r}; legal moves on this beat are "
                f"{self.legal_moves(seat)!r}"
            )
        stat = move[1]

        # THE reused rule -- 2d6 + stat, via Engine.roll -- nothing about
        # this arithmetic is reimplemented here. engine.stats is overridden
        # fresh from the acting seat's own sheet immediately before the
        # roll; apply_debility/restore_debility/_save_state are never
        # called (see module docstring).
        self._engine.stats = {
            _ENGINE_STAT_MAP.get(s, s): value for s, value in self._seat_stats[seat].items()
        }
        result, _engine_status = self._engine.roll(stat)

        # StorySession's OWN strong/weak/miss read of the raw sum -- see the
        # module docstring's "WHAT IS NOT REUSED, ON PURPOSE" section for
        # why this differs from Engine.roll's own status string.
        if result >= 10:
            bucket = "strong"
        elif result >= 7:
            bucket = "weak"
        else:
            bucket = "miss"
        self._tally[bucket] += 1

        narration = [beat["outcomes"][bucket]]
        self._advance(narration)

        new_seat = self.current_seat()
        return Observation(seat=new_seat, view=self._view(new_seat), narration=narration,
                            terminal=self._terminal)

    def is_terminal(self) -> bool:
        self._require_reset()
        return self._terminal

    def result(self) -> Result:
        self._require_reset()
        total = sum(self._tally.values())
        scores = dict(self._tally)

        sealed_lines = [
            f"{fact_id} {self._seals[fact_id]['verdict']} by {self._seals[fact_id]['by']}"
            for fact_id in self._seal_order
        ]
        sealed_summary = "; ".join(sealed_lines) if sealed_lines else "none"

        if total == 0:
            verdict = "The story never got underway."
        elif self._tally["strong"] >= self._tally["miss"]:
            verdict = "The night held together."
        else:
            verdict = "The night went sideways."

        summary = (
            f"{self.world['title']}: {total} beat(s) resolved "
            f"({self._tally['strong']} strong, {self._tally['weak']} weak, "
            f"{self._tally['miss']} miss); {len(self._seal_order)} decision(s) sealed "
            f"[{sealed_summary}]. {verdict}"
        )
        return Result(winners=[], scores=scores, summary=summary)

    # -- the one new mechanic: propose -> seal ------------------------------

    def pending_seal(self) -> Optional[dict]:
        """The current beat's proposed fact, if it is an unsealed decision
        beat -- else ``None``. This is the ONLY thing that tells a caller a
        decision is blocking play; ``is_terminal()`` stays ``False`` the
        whole time (blocked, not terminal)."""
        self._require_reset()
        if self._terminal:
            return None
        beat = self._current_beat()
        if beat["kind"] != "decision":
            return None
        scene = self._current_scene()
        fact_id = self._fact_id(scene, beat)
        if fact_id in self._seals:
            return None  # already sealed; _advance() should have moved past it
        return {
            "fact_id": fact_id,
            "fact": beat["proposes"]["fact"],
            "proposed_by": beat["proposes"]["proposed_by"],
            "scene_id": scene["id"],
            "beat_id": beat["id"],
            "prompt": beat["prompt"],
        }

    def seal(self, fact_id: str, by: str, verdict: str = "SEALED", reason: str = "") -> None:
        """The ONLY way past a decision beat. Refuses unless ``by`` is a
        real, named human -- no code path in this module may auto-seal.

        Raises ``ValueError`` if ``verdict`` is not ``SEALED``/``REJECTED``,
        or if ``by`` is empty or matches ``NOT_A_PERSON`` (case-insensitive,
        stripped) -- checked BEFORE looking at story state, so an invalid
        human is refused unconditionally, not only when a fact happens to be
        pending. Raises ``RuntimeError`` if no decision is currently
        pending, and ``ValueError`` if ``fact_id`` does not match the one
        currently pending (this module tracks exactly one pending fact at a
        time -- the current beat's). On a valid seal (accept OR reject),
        records it and advances past the decision beat -- a human decided,
        either way, and that is what unblocks play.
        """
        self._require_reset()

        if verdict not in ("SEALED", "REJECTED"):
            raise ValueError(f"verdict must be 'SEALED' or 'REJECTED', got {verdict!r}")

        who = (by or "").strip()
        if _is_not_a_person(who):
            raise ValueError(
                f"seal() refused: {by!r} is not a named human (matches, or is a "
                f"compound of, the not-a-person set {sorted(NOT_A_PERSON)!r}) -- "
                f"only a person may seal a fact"
            )

        pending = self.pending_seal()
        if pending is None:
            raise RuntimeError("seal() called but no decision beat is currently pending")
        if fact_id != pending["fact_id"]:
            raise ValueError(
                f"fact_id {fact_id!r} does not match the currently pending fact "
                f"{pending['fact_id']!r}"
            )

        self._seals[fact_id] = {"fact_id": fact_id, "by": who, "verdict": verdict, "reason": reason}
        self._seal_order.append(fact_id)
        self._advance([])

    # -- internal ------------------------------------------------------------

    def _current_scene(self) -> dict:
        return self.world["scenes"][self._scene_idx]

    def _current_beat(self) -> dict:
        return self._current_scene()["beats"][self._beat_idx]

    def _fact_id(self, scene: dict, beat: dict) -> str:
        return f"{scene['id']}::{beat['id']}"

    def _advance(self, narration: list) -> None:
        """Move the scene/beat pointer to the next beat (and the next
        scene, narrating its ``opening``, if the current scene's beats are
        exhausted), and mark terminal once every scene's every beat is
        played. Shared by ``step()`` (an action beat resolved) and
        ``seal()`` (a decision beat resolved) -- turn rotation and scene
        advancement work identically regardless of which kind of beat just
        resolved."""
        self._turn += 1
        self._beat_idx += 1
        scene = self.world["scenes"][self._scene_idx]
        if self._beat_idx >= len(scene["beats"]):
            self._scene_idx += 1
            self._beat_idx = 0
            if self._scene_idx >= len(self.world["scenes"]):
                self._terminal = True
            else:
                new_scene = self.world["scenes"][self._scene_idx]
                narration.append(f"-- {new_scene['title']} --")
                narration.extend(new_scene["opening"])

    def _view(self, seat: int) -> dict:
        character = self._seated[seat]
        view: dict = {
            "seat": seat,
            "character_id": character["id"],
            "character_name": character["name"],
            "stats": dict(self._seat_stats[seat]),
            "pending_seal": self.pending_seal(),
        }
        if self._terminal:
            view.update({
                "scene_id": None, "scene_title": None,
                "beat_id": None, "beat_kind": None,
                "prompt": None, "suggests": None,
            })
            return view
        scene = self._current_scene()
        beat = self._current_beat()
        view.update({
            "scene_id": scene["id"],
            "scene_title": scene["title"],
            "beat_id": beat["id"],
            "beat_kind": beat["kind"],
            "prompt": beat["prompt"],
            "suggests": beat.get("suggests"),
        })
        return view

    def _require_reset(self) -> None:
        if self._engine is None:
            raise RuntimeError("reset(seed) must be called before use")

    def _require_seat(self, seat: int) -> None:
        if not isinstance(seat, int) or isinstance(seat, bool) or not (0 <= seat < self.seats):
            raise ValueError(
                f"this story has {self.seats} seat(s); seat must be 0..{self.seats - 1}, got {seat!r}"
            )
