"""
Cheat / Bullshit simulator (stdlib only, self-contained).

Rules implemented:
  - 4 players, one standard 52-card deck dealt evenly (13 each). Only RANK
    matters (A,2,...,K -> indices 0..12); suits are ignored.
  - The demanded rank advances in strict ascending order around the table,
    cycling A,2,3,...,K,A,2,... regardless of who is playing.
  - On your turn you play 1+ cards FACE DOWN and announce them as the demanded
    rank. You may lie (play cards that are not actually that rank).
  - After a play, any other player may call "Cheat!" on that (most recent)
    play. Reveal: if the player lied (any played card != claimed rank) the
    liar takes the whole pile; if truthful, the challenger takes the pile.
  - First player to empty their hand, surviving any challenge on that final
    play, wins.

Policies:
  - "random": uniform-ish among legal actions. On a turn, if the player holds
    the demanded rank it flips a fair coin between playing truthfully and
    lying (else it is forced to lie); truthful = a random nonempty subset of
    matching cards, lie = 1..3 random cards from hand. Each opponent, in
    clockwise order, independently challenges with probability 0.5; first to
    do so resolves.
  - "john": honest competent everyman, identical in every seat. Never lies:
    plays ALL cards he holds of the demanded rank (truthful, maximal shedding).
    If he holds NONE of the demanded rank he is FORCED to bluff exactly one
    card -- his lowest-ranked card, chosen deterministically. This forced
    single-card bluff is John's ONLY dishonesty. He challenges by a fixed
    impossibility rule: if claimed_count + (his own count of that rank) > 4,
    the claim is impossible, so he challenges. First eligible seat (clockwise)
    challenges; ties -> lowest seat index.

SIMPLIFICATIONS (noted):
  - No "four-of-a-kind clears the pile" rule.
  - After a challenge the turn simply advances one seat clockwise and the rank
    keeps incrementing (no rank reset / no loser-restarts-round variant).

Length metric: number of PLAYS (individual face-down plays) until a winner.
"""

import json
import random

NUM_PLAYERS = 4
NUM_RANKS = 13
PLAY_CAP = 5000  # random Cheat runs long; keep cap high per task


def deal():
    deck = [r for r in range(NUM_RANKS) for _ in range(4)]  # 52 cards
    random.shuffle(deck)
    hands = [[] for _ in range(NUM_PLAYERS)]
    for i, c in enumerate(deck):
        hands[i % NUM_PLAYERS].append(c)
    for h in hands:
        h.sort()
    return hands


# ---------------------------------------------------------------- play choice
def random_play(hand, demanded):
    matching = [c for c in hand if c == demanded]
    if matching and random.random() < 0.5:
        k = random.randint(1, len(matching))
        return matching[:k]
    # lie (forced if no matching)
    k = random.randint(1, min(3, len(hand)))
    return random.sample(hand, k)


def john_play(hand, demanded):
    matching = [c for c in hand if c == demanded]
    if matching:
        return list(matching)          # play ALL matching, truthful
    return [min(hand)]                 # forced single-card bluff: lowest card


# ---------------------------------------------------------------- challenge
def random_challenge(hand, claimed_rank, claimed_count):
    return random.random() < 0.5


def john_challenge(hand, claimed_rank, claimed_count):
    own = sum(1 for c in hand if c == claimed_rank)
    return claimed_count + own > 4     # impossible -> challenge


PLAY_FN = {'random': random_play, 'john': john_play}
CHALLENGE_FN = {'random': random_challenge, 'john': john_challenge}


def play_game(policy):
    play_fn = PLAY_FN[policy]
    chal_fn = CHALLENGE_FN[policy]
    hands = deal()
    pile = []            # list of actual ranks
    turn = 0
    rank_idx = 0
    plays = 0

    while plays < PLAY_CAP:
        demanded = rank_idx % NUM_RANKS
        player = turn
        hand = hands[player]

        played = play_fn(hand, demanded)
        for c in played:
            hand.remove(c)
        pile.extend(played)
        claimed_count = len(played)
        lied = any(c != demanded for c in played)
        plays += 1

        # challenge opportunity, clockwise from next seat
        challenger = None
        for step in range(1, NUM_PLAYERS):
            cand = (player + step) % NUM_PLAYERS
            if chal_fn(hands[cand], demanded, claimed_count):
                challenger = cand
                break

        if challenger is not None:
            if lied:
                hands[player].extend(pile)   # liar caught -> takes pile
                hands[player].sort()
            else:
                hands[challenger].extend(pile)  # wrong call -> challenger takes
                hands[challenger].sort()
            pile = []
            # win only if truthful play emptied the hand and survived
            if not lied and len(hands[player]) == 0:
                return player, plays, False
        else:
            if len(hands[player]) == 0:
                return player, plays, False

        turn = (turn + 1) % NUM_PLAYERS
        rank_idx += 1

    return None, plays, True  # capped


def run(policy, N):
    wins = [0] * NUM_PLAYERS
    total_plays = 0
    caps = 0
    for _ in range(N):
        w, plays, capped = play_game(policy)
        if capped:
            caps += 1
        if w is not None:
            wins[w] += 1
        total_plays += plays
    return {
        'game': 'cheat',
        'policy': policy,
        'N': N,
        'wins_per_seat': wins,
        'distribution': ' · '.join(str(x) for x in wins),
        'avg_length_plays': round(total_plays / N, 2),
        'caps': caps,
    }


if __name__ == '__main__':
    results = [run('random', 500), run('john', 500)]
    print(json.dumps(results, indent=2))
