"""Self-contained 2-player Go Fish simulator (stdlib only).

52-card deck, ranks 0..12 (4 each). Deal 7 each; rest form the stock.
On your turn you ask the opponent for a rank you hold >=1 of:
  - opponent has some -> gives ALL of that rank; you go again (same turn).
  - opponent has none -> "Go Fish": draw one from stock (if any); turn passes.
Completing a book (all 4 of a rank) sets it aside. Game ends when all 13
books are formed; most books wins. 13 is odd so draws are impossible.

Two policies:
  - "random": ask for a uniformly random rank currently held.
  - "john": ask for the rank held the most of (tie -> lowest rank), deterministic,
            no opponent-card tracking beyond public info.

Seat 0 always moves first, exposing any first-move seat advantage.
A "turn" is counted per ask/decision the mover makes.
"""

import json
import random
from collections import Counter


def choose_ask(hand, policy):
    held = [r for r in hand if hand[r] > 0]
    if not held:
        return None
    if policy == "random":
        return random.choice(held)
    # john: most held, ties broken by lowest rank
    return max(held, key=lambda r: (hand[r], -r))


def go_fish_game(policy):
    deck = [r for r in range(13) for _ in range(4)]
    random.shuffle(deck)
    hands = [Counter(deck[0:7]), Counter(deck[7:14])]
    stock = deck[14:]
    books = [0, 0]

    def harvest(p):
        for r in list(hands[p]):
            if hands[p][r] >= 4:
                del hands[p][r]
                books[p] += 1

    # rare: dealt books
    harvest(0)
    harvest(1)

    turn = 0
    turns = 0
    guard = 0
    while books[0] + books[1] < 13 and guard < 100000:
        guard += 1
        turns += 1
        p, opp = turn, 1 - turn

        # empty hand: draw one to keep playing, else pass
        if sum(hands[p].values()) == 0:
            if stock:
                hands[p][stock.pop()] += 1
                harvest(p)
            if sum(hands[p].values()) == 0:
                turn = opp
                continue

        ask = choose_ask(hands[p], policy)
        if ask is None:
            turn = opp
            continue

        if hands[opp].get(ask, 0) > 0:
            n = hands[opp][ask]
            del hands[opp][ask]
            hands[p][ask] += n
            harvest(p)
            # successful ask -> same player goes again (turn unchanged)
        else:
            if stock:
                hands[p][stock.pop()] += 1
                harvest(p)
            turn = opp

    seat1 = 1 if books[0] > books[1] else 0
    return books, turns, seat1


def run(policy, N):
    seat1_wins = seat2_wins = 0
    total_turns = 0
    for _ in range(N):
        books, turns, seat1 = go_fish_game(policy)
        total_turns += turns
        if books[0] > books[1]:
            seat1_wins += 1
        else:
            seat2_wins += 1
    return {
        "game": "go_fish",
        "policy": policy,
        "N": N,
        "seat1_wins": seat1_wins,
        "seat2_wins": seat2_wins,
        "seat1_win_pct": round(100 * seat1_wins / N, 2),
        "seat2_win_pct": round(100 * seat2_wins / N, 2),
        "avg_turns": round(total_turns / N, 3),
    }


if __name__ == "__main__":
    N = 500
    results = [run("random", N), run("john", N)]
    print(json.dumps(results, indent=2))
