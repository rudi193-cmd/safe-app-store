"""The Liberty Bell -- civics-check's narrator. Cracked, deadpan, unimpressed by wrong answers.

House rule from the design system: jokes are load-bearing or they get cut. The Bell only
speaks when it has something to say -- on a wrong answer, a right one, or a perfect round.
It does not narrate the menu. It does not say hello.
"""
import random

RED = "\033[91m"
BLUE = "\033[94m"
GOLD = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# Joan G. Stark (jgs / Spunk), "Liberty Bell" (7/97), rec.arts.ascii / alt.ascii-art.
# Archive: https://oldcompcz.github.io/jgs/joan_stark/july4.html
# Also catalogued: Christopher Johnson's ASCII Art Collection (art #1711).
_LIBERTY_BELL_LINES = [
    "     .--.-,-.-.-,-.--.",
    "     |     \\   /     |",
    "     |      \\ /      |",
    "     |  .===,=,===.  |",
    "   _/\\_; .-'`^`'-. ;_/\\_",
    "  (  /` /_________\\ `\\  )",
    "  |  | |===========| |  |",
    "  |  | |           | |  |",
    "  |  | |  ,        | |  |",
    "  |  | ;_{_________; |  |",
    "  |  |/===`>========\\|  |",
    "  |  ;-._<`________.-;  |",
    "  |  | |     U     | |  |",
    " /   | |___________| |   \\",
    "|                         |",
    "|jgs                      |",
    "'-------------------------'",
]

LIBERTY_BELL_PLAIN = (
    "-=[ Liberty Bell ]=-  7/97\n"
    + "\n".join(_LIBERTY_BELL_LINES)
    + "\n                 est. 1776 — still ringing, barely\n"
)

LIBERTY_BELL = (
    f"{BOLD}{BLUE}\n"
    + "\n".join(_LIBERTY_BELL_LINES)
    + f"\n{RESET}{DIM}                 est. 1776 — still ringing, barely{RESET}\n"
)

# Legacy names — prefer LIBERTY_BELL / LIBERTY_BELL_PLAIN.
EAGLE = LIBERTY_BELL
EAGLE_PLAIN = LIBERTY_BELL_PLAIN

_WRONG = [
    "Wrong. I'd crack again if I could.",
    "No. I've heard worse, but not by much.",
    "That's not it. I've been broken longer and I'm still more right than that.",
    "Incorrect. Bold guess, though.",
    "No. Try reading a pamphlet sometime.",
    "Wrong answer. The Founders are, once again, disappointed in a different way.",
]

_RIGHT = [
    "Correct. Don't let it go to your head.",
    "Right. I'm grudgingly impressed.",
    "Correct. Even a cracked bell rings sometimes.",
    "Yes. Fine. Good.",
    "Correct. Someone read the pamphlet.",
]

_PERFECT = [
    "Perfect score. I would ring properly if I could. I cannot. You'll have to imagine it.",
    "All of them. Even I'm surprised, and I've been standing here since 1752.",
]

_ELECTION_YEAR_ASIDE = "// the Bell has opinions about November but the Bell keeps them to itself."


def perfect_plain():
    return f"THE BELL: {random.choice(_PERFECT)}"


def wrong():
    return f"{RED}THE BELL:{RESET} {random.choice(_WRONG)}"


def right():
    return f"{GOLD}THE BELL:{RESET} {random.choice(_RIGHT)}"


def perfect():
    return f"{GOLD}{BOLD}THE BELL:{RESET} {random.choice(_PERFECT)}"


def wrong_plain():
    return f"THE BELL: {random.choice(_WRONG)}"


def right_plain():
    return f"THE BELL: {random.choice(_RIGHT)}"


def ticker(quotes):
    """One-line marquee of a real founding-era quote, picked fresh each call."""
    q = random.choice(quotes)
    return f"{DIM}~~~ {q['quote']} -- {q['person']} ~~~{RESET}"


def ticker_plain(quotes):
    q = random.choice(quotes)
    return f"{q['quote']} -- {q['person']}"


MEDALS = [
    (1.0, "FOUNDING FATHER"),
    (0.9, "PATRIOT"),
    (0.75, "MINUTEMAN"),
    (0.6, "ALMOST FOUNDING FATHER"),
    (0.0, "REDCOAT SYMPATHIZER"),
]


def medal(score, total):
    if not total:
        return MEDALS[-1][1]
    pct = score / total
    for threshold, name in MEDALS:
        if pct >= threshold:
            return name
    return MEDALS[-1][1]


def telegram(mode, score, total, elapsed_s=None):
    passed = total and score / total >= 0.6
    m = medal(score, total)
    lines = [
        f"{GOLD}{BOLD}********* TELEGRAM *********{RESET}",
        f"RESULT MODE {mode.upper()} STOP",
        f"SCORE {score} OF {total} STOP",
    ]
    if elapsed_s is not None:
        lines.append(f"TIME {elapsed_s:.1f}S STOP")
    status = f"{GOLD}STATUS PASSED STOP{RESET}" if passed else f"{RED}STATUS KEEP STUDYING STOP{RESET}"
    lines.append(status)
    lines.append(f"{BLUE}MEDAL {m} STOP{RESET}")
    if total and score == total:
        lines.append(f"{GOLD}THE BELL SENDS REGARDS STOP ENTHUSIASTICALLY STOP{RESET}")
    else:
        lines.append(f"{DIM}THE BELL SENDS REGARDS STOP GRUDGINGLY STOP{RESET}")
    lines.append(f"{GOLD}{BOLD}*****************************{RESET}")
    return "\n".join(lines)


def telegram_plain(mode, score, total, elapsed_s=None):
    """Same telegram, no ANSI -- caller wraps in Rich markup if it wants color."""
    passed = total and score / total >= 0.6
    m = medal(score, total)
    lines = [
        "********* TELEGRAM *********",
        f"RESULT MODE {mode.upper()} STOP",
        f"SCORE {score} OF {total} STOP",
    ]
    if elapsed_s is not None:
        lines.append(f"TIME {elapsed_s:.1f}S STOP")
    lines.append("STATUS PASSED STOP" if passed else "STATUS KEEP STUDYING STOP")
    lines.append(f"MEDAL {m} STOP")
    if total and score == total:
        lines.append("THE BELL SENDS REGARDS STOP ENTHUSIASTICALLY STOP")
    else:
        lines.append("THE BELL SENDS REGARDS STOP GRUDGINGLY STOP")
    lines.append("*****************************")
    return "\n".join(lines)
