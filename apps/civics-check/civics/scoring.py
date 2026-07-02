"""Answer normalization, matching, and deck selection."""

from __future__ import annotations

import random


def normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()


def answer_matches(user_answer: str, accepted_answers: list[str]) -> bool:
    norm_user = normalize(user_answer)
    if not norm_user:
        return False
    for accepted in accepted_answers:
        norm_accepted = normalize(str(accepted))
        if norm_user == norm_accepted:
            return True
        if norm_user in norm_accepted or norm_accepted in norm_user:
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
    return None
