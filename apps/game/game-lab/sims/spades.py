"""Self-contained Spades simulator (stdlib only).

4 players in 2 partnerships: N/S = team1 (seats 0,2), E/W = team2 (seats 1,3).
52 cards, 13 each. Each player bids 0..13; team contract = sum of partners'
bids. Play 13 tricks: follow suit if able; spades are trump and cannot be LED
until "broken" (a spade played while void in the led suit). Nil is OMITTED.

Scoring per hand per team:
  make contract  -> +10*bid + 1 per overtrick ("bag")
  every 10 accumulated bags -> -100 (and reset that 10 of the bag counter)
  miss contract  -> -10*bid

First team to 500 wins. A "floor loss" at -200 means the score is floored
(clamped) at -200 -- a team can never drop below it. With uniform-random bids
scores peg to that floor and games essentially never reach 500, so we cap at
300 hands and report the fraction of games that hit the cap with no winner.

Two policies:
  "random": uniform random bid 0..13; random legal card.
  "john":   honest realistic estimator bid; greedy make-contract play, no reads.
            The same competent everyman sits in every seat.
"""

import random
import json

RANKS = {r: i for i, r in enumerate(
    ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'], start=2)}
SUITS = ['C', 'D', 'H', 'S']  # S = spades = trump


def make_deck():
    return [(s, RANKS[r]) for s in SUITS for r in RANKS]


def deal():
    deck = make_deck()
    random.shuffle(deck)
    return [sorted(deck[i * 13:(i + 1) * 13]) for i in range(4)]


# ---------------- Bidding ----------------

def bid_random(hand):
    return random.randint(0, 13)


def bid_john(hand):
    """Honest, sane trick estimator ~ true capacity.

    High-card tricks: aces always; kings if the suit is 2+ long (some backing).
    Spades (trump): honors count, plus length beyond 3 as long-trump tricks.
    Produces per-player expectations averaging near real capacity.
    """
    bysuit = {s: [r for (su, r) in hand if su == s] for s in SUITS}
    bid = 0
    for s in ['C', 'D', 'H']:
        ranks = bysuit[s]
        if RANKS['A'] in ranks:
            bid += 1
        if RANKS['K'] in ranks and len(ranks) >= 2:
            bid += 1
    sp = bysuit['S']
    n = len(sp)
    if RANKS['A'] in sp:
        bid += 1
    if RANKS['K'] in sp and n >= 2:
        bid += 1
    if RANKS['Q'] in sp and n >= 3:
        bid += 1
    if n > 4:
        bid += n - 4  # long trump tricks
    return max(0, min(13, bid))


# ---------------- Play ----------------

def legal_moves(hand, led, spades_broken):
    if led is None:
        # leading: cannot lead spades until broken, unless only spades left
        non_sp = [c for c in hand if c[0] != 'S']
        if not spades_broken and non_sp:
            return non_sp
        return list(hand)
    follow = [c for c in hand if c[0] == led]
    if follow:
        return follow
    return list(hand)


def trick_winner(plays, led):
    """plays: list of (seat, (suit, rank)). Returns winning seat."""
    spades = [(seat, r) for (seat, (s, r)) in plays if s == 'S']
    if spades:
        return max(spades, key=lambda x: x[1])[0]
    in_suit = [(seat, r) for (seat, (s, r)) in plays if s == led]
    return max(in_suit, key=lambda x: x[1])[0]


def would_win(card, plays, led):
    """Would `card` currently be winning against the cards already played?"""
    trial = plays + [(-1, card)]
    return trick_winner(trial, led if led is not None else card[0]) == -1


def choose_card_random(hand, led, plays, spades_broken, need_more):
    return random.choice(legal_moves(hand, led, spades_broken))


def choose_card_john(hand, led, plays, spades_broken, need_more):
    """Greedy: try to win when the team still needs tricks; else duck low."""
    moves = legal_moves(hand, led, spades_broken)
    effective_led = led if led is not None else None

    if led is None:
        # Leading: if we still need tricks, lead our strongest sure-ish card
        # (highest non-spade to preserve trumps); else lead lowest.
        if need_more > 0:
            non_sp = [c for c in moves if c[0] != 'S']
            pool = non_sp if non_sp else moves
            return max(pool, key=lambda c: c[1])
        return min(moves, key=lambda c: (c[0] == 'S', c[1]))

    winners = [c for c in moves if would_win(c, plays, effective_led)]
    if need_more > 0 and winners:
        # win as cheaply as possible
        return min(winners, key=lambda c: (c[0] == 'S', c[1]))
    # can't or shouldn't win: dump the lowest, keep spades if possible
    return min(moves, key=lambda c: (c[0] == 'S', c[1]))


CHOOSERS = {'random': choose_card_random, 'john': choose_card_john}
BIDDERS = {'random': bid_random, 'john': bid_john}


def play_hand(policy):
    """Return (tricks_seat0..3) as list of trick counts and bids list."""
    hands = deal()
    bidder = BIDDERS[policy]
    chooser = CHOOSERS[policy]
    bids = [bidder(hands[s]) for s in range(4)]

    team_bid = [bids[0] + bids[2], bids[1] + bids[3]]
    tricks = [0, 0, 0, 0]
    team_tricks = [0, 0]
    spades_broken = False
    leader = random.randint(0, 3)

    for _ in range(13):
        plays = []
        led = None
        for i in range(4):
            seat = (leader + i) % 4
            team = seat % 2  # 0 -> team1(0,2), 1 -> team2(1,3)
            # tricks the team still needs to make its contract
            need_more = team_bid[team] - team_tricks[team]
            card = chooser(hands[seat], led, plays, spades_broken, need_more)
            if card[0] == 'S' and led != 'S':
                # a spade played off-suit (or led when only spades) breaks spades
                if led is not None or all(c[0] == 'S' for c in hands[seat]):
                    spades_broken = True
            if led is None:
                led = card[0]
                if card[0] == 'S':
                    spades_broken = True
            hands[seat].remove(card)
            plays.append((seat, card))
        w = trick_winner(plays, led)
        tricks[w] += 1
        team_tricks[w % 2] += 1
        leader = w

    return tricks, bids, team_bid, team_tricks


def score_team(bid, made, bags):
    """Return (delta_score, new_bags)."""
    if made >= bid:
        pts = 10 * bid + (made - bid)  # 1 point per bag
        bags += (made - bid)
        penalty = 0
        while bags >= 10:
            penalty += 100
            bags -= 10
        return pts - penalty, bags
    else:
        return -10 * bid, bags


def play_game(policy, hand_cap=300):
    scores = [0, 0]
    bags = [0, 0]
    hands_played = 0
    winner = None
    while hands_played < hand_cap:
        _, _, team_bid, team_tricks = play_hand(policy)
        hands_played += 1
        for t in range(2):
            d, bags[t] = score_team(team_bid[t], team_tricks[t], bags[t])
            scores[t] += d
            # floor: score is clamped at -200, never lower
            if scores[t] < -200:
                scores[t] = -200
        # first to 500 (if both >=500, higher wins)
        if scores[0] >= 500 or scores[1] >= 500:
            if scores[0] == scores[1]:
                continue
            winner = 0 if scores[0] > scores[1] else 1
            break
    capped = winner is None
    return winner, capped, hands_played, scores


def run(policy, N):
    team1_wins = 0
    team2_wins = 0
    caps = 0
    total_hands = 0
    for _ in range(N):
        winner, capped, hands_played, scores = play_game(policy)
        total_hands += hands_played
        if capped:
            caps += 1
        elif winner == 0:
            team1_wins += 1
        else:
            team2_wins += 1
    return {
        'game': 'spades',
        'policy': policy,
        'games': N,
        'team1_wins': team1_wins,
        'team2_wins': team2_wins,
        'team1_pct': round(100.0 * team1_wins / N, 2),
        'team2_pct': round(100.0 * team2_wins / N, 2),
        'cap_hits': caps,
        'cap_pct': round(100.0 * caps / N, 2),
        'avg_hands': round(total_hands / N, 2),
        'note': 'nil omitted',
    }


if __name__ == '__main__':
    out = {p: run(p, 500) for p in ('random', 'john')}
    print(json.dumps(out, indent=2))
