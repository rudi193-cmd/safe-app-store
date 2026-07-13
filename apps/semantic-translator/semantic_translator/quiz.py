"""¿Cómo se dice? — multiple-choice EN↔ES match game over bilingual corpus pairs.

Each round shows a segment and four candidate translations; correct answers
build a streak multiplier. With --learner, every answer is recorded as an
FSRS review (correct=Good, wrong=Again), so playing schedules the same cards
the Learn tab studies.
"""
from __future__ import annotations

import random
import sys

from .learn import _load_bilingual_pairs

_OPTIONS = 4
_BASE_POINTS = 100
_STREAK_BONUS = 25

_GRADES = [
    (1.00, "🏆 ¡Perfecto! Traductor legendario."),
    (0.80, "🥇 Excelente — casi nada se te escapa."),
    (0.60, "🥈 Muy bien — el oído ya está afinado."),
    (0.40, "🥉 Buen comienzo — sigue practicando."),
    (0.00, "📚 ¡Ánimo! Repasa las lecciones y vuelve a intentarlo."),
]


def build_rounds(pairs: list[dict], n: int, reverse: bool,
                 rng: random.Random) -> list[dict]:
    """Return up to n rounds: prompt, shuffled options, correct index."""
    playable = [p for p in pairs if p["front"] and p["back"]]
    if len(playable) < 2:
        return []
    rng.shuffle(playable)
    rounds = []
    for pair in playable[:n]:
        prompt, answer = (pair["back"], pair["front"]) if reverse else (pair["front"], pair["back"])
        pool = [p["back"] if not reverse else p["front"]
                for p in playable if p is not pair]
        distractors = rng.sample(pool, min(_OPTIONS - 1, len(pool)))
        options = distractors + [answer]
        rng.shuffle(options)
        rounds.append({
            "prompt": prompt,
            "options": options,
            "correct": options.index(answer),
            "lesson": pair["lesson"],
            "atom_id": pair["atom_id"],
            "lang_from": pair["lang_back"] if reverse else pair["lang_front"],
            "lang_to": pair["lang_front"] if reverse else pair["lang_back"],
        })
    return rounds


def _read_answer(n_options: int) -> int | None:
    """Read 1..n_options from stdin; None means quit (q or EOF)."""
    while True:
        try:
            raw = input("your answer > ").strip().lower()
        except EOFError:
            return None
        if raw in ("q", "quit", "exit"):
            return None
        if raw.isdigit() and 1 <= int(raw) <= n_options:
            return int(raw) - 1
        print(f"  (enter 1-{n_options}, or q to quit)")


def _resolve_learner(name: str) -> dict | None:
    from . import db
    db.init_db()
    for learner in db.list_learners():
        if learner["name"].lower() == name.lower():
            return learner
    learner = db.create_learner(name=name)
    print(f"(new learner registered: {name})")
    return learner


def _record_srs(learner_id: str, atom_id: str, correct: bool) -> bool:
    """Map quiz result onto the SRS deck: correct=Good(3), wrong=Again(1)."""
    from .learn import submit_rating
    try:
        submit_rating(learner_id, atom_id, 3 if correct else 1)
        return True
    except ImportError:
        return False


def play(rounds: int = 10, reverse: bool = False, learner_name: str = "",
         seed: int | None = None) -> None:
    rng = random.Random(seed)
    pairs = _load_bilingual_pairs()
    game = build_rounds(pairs, rounds, reverse, rng)
    if not game:
        print("Not enough bilingual pairs in the corpus to play.")
        print("Seed some content first:  semantic-translator demo")
        sys.exit(1)

    learner = _resolve_learner(learner_name) if learner_name else None
    srs_ok = True

    direction = f"{game[0]['lang_from'].upper()} → {game[0]['lang_to'].upper()}"
    print("═" * 64)
    print(f"  ¿CÓMO SE DICE?   {direction}   {len(game)} rounds")
    print("  Pick the matching translation. Streaks multiply your score.")
    print("═" * 64)

    score = 0
    streak = 0
    best_streak = 0
    n_correct = 0
    played = 0

    for i, rnd in enumerate(game, 1):
        print(f"\n[{i}/{len(game)}]  ({rnd['lesson']})")
        print(f"  “{rnd['prompt']}”\n")
        for j, opt in enumerate(rnd["options"], 1):
            print(f"    {j}. {opt}")
        answer = _read_answer(len(rnd["options"]))
        if answer is None:
            print("\n(quit)")
            break
        played += 1
        correct = answer == rnd["correct"]
        if correct:
            n_correct += 1
            streak += 1
            best_streak = max(best_streak, streak)
            points = _BASE_POINTS + _STREAK_BONUS * (streak - 1)
            score += points
            flame = f"  🔥 streak x{streak}" if streak >= 3 else ""
            print(f"  ✓ +{points}{flame}")
        else:
            streak = 0
            print(f"  ✗ correct: {rnd['options'][rnd['correct']]}")
        if learner:
            srs_ok = _record_srs(learner["id"], rnd["atom_id"], correct) and srs_ok

    if not played:
        return
    accuracy = n_correct / played
    print("\n" + "═" * 64)
    print(f"  FINAL SCORE: {score}   ·   {n_correct}/{played} correct"
          f"   ·   best streak: {best_streak}")
    for threshold, title in _GRADES:
        if accuracy >= threshold:
            print(f"  {title}")
            break
    if learner:
        if srs_ok:
            from . import db
            stats = db.card_stats(learner["id"])
            print(f"  SRS updated for {learner['name']}: "
                  f"{stats['total']} cards, {stats['due']} due")
        else:
            print("  (fsrs not installed — results not recorded to SRS)")
    print("═" * 64)
