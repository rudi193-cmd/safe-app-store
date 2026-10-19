"""The lane: what a game leaves in SOIL, and how a record plays back.

A game is its inputs. ``(seed, n, moves)`` and the trivia bank it was played
against give back every state, heart, hint and napkin, byte for byte, so a
game's record holds those and nothing derived; the board is named by its
digest, so a replay that makes a different board says so.

Three collections, all inside this app's ``store_scope`` (``safe-app-
manifest.json``): ``catgrid_games`` (one per game), ``catgrid_napkins`` (one
per napkin found; found once, it stays found) and ``catgrid_trivia`` (one per
question asked). Writes go through the injected storage seam
(``libs/storage-backend``); with no backend, or no seam installed, nothing is
written, the answer says ``unavailable`` and the game plays the same. The
engine (board, solve, play) never imports this module.
"""
from __future__ import annotations

import hashlib
import json

from . import trivia
from .board import generate
from .play import Game

GAMES, NAPKINS, TRIVIA = "catgrid_games", "catgrid_napkins", "catgrid_trivia"
COLLECTIONS = (GAMES, NAPKINS, TRIVIA)


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def records(game: Game) -> list[tuple[str, str, dict]]:
    """(collection, record_id, record) for everything this game leaves."""
    n, seed = game.board.n, game.seed
    out = [(GAMES, f"{seed}-{n}-{_sha(game.moves)[:16]}", {
        "seed": seed, "n": n, "board": game.board.digest(),
        "bank": trivia.digest(game.bank) if game.bank else None,
        "words": _sha(game.words) if game.words else None,
        "moves": [list(m) for m in game.moves],
        "status": game.status, "hearts": game.hearts,
    })]
    for f in game.found:
        out.append((NAPKINS, f"{seed}-{n}-{f['cell']}",
                    {"word": f["word"], "seed": seed, "n": n, "cell": f["cell"]}))
    for k, a in enumerate(game.asked):
        out.append((TRIVIA, f"{seed}-{n}-{k}",
                    {"id": a["id"], "said": a["said"], "right": a["right"],
                     "seed": seed, "n": n, "k": k}))
    return out


def write(game: Game, backend=None) -> dict:
    """Put the game's records through the seam: ``backend`` if given, else the
    storage-backend module's configured one. ``{"state", "why", "written"}``."""
    if backend is None:
        try:
            import storage_backend as backend  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return {"state": "unavailable", "why": "the storage seam isn't installed",
                    "written": 0}
        if not backend.available():
            return {"state": "unavailable", "why": "no SOIL backend configured",
                    "written": 0}
    written = 0
    for collection, rid, rec in records(game):
        if collection not in COLLECTIONS:  # the lane wall, said here as well as at the gate
            raise ValueError(f"{collection!r} is outside catgrid's lane")
        backend.put(collection, rec, record_id=rid)
        written += 1
    return {"state": "written", "why": "", "written": written}


def replay(record: dict, *, bank: list | None = None, words: list | None = None) -> Game:
    """The game a ``catgrid_games`` record holds, played again from its inputs.
    Refuses a record whose board, or bank, isn't the one it names."""
    board = generate(record["seed"], record["n"])
    if board.digest() != record["board"]:
        raise ValueError("this board isn't the one the record names")
    if record.get("bank") and (not bank or trivia.digest(bank) != record["bank"]):
        raise ValueError("this trivia bank isn't the one the game was played against")
    if record.get("words") and (not words or _sha(list(words)) != record["words"]):
        raise ValueError("these napkin words aren't the ones the game was played with")
    game = Game(board, record["seed"], bank=bank, words=words)
    for move in record["moves"]:
        game.step(tuple(move))
    return game
