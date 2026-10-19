"""Trivia from Jeles: a fixed bank, and a question drawn from the seed.

The bank is Jeles's research corpus (``Jeles/corpus/seed/*.json``), read as it
stands: every pair whose question ends in "?" and cites at least one source URL.
Those pairs are Jeles's *asserted* nuggets: machine-proposed and sourced, not
yet checked by a named human (``Jeles/corpus/README.md``). The view says so.

Nothing here touches the corpus beyond reading it. The bank is sorted and
hashed, so a game's record names the exact bank it was played against, and a
replay against a different bank is a different game, said rather than hidden.

A question is ``ask(bank, seed, k)``: the k-th question of a board, drawn from
the seed, with the right answer and three others from the bank shuffled into
A-D. Same bank, seed and k: the same question, the same order.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .rng import Rng

LABELS = ("A", "B", "C", "D")
SOURCE = "Jeles, sourced, not yet human-checked"
#: Option text is the answer's first sentence, cut at this many characters.
OPTION_CHARS = 160


def default_root() -> Path:
    """``$CATGRID_JELES``, else the Jeles checkout beside safe-app-store."""
    if os.environ.get("CATGRID_JELES"):
        return Path(os.environ["CATGRID_JELES"]).expanduser()
    return Path(__file__).resolve().parents[4] / "Jeles"


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    for end in (". ", "! ", "? "):
        i = text.find(end)
        if 0 < i < OPTION_CHARS:
            return text[: i + 1]
    return text if len(text) <= OPTION_CHARS else text[: OPTION_CHARS - 1].rstrip() + "…"


def load_jeles(root: Path | None = None) -> tuple[list, str]:
    """(bank, why): the bank, or [] and why when Jeles can't be read."""
    seed_dir = (root or default_root()) / "corpus" / "seed"
    if not seed_dir.is_dir():
        return [], f"no Jeles corpus at {seed_dir.name}/ (set CATGRID_JELES)"
    bank = []
    for f in sorted(seed_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        cited = {
            ev.get("pair_source")
            for ev in data.get("evidence", [])
            if isinstance(ev, dict) and str(ev.get("locator", "")).startswith(("http://", "https://"))
        }
        for i, p in enumerate(data.get("pairs", [])):
            q, a = p.get("source_text", ""), p.get("target_text", "")
            if isinstance(q, str) and q.strip().endswith("?") and a and q in cited:
                bank.append({"id": f"{f.stem}:{i}", "question": q.strip(),
                             "answer": _first_sentence(a)})
    if len(bank) < len(LABELS):
        return [], "the Jeles corpus has too few sourced questions"
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
    }
