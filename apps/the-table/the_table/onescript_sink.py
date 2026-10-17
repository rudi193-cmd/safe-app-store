"""onescript_sink.py -- the-table's results as one-script ``verdict`` rows (J4).

SPEC W2 (box-build ``SPEC.md`` rulings R9, R10), SPEC-documented §9 J4,
SPEC-rival §2 / §8 R3-one-record.

``OneScriptSink`` has the ``LedgerSink`` duck type ``gm.run_session`` already
takes (``open_session`` / ``snapshot`` / ``close_session``, ``gm.py:95-113``),
so ``gm.py``, ``proof.py`` and every adapter are untouched. Each call becomes
one code-written ``verdict`` row through an injected ``write(row) -> dict``
(the host hands in ``onescript.table.verdict`` bound to its box; this module
never imports onescript -- the host imports it, never the reverse).

What a row carries: the session, the step, the seat index and the character
id (never a name: "The players are never written down", forge-convergence
§638), the move, the 2d6+stat ``total`` and its ``verdict`` (strong / weak /
miss), the ``last_roll`` record (seed id, counter, result, engine hash -- never
the seed itself; the ``open`` row of a forecast's session carries the beacon
round and its public randomness, W4 break 1), and the ``path`` so far. A
verdict row is code's record of what happened. It is never a seal (R10, the A5 class).

A decision beat is NOT stepped and NOT sealed here. ``decision`` writes a
``decision`` verdict row and hands the beat, with its world id, to
``propose`` (one-script's ``table.propose_beat``): a proposal the human seals
with their proof. ``apply_beat_seal`` calls ``StorySession.seal`` only after
the ``check`` the sink was built with (one-script's ``table.beat_seal``, fixed
at construction, beside ``write``) says a seal row over that proposal
re-checks AND that the sealed proposal is this beat: its path is this world's
fact path and its data this beat's fact (B2), so a seal over another beat or
another world's ``s1::b3`` moves nothing. The name check in
``StorySession.seal`` is a second gate behind that one, never the first
(SPEC-rival §3 row 7).

The ``open`` row names the world and a hash of its stat sheets
(``peaks.world_key``), and the forecast it plays for, so one-script can
refuse to take an outcome from a session on another world (S2).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .peaks import bucket, world_key
from .stream import StreamRandom

Writer = Callable[[dict], dict]
Checker = Callable[[str], dict]


class SinkRefused(RuntimeError):
    """one-script refused a row; the sink never carries on past a refusal."""


class BeatNotSealed(RuntimeError):
    """The human's seal over a decision beat's proposal does not re-check."""


def _seed_id(seed: Any) -> str | None:
    """The stream's hashed seed id. A roll row never carries the seed; a
    forecast's ``open`` row carries the beacon randomness once the round has
    fired (it is public then, and it is what one-script checks)."""
    try:
        return StreamRandom.from_seed(seed).seed_id
    except (TypeError, ValueError):
        return None


class OneScriptSink:
    """``LedgerSink`` duck type over one-script ``verdict`` rows."""

    def __init__(self, write: Writer, *, check: Checker | None = None,
                 forecast: str | None = None, game: Any = None,
                 game_name: str = "story", beacon_round: int | None = None) -> None:
        self._write = write
        # W4 break 1: the drand round the forecast awaits. The session is seeded
        # by that round's randomness, so the open row carries both (the beacon
        # is public once it fires); one-script checks them against the round.
        self.beacon_round = beacon_round
        self._check = check       # one-script's table.beat_seal, bound to the box
        self.forecast = forecast  # the wager hash this session plays for, if any
        self.game = game          # read for the beat about to be rolled, if given
        self.game_name = game_name
        self.session: str | None = None
        self.path: list[str] = []
        self.rows: list[dict] = []
        self._at: dict = {}

    # -- helpers ---------------------------------------------------------
    def _emit(self, row: dict) -> dict:
        res = self._write(row)
        if not isinstance(res, dict) or res.get("code") != 0 or "row" not in res:
            raise SinkRefused(f"one-script refused the {row.get('what')} row: "
                              f"{(res or {}).get('refused', res)!r}")
        self.rows.append(res["row"])
        return res["row"]

    def _base(self, what: str) -> dict:
        if self.session is None:
            raise RuntimeError("open_session first")
        return {"what": what, "session": self.session, "game": self.game_name}

    def _where_next(self, view: dict | None) -> None:
        """Remember the beat the NEXT step resolves (a step's view is the
        post-step one), so each roll row names the beat it rolled."""
        view = view or {}
        self._at = {"scene": view.get("scene_id"), "beat": view.get("beat_id"),
                    "character": view.get("character_id")}

    def _peek(self) -> None:
        if self.game is not None:
            try:
                self._where_next(self.game.observe(self.game.current_seat()).view)
            except (RuntimeError, ValueError, KeyError, AttributeError):
                # a game with nothing to observe: no beat named
                self._at = {}

    # -- the pinned sink surface (gm.run_session) --------------------------
    def open_session(self, session_id: str, meta: dict) -> None:
        self.session = str(session_id)
        self.path = []
        row = self._base("open")
        row.update({"seats": meta.get("seats"), "seed_id": _seed_id(meta.get("seed")),
                    "verdict": "open", "reason": f"session {self.session} opened"})
        if "roll" in meta:  # a deal-time record (Crazy Eights)
            row["roll"] = meta["roll"]
        world = getattr(self.game, "world", None)
        if isinstance(world, dict):  # S2: which world, which sheets
            row.update(world_key(world))
        if self.forecast is not None:
            row["forecast"] = self.forecast  # a row can't name a hash before it exists
        if self.beacon_round is not None:
            seed = meta.get("seed")
            if not (isinstance(seed, str) and len(seed) == 64):
                raise SinkRefused("a beacon session is seeded by the round's randomness "
                                  "(64 hex), not by another seed")
            row.update({"beacon_round": self.beacon_round, "randomness": seed.lower()})
        self._emit(row)
        self._peek()

    def snapshot(self, state: dict, note: str = "") -> None:
        roll = state.get("roll")
        at = dict(self._at)
        seat = state.get("seat")
        row = self._base("roll" if roll is not None else "step")
        row.update({
            "turn": state.get("turn"),
            "seat": seat,
            "move": list(state["move"]) if isinstance(state.get("move"), (list, tuple))
            else state.get("move"),
            "where": at.get("scene"),
            "scene": at.get("scene"),
            "beat": at.get("beat"),
            "character": at.get("character"),
        })
        if roll is not None and isinstance(roll.get("result"), int):
            total = roll["result"]
            v = bucket(total)
            self.path.append(v)
            row.update({
                "total": total, "verdict": v,
                "reason": f"2d6+{roll.get('stat_value')} = {total}: "
                f"{'10+' if v == 'strong' else '7-9' if v == 'weak' else '6-'}",
                "roll": dict(roll), "path": "-".join(self.path),
            })
        else:
            row.update({"verdict": "step", "reason": "a move with no roll"})
            if roll is not None:
                row["roll"] = dict(roll)
        self._emit(row)
        self._where_next(state.get("view"))

    def close_session(self, result: dict) -> None:
        row = self._base("result")
        row.update({"verdict": "result", "reason": result.get("summary", ""),
                    "scores": result.get("scores"), "winners": result.get("winners"),
                    "path": "-".join(self.path)})
        self._emit(row)

    # -- a model's refused move pick (R12; menu.py) ---------------------------
    def escalate(self, refusal: dict) -> dict:
        """One ``escalate`` verdict row for a pick ``menu.menu_policy`` refused
        (off the menu, ESCALATE, unreachable): the menu offered, the pick's
        path as a capped string and nothing else of what the model sent (S4),
        and what code took instead. Code's record of a refusal, so the human
        sees it; never a seal, never a move of its own. The reason is fixed
        text: no model words ride on it."""
        at = dict(self._at)
        row = self._base("escalate")
        path = refusal.get("path")
        row.update({
            "where": at.get("scene"), "scene": at.get("scene"), "beat": at.get("beat"),
            "seat": refusal.get("seat"),
            "verdict": "escalate",
            "reason": f"{refusal.get('reason')}: the model's pick was refused; "
                      f"code took {refusal.get('took')}",
            "menu": [str(m) for m in refusal.get("menu") or []],
            "pick": path if isinstance(path, str) else None,  # never `path`: the rolls' path
            "took": refusal.get("took"),
            "to": "human",
        })
        return self._emit(row)

    # -- decision beats: proposed, never sealed here -------------------------
    def decision(self, pending: dict, propose: Callable[[dict, list], dict]) -> str:
        """Write the ``decision`` verdict row that closes the path so far, then
        hand the beat to ``propose(pending, cites)`` (one-script's
        ``table.propose_beat``). Returns the proposal's subject, which only
        the human's seal makes count."""
        row = self._base("decision")
        row.update({"where": pending.get("scene_id"), "scene": pending.get("scene_id"),
                    "beat": pending.get("beat_id"), "fact_id": pending["fact_id"],
                    "verdict": "decision", "reason": "a decision beat: the human seals it",
                    "path": "-".join(self.path)})
        got = self._emit(row)
        res = propose(self._with_world(pending), [got["hash"]])
        if not isinstance(res, dict) or "subject" not in res:
            raise SinkRefused(f"the beat was not proposed: {res!r}")
        return res["subject"]

    def _with_world(self, pending: dict) -> dict:
        world = getattr(self.game, "world", None)
        if isinstance(world, dict) and world.get("id"):
            return {**pending, "world": str(world["id"])}
        return dict(pending)

    def apply_beat_seal(self, session: Any, pending: dict, subject: str) -> dict:
        """Advance past a decision beat only on a seal one-script re-checks,
        over THIS beat. The checker is the one the sink was built with; it is
        asked about ``subject`` here. Refused (``BeatNotSealed``, and
        ``pending_seal()`` stays set) unless it answers ``sealed`` and the
        sealed proposal's path is this world's path for ``pending['fact_id']``
        and its data is this beat's fact (B2). ``by`` is the verifier's name
        for a Nestor pair, else "human"; ``StorySession.seal``'s own name
        check still runs behind it."""
        if self._check is None:
            raise BeatNotSealed("this sink was built with no seal checker")
        sealed = self._check(subject)
        state = sealed.get("state") if isinstance(sealed, dict) else None
        if state != "sealed":
            why = sealed.get("why", "") if isinstance(sealed, dict) else repr(sealed)
            raise BeatNotSealed(
                f"the beat {pending.get('fact_id')!r} is not sealed by a proof that "
                f"re-checks: {state!r} {why}".strip())
        want = beat_path(self._with_world(pending))
        if sealed.get("path") != want or sealed.get("data") != pending.get("fact"):
            raise BeatNotSealed(
                f"the seal is over {sealed.get('path')!r}, not this beat ({want!r})")
        session.seal(pending["fact_id"], by=sealed.get("by") or "human")
        return sealed


