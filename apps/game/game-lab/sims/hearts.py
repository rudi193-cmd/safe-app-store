"""Hearts simulator (4 players, standard rules).

Two policies: "random" and "john".
Play hands until someone reaches 100; lowest score wins.
Reports per-seat win counts, tie%, and average hands per game.

Stdlib only. Run: python3 hearts.py
"""
import random
import json

# Card representation: (rank, suit)
# rank: 2..14 (11=J,12=Q,13=K,14=A); suit: 'C','D','H','S'
SUITS = ['C', 'D', 'H', 'S']
RANKS = list(range(2, 15))
QUEEN_SPADES = (12, 'S')
TWO_CLUBS = (2, 'C')


def make_deck():
    return [(r, s) for s in SUITS for r in RANKS]


def card_points(card):
    r, s = card
    if s == 'H':
        return 1
    if card == QUEEN_SPADES:
        return 13
    return 0


def deal(deck):
    random.shuffle(deck)
    return [sorted(deck[i * 13:(i + 1) * 13]) for i in range(4)]


# ---------- Passing ----------

def pass_direction(hand_number):
    # 0 left, 1 right, 2 across, 3 no-pass, cycle
    return hand_number % 4


def target_seat(seat, direction):
    if direction == 0:      # left (+1)
        return (seat + 1) % 4
    if direction == 1:      # right (-1)
        return (seat - 1) % 4
    if direction == 2:      # across (+2)
        return (seat + 2) % 4
    return seat             # no-pass


def choose_pass_random(hand):
    return random.sample(hand, 3)


def john_danger(card):
    """Higher = more dangerous to hold. John passes his 3 most dangerous."""
    r, s = card
    if card == QUEEN_SPADES:
        return 1000
    if s == 'S' and r >= 13:   # A,K spades: could be forced to take the Q
        return 500 + r
    if s == 'H':
        return 100 + r
    return r  # otherwise high cards are more dangerous


def choose_pass_john(hand):
    ranked = sorted(hand, key=john_danger, reverse=True)
    return ranked[:3]


# ---------- Playing ----------

def legal_plays(hand, trick, hearts_broken, first_trick):
    """trick: list of (seat, card) already played this trick."""
    leading = len(trick) == 0
    if leading:
        if first_trick:
            # 2 of clubs must lead
            if TWO_CLUBS in hand:
                return [TWO_CLUBS]
        if not hearts_broken:
            non_hearts = [c for c in hand if c[1] != 'H']
            if non_hearts:
                return non_hearts
            # only hearts left -> must lead hearts
            return list(hand)
        return list(hand)
    else:
        lead_suit = trick[0][1][1]
        follow = [c for c in hand if c[1] == lead_suit]
        if follow:
            return follow
        # void in lead suit
        if first_trick:
            # no hearts or Q on first trick unless no choice
            safe = [c for c in hand if card_points(c) == 0]
            if safe:
                return safe
            return list(hand)
        return list(hand)


def play_random(legal, trick, hand):
    return random.choice(legal)


def play_john(legal, trick, hand):
    leading = len(trick) == 0
    if leading:
        # Lead lowest card, prefer non-point suits, avoid leading into Q spade risk mildly.
        # Deterministic: lowest rank; ties by suit order.
        return min(legal, key=lambda c: (c[0], SUITS.index(c[1])))
    lead_suit = trick[0][1][1]
    # Determine if we're following suit
    if all(c[1] == lead_suit for c in legal):
        # Following suit. Is Q spades or high cards already in trick?
        cards_in_trick = [c for (_, c) in trick]
        highest_so_far = max(c[0] for c in cards_in_trick if c[1] == lead_suit)
        # Dump highest card that stays UNDER the current winner if possible (duck),
        # else play lowest to minimize taking.
        under = [c for c in legal if c[0] < highest_so_far]
        if under:
            # play highest safe card that still loses the trick
            return max(under, key=lambda c: c[0])
        # can't duck -> play lowest to save high cards
        return min(legal, key=lambda c: c[0])
    else:
        # Void: shed most dangerous card (Q spades, high hearts, high spades).
        return max(legal, key=john_danger)


PLAY_FN = {'random': play_random, 'john': play_john}
PASS_FN = {'random': choose_pass_random, 'john': choose_pass_john}


def play_hand(hands, policy):
    """Play one 13-trick hand. Returns list of 4 raw point totals (before shoot adj)."""
    play_fn = PLAY_FN[policy]
    hearts_broken = False
    # find who has 2 of clubs
    leader = next(i for i in range(4) if TWO_CLUBS in hands[i])
    points = [0, 0, 0, 0]
    taken_hearts = [0, 0, 0, 0]
    taken_q = [False, False, False, False]

    for trick_num in range(13):
        first_trick = (trick_num == 0)
        trick = []
        for k in range(4):
            seat = (leader + k) % 4
            legal = legal_plays(hands[seat], trick, hearts_broken, first_trick)
            card = play_fn(legal, trick, hands[seat])
            hands[seat].remove(card)
            if card[1] == 'H':
                hearts_broken = True
            trick.append((seat, card))
        # determine winner
        lead_suit = trick[0][1][1]
        winner_seat, _ = max(
            (t for t in trick if t[1][1] == lead_suit),
            key=lambda t: t[1][0])
        trick_pts = sum(card_points(c) for (_, c) in trick)
        points[winner_seat] += trick_pts
        for (_, c) in trick:
            if c[1] == 'H':
                taken_hearts[winner_seat] += 1
            if c == QUEEN_SPADES:
                taken_q[winner_seat] = True
        leader = winner_seat

    # Shooting the moon: one player took all 13 hearts + Q spades
    for i in range(4):
        if taken_hearts[i] == 13 and taken_q[i]:
            # shoot: others get 26, shooter 0
            return [0 if j == i else 26 for j in range(4)]
    return points


def play_game(policy):
    """Play hands until someone reaches 100. Return (scores, num_hands)."""
    scores = [0, 0, 0, 0]
    hand_number = 0
    MAX_HANDS = 1000  # sane cap
    while max(scores) < 100 and hand_number < MAX_HANDS:
        deck = make_deck()
        hands = deal(deck)
        # passing
        direction = pass_direction(hand_number)
        pass_fn = PASS_FN[policy]
        if direction != 3:
            passed = [pass_fn(hands[s]) for s in range(4)]
            # remove and give
            for s in range(4):
                for c in passed[s]:
                    hands[s].remove(c)
            for s in range(4):
                tgt = target_seat(s, direction)
                hands[tgt].extend(passed[s])
            for s in range(4):
                hands[s].sort()
        hand_pts = play_hand(hands, policy)
        for i in range(4):
            scores[i] += hand_pts[i]
        hand_number += 1
    return scores, hand_number


def run(policy, N):
    wins = [0, 0, 0, 0]
    ties = 0
    total_hands = 0
    capped = 0
    for _ in range(N):
        scores, num_hands = play_game(policy)
        total_hands += num_hands
        if num_hands >= 1000:
            capped += 1
        low = min(scores)
        winners = [i for i in range(4) if scores[i] == low]
        if len(winners) > 1:
            ties += 1
        # award win to lowest seat index among tied winners (single-winner accounting)
        wins[winners[0]] += 1
    return {
        'game': 'hearts',
        'policy': policy,
        'N': N,
        'seat_wins': wins,
        'tie_pct': round(100.0 * ties / N, 2),
        'avg_hands': round(total_hands / N, 2),
        'capped_games': capped,
    }


if __name__ == '__main__':
    results = []
    for policy in ['random', 'john']:
        results.append(run(policy, 500))
    print(json.dumps(results, indent=2))
