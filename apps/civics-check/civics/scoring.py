"""Answer normalization, matching, and deck selection.

Matching philosophy: the vibe counts. A learner who typed "he freed the
slaves", "washingtin", or "twenty seven" knew the answer — grade on
meaning-bearing tokens with spelling slack, not on exact strings.
Numbers stay strict: "16" is never the 6th amendment.
"""

from __future__ import annotations

import difflib
import random

# Words that carry no grading weight — grammar, hedges, question echoes.
_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "at", "by", "for",
    "is", "are", "was", "were", "be", "been", "it", "its", "that", "this",
    "we", "us", "our", "you", "your", "they", "them", "their", "he", "she",
    "can", "could", "must", "may", "do", "does", "did", "have", "has", "had",
    "one", "some", "any", "not", "no",
}

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
}
_ORDINAL_SUFFIXES = ("st", "nd", "rd", "th")


def normalize(text: str) -> str:
    # non-alnum becomes space (not dropped) so "twenty-seven" keeps its seam
    out = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    return " ".join(out.split())


def _canon_token(tok: str) -> str:
    """Digits win: '22nd' -> '22', 'sixth' -> '6'."""
    if tok.isdigit():
        return tok
    for suffix in _ORDINAL_SUFFIXES:
        stem = tok[: -len(suffix)]
        if tok.endswith(suffix) and stem.isdigit():
            return stem
    for table in (_ONES, _TEENS, _TENS, _ORDINALS):
        if tok in table:
            return str(table[tok])
    return tok


def _tokens(norm_text: str) -> list[str]:
    """Significant tokens: stopwords out, number words to digits,
    adjacent tens+ones merged ("twenty seven" -> "27").

    Stopword status is judged on the ORIGINAL word — "one" in "no one is
    above the law" stays grammar, but "twenty one" still merges to 21
    because the merge happens first."""
    raw = [(_canon_token(t), t) for t in norm_text.split()]
    merged: list[tuple[str, str]] = []
    for canon, orig in raw:
        prev = merged[-1][0] if merged else ""
        if (
            prev.isdigit()
            and canon.isdigit()
            and int(prev) % 10 == 0
            and 10 < int(prev) < 100
            and int(canon) < 10
        ):
            merged[-1] = (str(int(prev) + int(canon)), "")  # compound number
        else:
            merged.append((canon, orig))
    return [canon for canon, orig in merged if orig not in _STOPWORDS]


def _token_match(user_tok: str, accepted_tok: str) -> bool:
    if user_tok == accepted_tok:
        return True
    # numbers are graded strictly — no fuzz between 16 and 6
    if user_tok.isdigit() or accepted_tok.isdigit():
        return False
    # prefix slack: "free"/"freedom", "congress"/"congressional"
    if len(user_tok) >= 4 and len(accepted_tok) >= 4:
        if user_tok.startswith(accepted_tok) or accepted_tok.startswith(user_tok):
            return True
        # spelling slack for proper names and long words
        if difflib.SequenceMatcher(None, user_tok, accepted_tok).ratio() >= 0.8:
            return True
    return False


def answer_matches(user_answer: str, accepted_answers: list[str]) -> bool:
    norm_user = normalize(user_answer)
    if not norm_user:
        return False
    user_toks = _tokens(norm_user)
    for accepted in accepted_answers:
        norm_accepted = normalize(str(accepted))
        if not norm_accepted:
            continue
        if norm_user == norm_accepted:
            return True
        acc_toks = _tokens(norm_accepted)
        if not acc_toks:
            continue
        covered = sum(1 for a in acc_toks if any(_token_match(u, a) for u in user_toks))
        # user said everything the answer needs (extra chatter allowed)
        if covered == len(acc_toks):
            return True
        # everything the user said belongs to the answer, and it covers
        # at least half of it — "civil rights" for "civil rights movement"
        if user_toks and covered * 2 >= len(acc_toks):
            if all(any(_token_match(u, a) for a in acc_toks) for u in user_toks):
                return True
        # whole-string spelling slack for short answers ("washingtin")
        if len(norm_accepted) >= 5 and not any(t.isdigit() for t in acc_toks):
            if difflib.SequenceMatcher(None, norm_user, norm_accepted).ratio() >= 0.84:
                return True
    return False


def score_pass_fail(score: int, total: int, ratio: float = 0.6) -> bool:
    return score / total >= ratio if total else False


def pick_items(pool: list, count: int, weighted_ids: list[str] | None = None, id_key: str = "id"):
    """Pick `count` items from pool, optionally favoring weighted_ids."""
    if not pool:
        return []
    by_id = {item[id_key]: item for item in pool if id_key in item}
    chosen: list = []
    if weighted_ids:
        for item_id in weighted_ids:
            if item_id in by_id and by_id[item_id] not in chosen:
                chosen.append(by_id[item_id])
            if len(chosen) >= count:
                return chosen[:count]
    remaining = [item for item in pool if item not in chosen]
    random.shuffle(remaining)
    chosen.extend(remaining[: count - len(chosen)])
    return chosen[:count]


def pick_choice(user_raw: str, options: list[str]) -> str | None:
    raw = user_raw.strip()
    if not raw:
        return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass
    for opt in options:
        if normalize(raw) == normalize(opt):
            return opt
    # typed the option instead of its number — match on vibe, but only
    # if exactly one option matches (ambiguity picks nothing)
    hits = [opt for opt in options if answer_matches(raw, [opt])]
    if len(hits) == 1:
        return hits[0]
    return None
