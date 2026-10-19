"""Trivia from Jeles: a fixed bank, and a question drawn from the seed.

The bank is what Jeles serves in the shared SOIL store, read through the
injected seam (``libs/storage-backend``): ``storage_backend.list_records``
on ``ask_jeles_corpus``, a collection this app reads and never writes
(``safe-app-manifest.json``: in ``store_scope``, no ``store_write``).

A row joins the bank only when Jeles would let it answer: ``visibility`` is
``serve`` or ``public``, ``verification_kind`` is ``human`` or ``machine``
(never ``asserted``, never missing), its question ends in "?", and it cites a
source. Each question carries its own label from its row: its ``status`` and
who ``verified_by`` credits (``"public record: NASA, Encyclopaedia
Britannica"``), so the view says what Jeles says about that one question, not
one line for the whole bank. (Before Jeles 40456f1 every row was
``internal``; a store seeded before it is re-tiered by ``jeles-seed``.)

With no seam installed, no backend configured, or too few rows that can
answer, there is no bank, the game says why, and the board plays the same.

Nothing here writes to Jeles. The bank is sorted and hashed, so a game's
record names the exact bank it was played against, and a replay against a
different bank is a different game, said rather than hidden.

A question is ``ask(bank, seed, k)``: the k-th question of a board, drawn from
the seed, with the right answer and three others from the bank shuffled into
A-D. Same bank, seed and k: the same question, the same order.
"""
from __future__ import annotations

import hashlib
import json

from .rng import Rng

LABELS = ("A", "B", "C", "D")
#: Jeles's collection in the shared SOIL store; read, never written.
COLLECTION = "ask_jeles_corpus"
#: Rows that can answer (willow-mcp's serve tier and below) and the kinds that
#: are verified. ``asserted`` research is never a trivia answer.
VISIBLE = ("serve", "public")
ANSWERING = ("human", "machine")
#: Said for the bank as a whole while no question is waiting.
SOURCE = "Jeles, verified entries only"
#: A row with no verification label of its own (hand-built banks in tests).
UNLABELLED = "Jeles, no verification label"
#: Option text is the answer's first sentence, cut at this many characters.
OPTION_CHARS = 160


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    for end in (". ", "! ", "? "):
        i = text.find(end)
        if 0 < i < OPTION_CHARS:
            return text[: i + 1]
    return text if len(text) <= OPTION_CHARS else text[: OPTION_CHARS - 1].rstrip() + "…"


def answers(row: dict) -> bool:
    """Whether a Jeles row may be a trivia answer."""
    q, a, src = row.get("question"), row.get("answer"), row.get("sources")
    return (row.get("visibility") in VISIBLE
            and row.get("verification_kind") in ANSWERING
            and isinstance(q, str) and q.strip().endswith("?")
            and isinstance(a, str) and bool(a.strip())
            and isinstance(src, list) and any(str(x).strip() for x in src))


def label(row: dict) -> str:
    """What Jeles says about this one row: ``Jeles, verified: public record: NASA``."""
    status = str(row.get("status") or row.get("verification_kind"))
    by = str(row.get("verified_by") or "").strip()
    return f"Jeles, {status}: {by}" if by else f"Jeles, {status}"


def _row_id(row: dict) -> str:
    for key in ("id", "_id", "record_id", "nugget_id"):
        if isinstance(row.get(key), str) and row[key]:
            return row[key]
    return "q" + hashlib.sha256(row["question"].strip().encode()).hexdigest()[:10]


def load_jeles(backend=None) -> tuple[list, str]:
    """(bank, why): the answering rows of ``ask_jeles_corpus``, or [] and why.
    ``backend`` is anything with ``list(collection)``; else the seam's own."""
    if backend is None:
        try:
            import storage_backend as seam  # type: ignore[import-not-found]
        except ImportError:
            return [], "the storage seam isn't installed, so Jeles can't be read"
        if not seam.available():
            return [], "no SOIL backend configured, so Jeles can't be read"
        read = seam.list_records
    else:
        read = backend.list
    try:
        rows = read(COLLECTION)
    except Exception as e:  # a store that fails is said, never guessed past
        return [], f"Jeles could not be read: {type(e).__name__}: {e}"
    bank = [{"id": _row_id(r), "question": r["question"].strip(),
             "answer": _first_sentence(r["answer"]), "source": label(r)}
            for r in rows if isinstance(r, dict) and answers(r)]
    if len({b["answer"] for b in bank}) < len(LABELS):
        return [], f"Jeles serves too few verified questions ({len(bank)})"
    return sorted(bank, key=lambda b: b["id"]), ""


def digest(bank: list) -> str:
    return hashlib.sha256(
        json.dumps(bank, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ask(bank: list, seed: int, k: int) -> dict:
    """The k-th question for this seed: id, question, options A-D, the right label."""
    rng = Rng((seed * 1000003 + 7919 * (k + 1)) & 0xFFFFFFFF)
    pick = bank[rng.below(len(bank))]
    others = [b["answer"] for b in bank if b["answer"] != pick["answer"]]
    wrong = []
    while len(wrong) < len(LABELS) - 1:
        cand = rng.pick(others)
        if cand not in wrong:
            wrong.append(cand)
    options = rng.shuffled([pick["answer"], *wrong])
    return {
        "id": pick["id"],
        "question": pick["question"],
        "options": dict(zip(LABELS, options)),
        "right": LABELS[options.index(pick["answer"])],
        "source": pick.get("source", UNLABELLED),
    }
