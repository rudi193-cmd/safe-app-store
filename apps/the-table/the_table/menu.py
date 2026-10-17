"""menu.py -- the closed menu: the one way a model picks a move (box-build R12, R22).

SPEC rulings R12 (the act) and R22 (the model picks only on a ``set_piece``
beat; every other beat takes the beat's own suggested stat in code),
SPEC-rival §8 R5-the-act, SPEC-documented §13 J7 and its conflicts C14 (a
decision beat is never on the menu) and C15 (``set_piece`` is a beat
marker). Adversarial: rival T12; W3b audit N1, N5, S4, S5, idea-side row 33.

What a model may do here is exactly one thing: pick a move **id** from the
menu code hands it, through ratatosk's one-tool contract --
``propose(path=<move id>)`` (``ratatosk_choose``) -- or, in tests, through an
injected ``choose``. Code turns ``legal_moves(seat)`` into ids (``move_ids``:
``act:Grit``), hands the list over, and accepts the answer only if it is
exactly one of those ids (``move_of``: a str, compared whole; no case fold,
no strip, no lookalike). Everything else is refused and the game goes on by
code:

    refused as     when
    off_menu       anything that is not a listed id: an unlisted id
                   (``act:Fly``), a bare stat, an index, a list or tuple, a
                   propose row whose path is not listed
    escalate       the model proposed ``ESCALATE``: it goes to the human
    unreachable    ``choose`` raised, or returned nothing (None)

On any refusal code picks (``code_pick``: the beat's own suggested stat when
the view names one and it is legal, else the first legal move -- computed
from the legal list code read BEFORE the model was asked, so a chooser that
mutates the game cannot widen it), the roll still happens in code (the D0 is
``GameSession.step``), and the refusal is recorded: on the policy's own
``refusals`` list and, when a sink with ``escalate`` is given, as one
``escalate`` verdict row. The record keeps only the pick's ``path`` as a
string, capped at ``PATH_CAP`` characters (S4): a claim, extra fields, a
nested row never ride into the record. A refusal never raises (N5).

A decision beat never reaches ``choose``: ``StorySession.legal_moves`` is
``[]`` there and ``onescript_sink.play_to_decision`` stops before asking a
policy, so the only path past it is the human's seal (R10). This module
raises if it is ever asked for a move with no legal move, rather than guess.

R22: by default (``set_piece_only=True``) the model is asked only on a beat
whose view says ``set_piece``; every other beat is ``code_pick``. The
documented reading (SPEC-documented §13) returned an index; R12 makes it an
id through ``propose(path=...)``, and an index is off the menu.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .gm import Policy

ESCALATE = "ESCALATE"  # ratatosk/onescript.py: the reserved propose path
OFF_MENU, ESCALATED, UNREACHABLE = "off_menu", "escalate", "unreachable"
TO_HUMAN = "human"
PATH_CAP = 120


def move_id(move: Any) -> str:
    """The menu id of a move: ``("act", "Grit")`` -> ``act:Grit``. A move
    that is not a tuple/list of strings reads as its ``str``."""
    if isinstance(move, (tuple, list)) and all(isinstance(x, str) for x in move):
        return ":".join(move)
    return str(move)


def move_ids(legal: Sequence[Any]) -> list[str]:
    """The closed menu, in ``legal_moves`` order."""
    return [move_id(m) for m in legal]


def move_of(path: Any, legal: Sequence[Any]) -> Any | None:
    """The legal move whose id is exactly ``path`` (a str, whole), else
    ``None``. An int, a tuple, a stat name alone, a near-miss: not an id."""
    if not isinstance(path, str):
        return None
    for m in legal:
        if move_id(m) == path:
            return m
    return None


def read_pick(got: Any) -> tuple[str | None, str]:
    """``(path, reason)`` from what ``choose`` returned: a str id, or a
    propose row ``{"path": <str>, ...}`` (ratatosk's contract) -> its path.
    ``None`` (nothing came back) is ``unreachable``; any other shape (an
    int, a list, a tuple, bytes, a row with a non-string path) is
    ``off_menu`` (N1)."""
    if got is None:
        return None, UNREACHABLE
    if isinstance(got, str):
        return got, ""
    if isinstance(got, dict) and isinstance(got.get("path"), str):
        return got["path"], ""
    return None, OFF_MENU


def path_text(got: Any) -> str | None:
    """What the record keeps of a pick: its path as a string, capped (S4).
    Nothing else of what a model sent is written anywhere."""
    if got is None:
        return None
    path = got if isinstance(got, str) else got.get("path") if isinstance(got, dict) else got
    if not isinstance(path, str):
        return type(path).__name__
    path = "".join(c if c.isprintable() else "?" for c in path)
    return path if len(path) <= PATH_CAP else path[: PATH_CAP - 1] + "…"


def code_pick(game: Any, seat: int, legal: Sequence[Any]) -> Any:
    """Code's own move on a beat: the beat's suggested stat when the view
    names one and it is legal (``suggested_policy``), else the first legal
    move. Reads only ``legal`` as handed in, never ``legal_moves`` again."""
    try:
        want = game.observe(seat).view.get("suggests")
    except Exception:  # noqa: BLE001 - a game with no view suggests nothing
        want = None
    if isinstance(want, str):
        found = move_of(f"act:{want}", legal)
        if found is not None:
            return found
    return legal[0]


def menu_policy(
    choose: Callable[[list[str]], Any],
    *,
    fallback: Callable[[Any, int, Sequence[Any]], Any] | None = None,
    sink: Any = None,
    set_piece_only: bool = True,
) -> Policy:
    """A ``Policy`` whose only model act is ``choose(menu) -> move id``.

    ``choose`` is injected: ``ratatosk_choose`` in the seat, a fake in
    tests. ``fallback(game, seat, legal)`` picks when the pick is refused
    (default ``code_pick``). ``sink`` with an ``escalate`` method records
    each refusal as a verdict row. ``set_piece_only`` (default True, R22)
    asks the model only on a beat whose view says ``set_piece``; ``False``
    asks on every action beat.

    The returned policy carries ``refusals``: one dict per refused pick
    ``{"reason", "why", "menu", "path", "took", "to", "seat"}``, ``to`` =
    ``"human"``.
    """
    fallback = fallback or code_pick

    def _refuse(reason: str, why: str, menu: list[str], got: Any, game: Any, seat: int, legal: list) -> Any:
        took = fallback(game, seat, legal)
        entry = {
            "reason": reason,
            "why": why,
            "menu": list(menu),
            "path": path_text(got),
            "took": move_id(took),
            "to": TO_HUMAN,
            "seat": seat,
        }
        _policy.refusals.append(entry)
        if sink is not None and hasattr(sink, "escalate"):
            sink.escalate(entry)
        return took

    def _policy(game: Any, seat: int) -> Any:
        legal = list(game.legal_moves(seat))
        if not legal:  # C14: a decision beat has no move; it is the human's
            raise RuntimeError(
                "no legal move for this seat: a decision beat is never on the menu"
            )
        if set_piece_only:
            try:
                view = game.observe(seat).view
            except Exception:  # noqa: BLE001 - a game with no view: not a set piece
                view = {}
            if not (isinstance(view, dict) and view.get("set_piece") is True):
                return fallback(game, seat, legal)
        menu = move_ids(legal)
        try:
            got = choose(list(menu))
        except Exception as e:  # noqa: BLE001 - a model is never trusted to behave
            return _refuse(UNREACHABLE, type(e).__name__, menu, None, game, seat, legal)
        path, reason = read_pick(got)
        if path is None:
            why = "nothing came back" if reason == UNREACHABLE else "not a move id"
            return _refuse(reason, why, menu, got, game, seat, legal)
        if path == ESCALATE:
            return _refuse(ESCALATED, "the model escalated", menu, got, game, seat, legal)
        move = move_of(path, legal)
        if move is None:
            return _refuse(OFF_MENU, "not on the menu", menu, got, game, seat, legal)
        return move

    _policy.refusals = []  # type: ignore[attr-defined]
    return _policy


# -- the ratatosk adapter (idea-side row 33) -----------------------------------
#: What the menu is served as: a one-script-shaped document with one table of
#: move rows, so ratatosk's frame reads it like any served scope.
MENU_RETURN = "Reply by calling propose once with path = one move id from the menu, exactly as listed, or path = ESCALATE."
QUESTION = "Pick one move id from the menu table and propose it as the path."


def menu_doc(menu: list[str]) -> dict:
    return {
        "state": "populated",
        "why": "",
        "return": MENU_RETURN,
        "tables": [
            {
                "id": "menu",
                "trust": "untrusted",
                "group": {"what": "menu"},
                "cannot_hold": [],
                "rows": [{"what": "move", "where": "menu", "move": m} for m in menu],
            }
        ],
    }


def ratatosk_choose(
    cmd: Sequence[str] = ("ratatosk",),
    model: str | None = None,
    timeout: float = 180.0,
    run: Callable[..., Any] = subprocess.run,
) -> Callable[[list[str]], Any]:
    """A ``choose`` that asks a local model through ``ratatosk --onescript``:
    the menu is served as a document, the model has the one tool, and its
    first ``propose`` row's ``path`` is the pick (``read_pick`` and
    ``move_of`` judge it; this adapter judges nothing). ``run`` is injected
    (``subprocess.run`` by default) so a test can fake the subprocess. A
    missing or failed command, a timeout, or no row is ``None`` -> the policy
    records ``unreachable`` and code picks."""
    cmd = tuple(cmd)

    def choose(menu: list[str]) -> Any:
        with tempfile.TemporaryDirectory(prefix="the-table-menu-") as d:
            served = Path(d) / "menu.json"
            out = Path(d) / "rows.jsonl"
            served.write_text(json.dumps(menu_doc(menu), sort_keys=True) + "\n", encoding="utf-8")
            argv = [*cmd, "--onescript", "--served", str(served), "--out", str(out)]
            if model:
                argv += ["--model", model]
            argv.append(QUESTION)
            try:
                run(argv, cwd=d, stdin=subprocess.DEVNULL, capture_output=True,
                    timeout=timeout, check=False)
            except (OSError, subprocess.TimeoutExpired):
                return None
            if not out.is_file():
                return None
            for line in out.read_text(encoding="utf-8", errors="replace").split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    return None
                return row if isinstance(row, dict) else None
            return None

    return choose
