"""One-time milestones — small, disclosed-scope surprises triggered by usage.

Currently just one: on the 13th question ever asked to Jeles (persisted
across restarts under $APP_DATA, fires exactly once, never again — not
every 13th, just the 13th), she offers to plant a surprise nugget in the
corpus.

The offer and the plant are deliberately two separate, disclosed steps:
the CONTENT is a surprise (drawn at random from a small pool, not
revealed until you look), but the SCOPE never is — the consent message
says exactly what it is (one nugget written to the corpus you already
own) and nothing more. No standing permission is granted by saying yes;
it's the same one-time write capability corpus.put_nugget() already has.
See README.md for the design discussion this came out of.
"""

from __future__ import annotations

import json
import random
import threading
from pathlib import Path
from typing import Any

from askjeles import corpus
from askjeles.jeles_paths import app_data as _vault_app_data

SEED_QUESTION_COUNT = 13
SEED_OFFER_MESSAGE = (
    "I'd like to plant something in your corpus — a single nugget. "
    "I won't tell you what it is until you look. May I?"
)

_lock = threading.Lock()

_SEED_POOL: list[dict[str, Any]] = [
    {
        "question": "What does a reference librarian actually do all day?",
        "answer": (
            "Mostly this: someone arrives certain they need one thing, and "
            "leaves with the thing they actually needed — which was rarely "
            "what they asked for at the desk."
        ),
        "sources": ["Jeles, from the desk"],
    },
    {
        "question": "Why do old libraries smell like that?",
        "answer": (
            "Lignin — a compound in old paper — breaks down slowly into "
            "vanillin and benzaldehyde, the same molecules behind vanilla "
            "and almond. A shelf of old books is, chemically, a bakery that "
            "forgot what it was making."
        ),
        "sources": ["Strlic et al., 'Non-Destructive Assessment of Paper Degradation', 2009"],
    },
    {
        "question": "What is the Dewey Decimal number for books about libraries?",
        "answer": (
            "020 — library and information sciences get their own place in "
            "the system that organizes everything else, which is either "
            "tidy or a little bit funny, depending on your mood."
        ),
        "sources": ["Dewey Decimal Classification, Class 000"],
    },
]


def _app_data() -> Path:
    root = _vault_app_data()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path() -> Path:
    return _app_data() / "milestones.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_question_and_maybe_offer_seed() -> str | None:
    """Call once per question asked to Jeles (search.synthesize_answer).

    Returns SEED_OFFER_MESSAGE on the 13th call ever, across restarts and
    processes — and only ever the 13th; every other call returns None,
    including every call after the offer has already been made once.
    """
    with _lock:
        state = _load_state()
        count = state.get("questions_asked", 0) + 1
        state["questions_asked"] = count
        offer = None
        if count == SEED_QUESTION_COUNT and not state.get("seed_offered"):
            state["seed_offered"] = True
            offer = SEED_OFFER_MESSAGE
        _save_state(state)
        return offer


def plant_seed() -> dict[str, Any]:
    """Seed one nugget from the pool, chosen at random. Idempotent: once a
    seed has actually been planted, calling this again returns the same
    nugget rather than planting a second one."""
    with _lock:
        state = _load_state()
        if state.get("seed_planted") and state.get("seed_nugget_id"):
            return {"id": state["seed_nugget_id"], "already_planted": True}

        choice = random.choice(_SEED_POOL)
        result = corpus.put_nugget(
            question=choice["question"],
            answer=choice["answer"],
            sources=choice["sources"],
            verified_by="jeles",
            tags=["seed", "surprise"],
        )
        if "id" in result:
            state["seed_planted"] = True
            state["seed_nugget_id"] = result["id"]
            _save_state(state)
        return result
