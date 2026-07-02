#!/usr/bin/env python3
"""Civics Check — America's 250th civics quiz. Pure Python, offline, stdlib only."""
import random
import time

import db
import engine

RED = "\033[91m"
BLUE = "\033[94m"
GOLD = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

BANNER = f"""{BOLD}{BLUE}
   *  *  *  *  *  *  *  *  *  *  *  *  *
  {RED}=================================={BLUE}
     C I V I C S   C H E C K
     America's 250th -- 1776 * 2026
  {RED}=================================={BLUE}
   *  *  *  *  *  *  *  *  *  *  *  *  *
{RESET}"""

MENU = [
    ("1", "Naturalization quiz (10 questions, need 6 to pass)"),
    ("2", "Review my missed questions"),
    ("3", "State matchup (capital / admission order)"),
    ("4", "Timeline sort (put history in order)"),
    ("5", "13 Colonies flashcards"),
    ("6", "On This Day"),
    ("7", "Founding Fathers quote match"),
    ("8", "Declaration signers browser"),
    ("9", "Amendment explorer"),
    ("10", "Speed round (60 seconds, naturalization bank)"),
    ("11", "View last certificate"),
    ("12", "Pass-the-keyboard duel"),
    ("Q", "Quit"),
]


def pause():
    input(f"{DIM}(press enter to continue){RESET}\n")


def header(title):
    print(f"\n{BOLD}{GOLD}--- {title} ---{RESET}\n")


def ask_open(question, accepted):
    ans = input(f"{question}\n> ").strip()
    return engine.answer_matches(ans, accepted)


def certificate(mode, score, total, elapsed_s=None):
    passed = engine.score_pass_fail(score, total)
    stars = "*" * 13
    print(f"\n{BOLD}{GOLD}{stars}{RESET}")
    print(f"{BOLD}  CERTIFICATE OF COMPLETION{RESET}")
    print(f"  Mode: {mode}")
    print(f"  Score: {score}/{total}")
    if elapsed_s is not None:
        print(f"  Time: {elapsed_s:.1f}s")
    if total and score / total >= 0.6:
        print(f"  {GOLD}Status: PASSED{RESET}")
    else:
        print(f"  {RED}Status: keep studying{RESET}")
    print(f"{BOLD}{GOLD}{stars}{RESET}\n")
    if total and score == total:
        fireworks()
    db.record_score(mode, score, total, elapsed_s)


def fireworks():
    frames = ["  .  *  .  ", "  * *** *  ", " *  *#*  * ", "  * *** *  ", "  .  *  .  "]
    print(f"{GOLD}{BOLD}PERFECT SCORE!{RESET}")
    for f in frames:
        print(f"{RED}{f}{RESET}")


def run_quiz(pool, count, mode_name, time_limit=None, weighted=False):
    weighted_ids = db.missed_question_ids() if weighted else None
    questions = engine.pick_questions(pool, count, weighted_ids)
    if not questions:
        print("No questions available.")
        return
    score = 0
    start = time.time()
    for i, q in enumerate(questions, 1):
        if time_limit and (time.time() - start) > time_limit:
            print(f"\n{RED}Time's up!{RESET}")
            break
        print(f"\n{DIM}[{q['category']} / {q['subcategory']}]{RESET}")
        correct = ask_open(f"Q{i}. {q['question']}", q["answers"])
        if correct:
            print(f"{GOLD}Correct.{RESET}")
            score += 1
            db.clear_miss(q["id"])
        else:
            print(f"{RED}Not quite. Accepted answer(s): {', '.join(str(a) for a in q['answers'])}{RESET}")
            db.record_miss(q["id"])
    elapsed = time.time() - start
    certificate(mode_name, score, len(questions), elapsed)


def mode_naturalization():
    header("Naturalization Quiz")
    run_quiz(engine.load_naturalization_questions(), 10, "naturalization")


def mode_missed():
    header("Missed Questions Review")
    ids = db.missed_question_ids(limit=10)
    if not ids:
        print("Nothing missed yet -- clean slate.")
        return
    pool = engine.load_naturalization_questions()
    run_quiz(pool, len(ids), "missed-review", weighted=True)


def mode_states():
    header("State Matchup")
    states = engine.load_states()
    random.shuffle(states)
    score = 0
    rounds = min(8, len(states))
    for s in states[:rounds]:
        mode = random.choice(["capital", "order"])
        if mode == "capital":
            correct = ask_open(f"What is the capital of {s['name']}?", [s["capital"]])
        else:
            correct = ask_open(
                f"{s['name']} was admitted as the __th state. (number)", [str(s["order"])]
            )
        if correct:
            print(f"{GOLD}Correct.{RESET} {s['fact']}")
            score += 1
        else:
            print(f"{RED}Nope.{RESET} {s['name']} -- capital {s['capital']}, admitted #{s['order']} ({s['admitted']}). {s['fact']}")
    certificate("state-matchup", score, rounds)


def mode_timeline():
    header("Timeline Sort")
    events = engine.load_timeline_events()
    sample = random.sample(events, min(8, len(events)))
    shuffled = sample[:]
    random.shuffle(shuffled)
    print("Put these in chronological order (earliest first) by typing the numbers, e.g. '3 1 2 ...':\n")
    for i, e in enumerate(shuffled, 1):
        print(f"  {i}. {e['event']}")
    raw = input("\nYour order> ").split()
    correct_order = sorted(range(len(shuffled)), key=lambda i: shuffled[i]["year"])
    try:
        user_order = [int(x) - 1 for x in raw]
    except ValueError:
        user_order = []
    score = sum(1 for a, b in zip(user_order, correct_order) if a == b)
    print(f"\nActual chronological order:")
    for i in correct_order:
        print(f"  {shuffled[i]['year']} -- {shuffled[i]['event']}")
    certificate("timeline-sort", score, len(shuffled))


