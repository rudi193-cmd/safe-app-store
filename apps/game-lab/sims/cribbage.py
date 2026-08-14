"""Self-contained 121-point 2-player Cribbage simulator (stdlib only).

Cards are (rank, suit) with rank 1..13 (A=1 .. J=11,Q=12,K=13), suit 0..3.
Count value = min(rank, 10). Run order uses rank directly.

Two policies:
  - "random": random legal discard + random legal peg play.
  - "john": keep the highest-scoring 4 cards (hand-only proxy, ignores crib
            ownership and starter) and peg greedily for immediate points
            (tie -> lowest count-value card).

Real scoring implemented for the PLAY (15/pair/run/31/go/last) and the SHOW
(15s/pairs/runs/flush/nobs; crib flush requires all 5 same suit).

Dealer alternates each hand; dealer's crib is the structural seat advantage.
First to 121 wins (checked immediately whenever points are pegged/counted,
non-dealer counting first in the show). A "skunk" = loser finished < 91.
"""

import json
import random
from itertools import combinations
from collections import Counter


def val(rank):
    return min(rank, 10)


# ---------------------------------------------------------------- SHOW scoring
def score_show(hand, starter, is_crib=False):
    """Score a 4-card hand plus the starter (5 cards)."""
    cards = list(hand) + [starter]
    ranks = [c[0] for c in cards]
    vals = [val(r) for r in ranks]
    s = 0
    # fifteens
    for r in range(2, 6):
        for comb in combinations(vals, r):
            if sum(comb) == 15:
                s += 2
    # pairs
    for a, b in combinations(ranks, 2):
        if a == b:
            s += 2
    # runs
    cnt = Counter(ranks)
    dis = sorted(cnt)
    i = 0
    while i < len(dis):
        j = i
        while j + 1 < len(dis) and dis[j + 1] == dis[j] + 1:
            j += 1
        L = j - i + 1
        if L >= 3:
            m = 1
            for k in range(i, j + 1):
                m *= cnt[dis[k]]
            s += L * m
        i = j + 1
    # flush
    hsuits = [c[1] for c in hand]
    if len(set(hsuits)) == 1:
        if starter[1] == hsuits[0]:
            s += 5
        elif not is_crib:
            s += 4
    # nobs (jack in hand matching starter suit)
    for c in hand:
        if c[0] == 11 and c[1] == starter[1]:
            s += 1
    return s


def score_four(cards):
    """Hand-only score of exactly the kept cards (proxy for discard choice)."""
    ranks = [c[0] for c in cards]
    vals = [val(r) for r in ranks]
    s = 0
    for r in range(2, len(cards) + 1):
        for comb in combinations(vals, r):
            if sum(comb) == 15:
                s += 2
    for a, b in combinations(ranks, 2):
        if a == b:
            s += 2
    cnt = Counter(ranks)
    dis = sorted(cnt)
    i = 0
    while i < len(dis):
        j = i
        while j + 1 < len(dis) and dis[j + 1] == dis[j] + 1:
            j += 1
        L = j - i + 1
        if L >= 3:
            m = 1
            for k in range(i, j + 1):
                m *= cnt[dis[k]]
            s += L * m
        i = j + 1
    suits = [c[1] for c in cards]
    if len(set(suits)) == 1:
        s += len(cards)
    return s


# ---------------------------------------------------------------- PLAY scoring
def peg_score(seq, total):
    """Score the just-played card given the current run pile and running total."""
    pts = 0
    if total == 15:
        pts += 2
    if total == 31:
        pts += 2
    n = len(seq)
    # pairs / trips / quads via trailing equal ranks
    k = 1
    while k < n and seq[-1 - k][0] == seq[-1][0]:
        k += 1
    pts += (0, 0, 2, 6, 12)[k] if k <= 4 else 0
    # runs: longest trailing set of >=3 cards forming a consecutive run
    for L in range(min(n, 7), 2, -1):
        tail = sorted(c[0] for c in seq[-L:])
        if len(set(tail)) == L and tail[-1] - tail[0] == L - 1:
            pts += L
            break
    return pts