def beat_path(pending: dict) -> str:
    """Where one-script writes a sealed beat: ``world/<world id>/<fact id>.md``
    (one-script's ``table.beat_path``, restated here: the-table never imports
    onescript)."""
    return f"world/{pending.get('world')}/{pending['fact_id']}.md"


def play_to_decision(session: Any, policy: Callable, sink: Any, *, seed: Any,
                     session_id: str, max_turns: int = 1000) -> dict | None:
    """``gm.run_session``'s loop and sink calls for a ``StorySession``, which
    ``run_session`` can't drive past (a decision beat has no legal move):
    reset, ``open_session``, one ``snapshot`` per step, and stop at the first
    pending seal (returned) or at terminal (``close_session``; None)."""
    session.reset(seed)
    for one in getattr(sink, "sinks", (sink,)):  # a Tee: each sink inside it
        if getattr(one, "game", False) is None:
            one.game = session  # so the first roll row names its beat
    sink.open_session(session_id, {"seed": seed, "seats": session.seats})
    last = getattr(session, "last_roll", None)
    for turn in range(max_turns):
        if session.is_terminal():
            r = session.result()
            sink.close_session({"winners": r.winners, "scores": r.scores, "summary": r.summary})
            return None
        pending = session.pending_seal()
        if pending is not None:
            return pending
        seat = session.current_seat()
        move = policy(session, seat)
        obs = session.step(seat, move)
        state = {"turn": turn, "seat": seat, "move": move, "view": obs.view}
        roll = getattr(session, "last_roll", None)
        if roll is not None and roll is not last:
            state["roll"] = roll
            last = roll
        sink.snapshot(state, note=obs.narration[0] if obs.narration else "")
    raise RuntimeError(f"max_turns ({max_turns}) reached")


def suggested_policy() -> Callable:
    """The beat's own suggested stat (peaks' 'suggested' policy)."""
    def _policy(game: Any, seat: int):
        return ("act", game.observe(seat).view["suggests"])
    return _policy


class Tee:
    """Two (or more) sinks at once: ``Tee(LedgerSink(...), OneScriptSink(...))``."""

    def __init__(self, *sinks: Any) -> None:
        self.sinks = sinks

    def open_session(self, session_id: str, meta: dict) -> None:
        for s in self.sinks:
            s.open_session(session_id, meta)

    def snapshot(self, state: dict, note: str = "") -> None:
        for s in self.sinks:
            s.snapshot(state, note=note)

    def close_session(self, result: dict) -> None:
        for s in self.sinks:
            s.close_session(result)