def mode_colonies():
    header("13 Colonies Flashcards")
    colonies = engine.load_colonies()
    random.shuffle(colonies)
    for c in colonies:
        print(f"\n{BOLD}{c['name']}{RESET} -- founded {c['founded']} by {c['founder']}")
        print(f"  {c['fact']}")
        input(f"{DIM}(press enter for next colony){RESET}")


def mode_on_this_day():
    header("On This Day")
    events = engine.today_events()
    if not events:
        print("No recorded events for today in this dataset -- try July 4th weekend for the good stuff.")
    for e in events:
        print(f"  * {e}")


def mode_quotes():
    header("Founding Fathers Quote Match")
    quotes = engine.load_quotes()
    random.shuffle(quotes)
    score = 0
    for q in quotes[:6]:
        options = [q["person"]] + q["distractors"]
        random.shuffle(options)
        print(f"\n\"{q['quote']}\"")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        raw = input("Who said it? > ").strip()
        try:
            pick = options[int(raw) - 1]
        except (ValueError, IndexError):
            pick = ""
        if pick == q["person"]:
            print(f"{GOLD}Correct.{RESET}")
            score += 1
        else:
            print(f"{RED}It was {q['person']}.{RESET}")
    certificate("quote-match", score, min(6, len(quotes)))


def mode_signers():
    header("Declaration Signers Browser")
    signers = engine.load_signers()
    for s in signers:
        print(f"\n{BOLD}{s['name']}{RESET} ({s['state']})")
        print(f"  {s['fact']}")
    pause()


def mode_amendments():
    header("Amendment Explorer")
    amendments = engine.load_amendments()
    print("Browse: enter a number 1-27, or 'quiz' for a quick round.\n")
    choice = input("> ").strip().lower()
    if choice == "quiz":
        sample = random.sample(amendments, 5)
        score = 0
        for a in sample:
            correct = ask_open(f"Which amendment (number): \"{a['summary']}\"", [str(a["number"])])
            if correct:
                print(f"{GOLD}Correct.{RESET}")
                score += 1
            else:
                print(f"{RED}That's the {a['number']}th Amendment ({a['year']}).{RESET}")
        certificate("amendment-quiz", score, len(sample))
        return
    try:
        n = int(choice)
        match = next(a for a in amendments if a["number"] == n)
        print(f"\n{BOLD}Amendment {match['number']} ({match['year']}){RESET}: {match['summary']}")
    except (ValueError, StopIteration):
        print("Not a valid amendment number.")


def mode_speed_round():
    header("Speed Round -- 60 seconds")
    run_quiz(engine.load_naturalization_questions(), 100, "speed-round", time_limit=60)


def mode_certificate():
    header("Recent Scores")
    for mode in ["naturalization", "speed-round", "state-matchup", "quote-match", "amendment-quiz"]:
        rows = db.top_scores(mode, limit=3)
        if rows:
            print(f"\n{BOLD}{mode}{RESET}")
            for score, total, elapsed_s, played_at in rows:
                t = f", {elapsed_s:.1f}s" if elapsed_s else ""
                print(f"  {score}/{total}{t}  ({played_at})")
    if not any(db.top_scores(m, 1) for m in ["naturalization", "speed-round", "state-matchup", "quote-match", "amendment-quiz"]):
        print("No scores recorded yet -- play a round first.")


def mode_duel():
    header("Pass-the-Keyboard Duel")
    p1 = input("Player 1 name: ").strip() or "Player 1"
    p2 = input("Player 2 name: ").strip() or "Player 2"
    pool = engine.load_naturalization_questions()
    questions = engine.pick_questions(pool, 10)
    scores = {p1: 0, p2: 0}
    for i, q in enumerate(questions):
        player = p1 if i % 2 == 0 else p2
        print(f"\n{BOLD}{player}'s turn.{RESET}")
        correct = ask_open(f"Q{i + 1}. {q['question']}", q["answers"])
        if correct:
            print(f"{GOLD}Correct.{RESET}")
            scores[player] += 1
        else:
            print(f"{RED}Nope. Answer: {q['answers'][0]}{RESET}")
    print(f"\n{BOLD}Final score:{RESET} {p1}: {scores[p1]}  |  {p2}: {scores[p2]}")
    if scores[p1] == scores[p2]:
        print("It's a tie!")
    else:
        winner = p1 if scores[p1] > scores[p2] else p2
        print(f"{GOLD}{winner} wins!{RESET}")
    db.record_score(f"duel:{p1}-vs-{p2}", max(scores.values()), len(questions))


HANDLERS = {
    "1": mode_naturalization,
    "2": mode_missed,
    "3": mode_states,
    "4": mode_timeline,
    "5": mode_colonies,
    "6": mode_on_this_day,
    "7": mode_quotes,
    "8": mode_signers,
    "9": mode_amendments,
    "10": mode_speed_round,
    "11": mode_certificate,
    "12": mode_duel,
}


def main():
    print(BANNER)
    today = engine.today_events()
    if today:
        print(f"{GOLD}On this day: {today[0]}{RESET}\n")
    while True:
        header("Main Menu")
        for key, label in MENU:
            print(f"  {BOLD}{key:>2}{RESET}  {label}")
        try:
            choice = input("\n> ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            print("\nHappy 250th.")
            break
        if choice == "Q":
            print("Happy 250th.")
            break
        handler = HANDLERS.get(choice)
        if handler:
            try:
                handler()
            except (KeyboardInterrupt, EOFError):
                print("\nInterrupted.")
        else:
            print("Not a valid option.")


if __name__ == "__main__":
    main()