def choose_peg(legal, seq, total, policy):
    if policy == "random":
        return random.choice(legal)
    best, bestpts = None, -1
    for c in sorted(legal, key=lambda c: val(c[0])):
        p = peg_score(seq + [c], total + val(c[0]))
        if p > bestpts:
            bestpts, best = p, c
    return best


def play_phase(h0, h1, dealer, policy, scores):
    """Run the pegging. Updates scores in place; returns winner seat or None."""
    hands = [list(h0), list(h1)]
    turn = 1 - dealer          # non-dealer leads
    total = 0
    seq = []
    gos = 0
    last = None

    def award(p, pts):
        scores[p] += pts
        return scores[p] >= 121

    while hands[0] or hands[1]:
        legal = [c for c in hands[turn] if val(c[0]) + total <= 31]
        if not legal:
            gos += 1
            if gos == 2:
                if last is not None and award(last, 1):
                    return last
                total, seq, gos = 0, [], 0
            turn = 1 - turn
            continue
        gos = 0
        card = choose_peg(legal, seq, total, policy)
        hands[turn].remove(card)
        total += val(card[0])
        seq.append(card)
        last = turn
        pts = peg_score(seq, total)
        if pts and award(turn, pts):
            return turn
        if total == 31:
            total, seq, gos = 0, [], 0
        turn = 1 - turn

    if seq and last is not None and award(last, 1):  # last-card point
        return last
    return None


# ---------------------------------------------------------------- discard
def choose_discard(hand, policy):
    if policy == "random":
        keep = random.sample(hand, 4)
    else:
        best, bs = None, -1
        for comb in combinations(hand, 4):
            sc = score_four(list(comb))
            if sc > bs:
                bs, best = sc, comb
        keep = list(best)
    disc = [c for c in hand if c not in keep]
    return keep, disc


# ---------------------------------------------------------------- one hand
def play_hand(scores, dealer, policy):
    """Play one deal. Updates scores; returns winner seat or None."""
    deck = [(r, s) for s in range(4) for r in range(1, 14)]
    random.shuffle(deck)
    h = [deck[0:6], deck[6:12]]
    starter = deck[12]

    keep = [None, None]
    crib = []
    for p in range(2):
        k, d = choose_discard(h[p], policy)
        keep[p] = k
        crib += d

    # his heels: starter is a Jack -> dealer pegs 2
    if starter[0] == 11:
        scores[dealer] += 2
        if scores[dealer] >= 121:
            return dealer

    w = play_phase(keep[0], keep[1], dealer, policy, scores)
    if w is not None:
        return w

    nd = 1 - dealer
    scores[nd] += score_show(keep[nd], starter, False)
    if scores[nd] >= 121:
        return nd
    scores[dealer] += score_show(keep[dealer], starter, False)
    if scores[dealer] >= 121:
        return dealer
    scores[dealer] += score_show(crib, starter, True)
    if scores[dealer] >= 121:
        return dealer
    return None


# ---------------------------------------------------------------- run N games
def run(policy, N):
    d_wins = nd_wins = 0
    total_hands = 0
    skunks = 0
    for _ in range(N):
        scores = [0, 0]
        dealer = 0 if random.random() < 0.5 else 1
        hands = 0
        winner = None
        win_is_dealer = False
        while winner is None and hands < 500:
            hands += 1
            w = play_hand(scores, dealer, policy)
            if w is not None:
                winner = w
                win_is_dealer = (w == dealer)
            else:
                dealer = 1 - dealer
        total_hands += hands
        if win_is_dealer:
            d_wins += 1
        else:
            nd_wins += 1
        loser = 1 - (winner if winner is not None else 0)
        if scores[loser] < 91:
            skunks += 1
    return {
        "game": "cribbage",
        "policy": policy,
        "N": N,
        "dealer_wins": d_wins,
        "nondealer_wins": nd_wins,
        "dealer_win_pct": round(100 * d_wins / N, 2),
        "nondealer_win_pct": round(100 * nd_wins / N, 2),
        "avg_hands": round(total_hands / N, 3),
        "skunk_pct": round(100 * skunks / N, 2),
    }


if __name__ == "__main__":
    N = 500
    results = [run("random", N), run("john", N)]
    print(json.dumps(results, indent=2))
