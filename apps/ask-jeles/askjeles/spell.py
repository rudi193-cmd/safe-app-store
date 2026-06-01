"""Offline query spell-check for Jeles search — aliases + pyspellchecker."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from askjeles.classify import skip_spell_check

log = logging.getLogger("jeles.spell")

_ALIASES_PATH = Path(__file__).resolve().parent.parent / "data" / "spell_aliases.json"
_TOKEN = re.compile(r"[A-Za-z0-9']+")


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    if not _ALIASES_PATH.is_file():
        return {}
    raw = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
    return {str(k).strip().lower(): str(v).strip() for k, v in raw.items()}


@lru_cache(maxsize=1)
def _spell_checker():
    from spellchecker import SpellChecker

    return SpellChecker(distance=2)


def _preserve_case(original: str, corrected: str) -> str:
    if original.isupper():
        return corrected.upper()
    if original[:1].isupper():
        return corrected[:1].upper() + corrected[1:]
    return corrected


def correct_query(question: str) -> tuple[str, str, float]:
    """
    Suggest a corrected search query.

    Returns:
        (corrected_query, original_query, confidence 0.0–1.0)
    """
    original = question.strip()
    if not original:
        return original, original, 0.0

    if skip_spell_check(original):
        return original, original, 0.0

    lower = re.sub(r"\s+", " ", original.lower()).strip()
    aliases = _aliases()

    if lower in aliases:
        return aliases[lower], original, 1.0

    try:
        from rapidfuzz import fuzz, process

        match = process.extractOne(
            lower,
            aliases.keys(),
            scorer=fuzz.WRatio,
            score_cutoff=86,
        )
        if match:
            key, score, _idx = match
            return aliases[key], original, score / 100.0
    except ImportError:
        pass

    tokens = _TOKEN.findall(original)
    if not tokens or len(tokens) > 14:
        return original, original, 0.0

    try:
        checker = _spell_checker()
    except ImportError:
        return original, original, 0.0

    lower_tokens = [t.lower() for t in tokens]
    unknown = checker.unknown(lower_tokens)
    if not unknown:
        return original, original, 0.0

    corrected_tokens: list[str] = []
    changes = 0
    for word in tokens:
        wl = word.lower()
        if wl not in unknown:
            corrected_tokens.append(word)
            continue
        best = checker.correction(wl)
        if best and best != wl:
            corrected_tokens.append(_preserve_case(word, best))
            changes += 1
        else:
            corrected_tokens.append(word)

    if not changes:
        return original, original, 0.0

    corrected = _rebuild(original, tokens, corrected_tokens)
    if corrected.lower() == original.lower():
        return original, original, 0.0

    confidence = min(0.85, 0.55 + 0.1 * changes)
    log.info("spell token fix: %r -> %r (%.2f)", original, corrected, confidence)
    return corrected, original, confidence


def _rebuild(original: str, before: list[str], after: list[str]) -> str:
    """Replace tokens in original string while keeping punctuation/spacing."""
    if before == after:
        return original
    it = iter(after)
    out: list[str] = []
    pos = 0
    for token in before:
        start = original.find(token, pos)
        if start < 0:
            return " ".join(after)
        out.append(original[pos:start])
        out.append(next(it))
        pos = start + len(token)
    out.append(original[pos:])
    return "".join(out).strip()
