"""
Liar's Dice / Perudo simulator (stdlib only, self-contained).

Rules implemented (core Perudo):
  - 4 players, 5 dice each, hidden under cups.
  - A bid = (quantity, face) claiming AT LEAST `quantity` dice showing `face`
    across ALL dice on the table.
  - Ones (aces) are WILD: they count as any face when tallying (except when the
    bid itself is on face 1, where only actual ones count).
  - Play goes clockwise. Each player must either RAISE the standing bid
    (strictly higher quantity, OR same quantity with a strictly higher face)
    or CHALLENGE ("Dudo").
  - On a challenge, all dice are revealed and the claimed face is counted
    (including wild ones). If the actual count >= bid quantity the bid was
    good -> the CHALLENGER loses a die; otherwise -> the BIDDER loses a die.
  - Losing your last die knocks you out. Last player standing wins.

SIMPLIFICATIONS (noted per task):
  - Palifico and Calza (exact-call) rounds are NOT implemented.
  - Ace bids are treated with ordinary ordering (no "aces worth double /
    half quantity" special bidding rule). Aces are still wild for COUNTING.
  - Bid ordering is plain lexicographic on (quantity, face) with faces 1..6.

Length metric: number of ROUNDS, where one round == one full bidding
sequence terminated by a challenge (i.e. one die-loss event).
"""

import json
import random

NUM_PLAYERS = 4
DICE_PER_PLAYER = 5
ROUND_CAP = 2000  # safety cap on rounds per game


def roll(n):
    return [random.randint(1, 6) for _ in range(n)]


def count_face(all_dice, face):
    """Count dice matching `face`, ones wild (unless face == 1)."""
    c = 0
    for d in all_dice:
        if d == face or (face != 1 and d == 1):
            c += 1
    return c


def bids_above(cur, total):
    """All legal raises above `cur`=(q,f) with quantity up to `total`, ascending."""
    cq, cf = cur
    out = []
    for q in range(1, total + 1):
        for f in range(1, 7):
            if q > cq or (q == cq and f > cf):
                out.append((q, f))
    return out


def expected_count(face, my_dice, total_dice):
    """John's expected total count of `face` given his own dice known exactly."""
    my_match = sum(1 for d in my_dice if d == face or (face != 1 and d == 1))
    unknown = total_dice - len(my_dice)
    p = (1.0 / 6.0) if face == 1 else (2.0 / 6.0)
    return my_match + unknown * p


# ---------------------------------------------------------------- policies
def random_action(cur, my_dice, total_dice):
    """Return ('challenge', None) or ('bid', (q,f))."""
    if cur is None:
        # must open; pick a uniform-ish legal opening bid
        q = random.randint(1, total_dice)
        f = random.randint(1, 6)
        return ('bid', (q, f))
    # 50/50 challenge vs raise
    raises = bids_above(cur, total_dice)
    if not raises or random.random() < 0.5:
        return ('challenge', None)
    return ('bid', random.choice(raises))


def john_action(cur, my_dice, total_dice):
    """Honest, competent: minimal expectation-supported raise; challenge when
    standing bid quantity exceeds expected count."""
    if cur is not None:
        cq, cf = cur
        if cq > expected_count(cf, my_dice, total_dice):
            return ('challenge', None)
    base = cur if cur is not None else (0, 0)
    for (q, f) in bids_above(base, total_dice):
        if q <= expected_count(f, my_dice, total_dice):
            return ('bid', (q, f))
    # nothing supported
    if cur is None:
        # forced to open: pick strongest supported-ish (best expected face)
        best_f = max(range(1, 7), key=lambda f: expected_count(f, my_dice, total_dice))
        return ('bid', (1, best_f))
    return ('challenge', None)


POLICIES = {'random': random_action, 'john': john_action}


def play_game(policy_fn):
    dice = [DICE_PER_PLAYER] * NUM_PLAYERS  # dice remaining per player
    starter = 0
    rounds = 0
    capped = False

    def active_players():
        return [p for p in range(NUM_PLAYERS) if dice[p] > 0]

    while len(active_players()) > 1:
        if rounds >= ROUND_CAP:
            capped = True
            break
        rounds += 1

        total_dice = sum(dice)
        hands = {p: roll(dice[p]) for p in active_players()}
        act = active_players()
        # ensure starter is active
        if starter not in act:
            starter = act[0]

        order = act[act.index(starter):] + act[:act.index(starter)]
        cur_bid = None
        idx = 0
        loser = None
        # bidding loop
        while True:
            player = order[idx % len(order)]
            kind, payload = policy_fn(cur_bid, hands[player], total_dice)
            if kind == 'challenge' and cur_bid is not None:
                # resolve against previous bidder
                bidder = order[(idx - 1) % len(order)]
                all_dice = [d for p in act for d in hands[p]]
                q, f = cur_bid
                actual = count_face(all_dice, f)
                if actual >= q:
                    loser = player      # challenge failed
                else:
                    loser = bidder      # bid was a lie
                break
            else:
                if kind == 'challenge':
                    # cannot challenge with no bid; force an opening bid
                    kind, payload = ('bid', (1, random.randint(1, 6)))
                cur_bid = payload
                idx += 1

        dice[loser] -= 1
        starter = loser if dice[loser] > 0 else None
        if starter is None:
            # next active player clockwise from loser
            for step in range(1, NUM_PLAYERS + 1):
                cand = (loser + step) % NUM_PLAYERS
                if dice[cand] > 0:
                    starter = cand
                    break

    winner = active_players()[0] if active_players() and not capped else None
    if capped and active_players():
        # pick current leader as winner for accounting if capped
        winner = max(active_players(), key=lambda p: dice[p])
    return winner, rounds, capped


def run(policy, N):
    policy_fn = POLICIES[policy]
    wins = [0] * NUM_PLAYERS
    total_rounds = 0
    caps = 0
    for _ in range(N):
        w, rounds, capped = play_game(policy_fn)
        if capped:
            caps += 1
        if w is not None:
            wins[w] += 1
        total_rounds += rounds
    return {
        'game': 'liars_dice',
        'policy': policy,
        'N': N,
        'wins_per_seat': wins,
        'distribution': ' · '.join(str(x) for x in wins),
        'avg_length_rounds': round(total_rounds / N, 2),
        'caps': caps,
    }


if __name__ == '__main__':
    results = [run('random', 500), run('john', 500)]
    print(json.dumps(results, indent=2))
