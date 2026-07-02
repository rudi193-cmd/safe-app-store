"""Data loading and quiz-scoring engine for civics-check. Pure stdlib, no network."""
import json
import random
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_naturalization_questions():
    return _load("naturalization_questions.json")


def load_colonies():
    return _load("colonies.json")


def load_amendments():
    return _load("amendments.json")


def load_quotes():
    return _load("quotes.json")


def load_on_this_day():
    return _load("on_this_day.json")


def load_timeline_events():
    return _load("timeline_events.json")


def load_signers():
    return _load("signers.json")


def load_states():
    return _load("states.json")


def today_events():
    key = date.today().strftime("%m-%d")
    return load_on_this_day().get(key, [])


def normalize(text):
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()


def answer_matches(user_answer, accepted_answers):
    norm_user = normalize(user_answer)
    if not norm_user:
        return False
    for accepted in accepted_answers:
        norm_accepted = normalize(accepted)
        if norm_user == norm_accepted:
            return True
        if norm_user in norm_accepted or norm_accepted in norm_user:
            return True
    return False


def pick_questions(pool, count, weighted_ids=None):
    """Pick `count` questions from pool, optionally favoring weighted_ids (missed questions)."""
    pool_by_id = {q["id"]: q for q in pool}
    chosen = []
    if weighted_ids:
        for qid in weighted_ids:
            if qid in pool_by_id and pool_by_id[qid] not in chosen:
                chosen.append(pool_by_id[qid])
            if len(chosen) >= count:
                return chosen[:count]
    remaining = [q for q in pool if q not in chosen]
    random.shuffle(remaining)
    chosen.extend(remaining[: count - len(chosen)])
    return chosen[:count]


def score_pass_fail(score, total):
    """USCIS-style: need 60% correct (6/10 on the real test) to pass."""
    return score / total >= 0.6 if total else False
