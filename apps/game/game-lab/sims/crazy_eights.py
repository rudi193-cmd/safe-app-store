"""Crazy Eights simulator (4 players, 52-card deck).

Deal 5 each, flip 1 to start. Match rank or suit of top discard, or play an
8 (wild -> declare next suit). Can't play -> draw from stock until playable or
stock empty, then pass. First to empty hand wins the hand.

Two policies: "random" and "john".
Reports per-seat win counts, stall%, and average plies per hand.

Stdlib only. Run: python3 crazy_eights.py
"""
import random
import json
from collections import Counter

SUITS = ['C', 'D', 'H', 'S']
RANKS = list(range(2, 15))  # 8 is rank 8 (wild)


def make_deck():
    return [(r, s) for s in SUITS for r in RANKS]


def is_legal(card, top_rank, top_suit, active_suit):
    r, s = card
    if r == 8:
        return True
    # active_suit is the declared/current suit to match
    if s == active_suit:
        return True
    if r == top_rank:
        return True
    return False


def legal_cards(hand, top_rank, top_suit, active_suit):
    return [c for c in hand if is_legal(c, top_rank, top_suit, active_suit)]


def choose_random(legal, hand):
    card = random.choice(legal)
    suit_call = None
    if card[0] == 8:
        suit_call = random.choice(SUITS)
    return card, suit_call


def choose_john(legal, hand):
    # Play a matching non-8 when possible (save 8s). Deterministic ties: lowest
    # rank then suit order.
    non8 = [c for c in legal if c[0] != 8]
    if non8:
        card = min(non8, key=lambda c: (c[0], SUITS.index(c[1])))
        return card, None
    # must play an 8 (or 8 is the only legal thing)
    card = min(legal, key=lambda c: (c[0], SUITS.index(c[1])))
    # call the suit John holds most of (excluding the 8 being played)
    remaining = [c for c in hand if c != card]
    counts = Counter(c[1] for c in remaining)
    if counts:
        best = max(SUITS, key=lambda s: (counts.get(s, 0), -SUITS.index(s)))
    else:
        best = SUITS[0]
    return card, best


CHOOSE_FN = {'random': choose_random, 'john': choose_john}


def play_hand(policy):
    """Return (winner_seat or None if stalled, plies)."""
    choose = CHOOSE_FN[policy]
    deck = make_deck()
    random.shuffle(deck)
    hands = [deck[i * 5:(i + 1) * 5] for i in range(4)]
    idx = 20
    stock = deck[idx:]
    # flip first card. If it's an 8, the starting active suit is that card's suit.
    top = stock.pop(0)
    discard_top_rank, discard_top_suit = top
    active_suit = discard_top_suit

    plies = 0
    turn = 0
    MAX_PLIES = 2000  # sane cap
    stalled = False
    consecutive_passes = 0

    while True:
        if plies >= MAX_PLIES:
            stalled = True
            break
        hand = hands[turn]
        legal = legal_cards(hand, discard_top_rank, discard_top_suit, active_suit)
        if not legal:
            # draw until playable or stock empty
            drew_playable = False
            while stock:
                c = stock.pop()
                hand.append(c)
                if is_legal(c, discard_top_rank, discard_top_suit, active_suit):
                    drew_playable = True
                    break
            if drew_playable:
                legal = legal_cards(hand, discard_top_rank, discard_top_suit, active_suit)
            else:
                # can't play, pass
                plies += 1
                consecutive_passes += 1
                turn = (turn + 1) % 4
                # stock empty + all 4 seats passed in a row -> nobody can move
                if consecutive_passes >= 4:
                    stalled = True
                    break
                continue

        consecutive_passes = 0
        card, suit_call = choose(legal, hand)
        hand.remove(card)
        discard_top_rank, discard_top_suit = card
        if card[0] == 8:
            active_suit = suit_call if suit_call else card[1]
        else:
            active_suit = card[1]
        plies += 1

        if len(hand) == 0:
            return turn, plies

        turn = (turn + 1) % 4

        # Stall detection: stock empty and no player has a legal move.
        if not stock:
            any_move = False
            for s in range(4):
                if legal_cards(hands[s], discard_top_rank, discard_top_suit, active_suit):
                    any_move = True
                    break
            if not any_move:
                stalled = True
                break

    return None, plies


def run(policy, N):
    wins = [0, 0, 0, 0]
    stalls = 0
    total_plies = 0
    capped = 0
    for _ in range(N):
        winner, plies = play_hand(policy)
        total_plies += plies
        if winner is None:
            stalls += 1
            if plies >= 2000:
                capped += 1
        else:
            wins[winner] += 1
    return {
        'game': 'crazy_eights',
        'policy': policy,
        'N': N,
        'seat_wins': wins,
        'stall_pct': round(100.0 * stalls / N, 2),
        'avg_plies': round(total_plies / N, 2),
        'capped_hands': capped,
    }


if __name__ == '__main__':
    results = []
    for policy in ['random', 'john']:
        results.append(run(policy, 500))
    print(json.dumps(results, indent=2))
