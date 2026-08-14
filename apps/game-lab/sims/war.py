"""Self-contained War simulator (stdlib only).

2 players, 52 cards split 26/26. Each flips top card; higher rank wins both.
Tie -> "war": each places cards face down then flips again; winner takes the
whole pile. Decision-free pure luck (John == random by construction).

War can fail to terminate, so we cap the number of flips (default 10000) and
count games that hit the cap. We report seat1 vs seat2 win counts and avg
flips. On a war, if a player lacks enough cards, they lose the game.
"""

import random
import json

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VAL = {r: i for i, r in enumerate(RANKS, start=2)}
FACE_DOWN = 1  # cards placed face down per player during a war


def make_deck():
    deck = []
    for r in RANKS:
        for _ in range(4):
            deck.append(RANK_VAL[r])
    return deck


def play_game(flip_cap=10000):
    from collections import deque
    deck = make_deck()
    random.shuffle(deck)
    p1 = deque(deck[:26])
    p2 = deque(deck[26:])

    flips = 0
    while p1 and p2 and flips < flip_cap:
        pot = []
        # resolve one battle (possibly with wars)
        while True:
            flips += 1
            if flips >= flip_cap:
                break
            c1 = p1.popleft()
            c2 = p2.popleft()
            pot.append(c1)
            pot.append(c2)
            if c1 > c2:
                random.shuffle(pot)
                p1.extend(pot)
                break
            elif c2 > c1:
                random.shuffle(pot)
                p2.extend(pot)
                break
            else:
                # war: each puts FACE_DOWN cards down, then flip again
                for _ in range(FACE_DOWN):
                    if p1:
                        pot.append(p1.popleft())
                    if p2:
                        pot.append(p2.popleft())
                if not p1 or not p2:
                    # cannot sustain the war -> loser is the one who ran out
                    break
                # loop continues for another flip
        if not p1 or not p2:
            break

    capped = flips >= flip_cap
    if not p1:
        winner = 2
    elif not p2:
        winner = 1
    else:
        winner = None  # capped with both still holding cards
    return winner, capped, flips


def run(policy, N):
    # War is decision-free: 'random' and 'john' are identical by construction.
    seat1_wins = 0
    seat2_wins = 0
    caps = 0
    total_flips = 0
    for _ in range(N):
        winner, capped, flips = play_game()
        total_flips += flips
        if capped:
            caps += 1
        if winner == 1:
            seat1_wins += 1
        elif winner == 2:
            seat2_wins += 1
    return {
        'game': 'war',
        'policy': policy,
        'games': N,
        'seat1_wins': seat1_wins,
        'seat2_wins': seat2_wins,
        'cap_hits': caps,
        'cap_pct': round(100.0 * caps / N, 2),
        'avg_flips': round(total_flips / N, 2),
        'note': 'john == random (decision-free)',
    }


if __name__ == '__main__':
    out = {p: run(p, 500) for p in ('random', 'john')}
    print(json.dumps(out, indent=2))
