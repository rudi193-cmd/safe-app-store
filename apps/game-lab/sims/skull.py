"""Skull (4 players) self-contained simulator. Stdlib only.

Each player owns 4 discs: 3 roses + 1 skull. A round: players place discs
face-down on their own stack; once everyone active has >=1 placed, a player may
open bidding a number of face-up rose-flips. Others raise or pass; last bidder
is the Challenger, who must flip ALL their own stack first (top-down) then
opponents' top discs (choice of stack). Reaching the bid in roses = success
(+1 point); flipping any skull = fail, discard one own disc (0 discs => out).
First to TWO successful challenges wins, or last player standing.

Two policies:
  - "random": pick uniformly among legal concrete moves.
  - "john":   identical honest everyman in every seat. Never bluffs: places
              roses (keeps his skull in hand until forced), only ever bids what
              his own placed roses support, raises minimally, passes rather than
              over-commit. Deterministic, ties by lowest seat index.

run(policy, N) plays N games; __main__ runs BOTH at N=500 and prints JSON.
"""
import random
import json


class Player:
    def __init__(self, idx):
        self.idx = idx
        self.discs = ["rose", "rose", "rose", "skull"]  # owned discs
        self.points = 0
        self.stack = []   # placed this round (top = last)
        self.hand = []    # discs available to place this round

    def active(self):
        return len(self.discs) > 0


class SkullGame:
    def __init__(self, policy, max_rounds=500):
        self.policy = policy
        self.max_rounds = max_rounds
        self.players = [Player(i) for i in range(4)]
        self.start = 0
        self.rounds = 0

    def active_players(self):
        return [p for p in self.players if p.active()]

    def active_order(self):
        """Active players ordered by seat starting at self.start."""
        out = []
        for k in range(4):
            p = self.players[(self.start + k) % 4]
            if p.active():
                out.append(p)
        return out

    # ---- disc loss -----------------------------------------------
    def discard_one(self, p):
        if self.policy == "random":
            p.discs.pop(random.randrange(len(p.discs)))
        else:
            # john: keep his skull (defensive), shed a rose first
            if "rose" in p.discs:
                p.discs.remove("rose")
            else:
                p.discs.remove("skull")

    # ---- placement / bidding decisions ---------------------------
    def own_roses(self, p):
        return p.stack.count("rose")

    def decide_open(self, p, bidding_allowed, total):
        """Pre-bid turn. Return ('place', disc) or ('bid', n)."""
        can_place = len(p.hand) > 0
        if self.policy == "random":
            actions = []
            if can_place:
                actions.append(("place", None))
            if bidding_allowed:
                for n in range(1, total + 1):
                    actions.append(("bid", n))
            if not actions:                       # safety
                return ("place", None) if can_place else ("bid", 1)
            choice = random.choice(actions)
            if choice[0] == "place":
                return ("place", random.choice(p.hand))
            return choice
        # john: place a rose while able and no bid pressure; else open minimally
        if can_place and "rose" in p.hand:
            return ("place", "rose")
        if bidding_allowed and self.own_roses(p) >= 1:
            return ("bid", 1)
        if can_place:                              # forced to place skull
            return ("place", p.hand[0])
        return ("bid", 1)                          # forced, unsafe (rare)

    def decide_bid(self, p, current_bid, total):
        """Bidding phase. Return ('pass', None) or ('bid', n)."""
        if self.policy == "random":
            actions = [("pass", None)]
            for n in range(current_bid + 1, total + 1):
                actions.append(("bid", n))
            return random.choice(actions)
        # john: minimal safe raise, only what his own placed roses support
        safe = self.own_roses(p)
        if current_bid + 1 <= safe and current_bid + 1 <= total:
            return ("bid", current_bid + 1)
        return ("pass", None)

    def choose_flip_target(self, challenger, targets):
        if self.policy == "random":
            return random.choice(targets)
        return sorted(targets, key=lambda q: q.idx)[0]

    # ---- one round -----------------------------------------------
    def play_round(self):
        self.rounds += 1
        active = self.active_order()
        for p in active:
            p.stack = []
            p.hand = list(p.discs)

        bidding_started = False
        current_bid = 0
        current_bidder = None
        passed = set()
        total = 0
        pos = 0
        guard = 0

        while True:
            guard += 1
            if guard > 100000:
                return  # safety, should never trigger
            p = active[pos % len(active)]

            if not bidding_started:
                everyone_placed = all(len(q.stack) >= 1 for q in active)
                total_table = sum(len(q.stack) for q in active)
                act = self.decide_open(p, everyone_placed, total_table)
                if act[0] == "place":
                    if p.hand:
                        disc = act[1] if act[1] in p.hand else p.hand[0]
                        p.hand.remove(disc)
                        p.stack.append(disc)
                    pos += 1
                    continue
                else:
                    bidding_started = True
                    total = sum(len(q.stack) for q in active)
                    current_bid = min(act[1], total)
                    current_bidder = p
                    passed = set()
                    pos += 1
                    continue
            else:
                if p in passed or p is current_bidder:
                    # check for a settled auction
                    remaining = [q for q in active if q not in passed]
                    if len(remaining) <= 1:
                        break
                    pos += 1
                    continue
                act = self.decide_bid(p, current_bid, total)
                if act[0] == "pass":
                    passed.add(p)
                else:
                    current_bid = act[1]
                    current_bidder = p
                remaining = [q for q in active if q not in passed]
                if len(remaining) <= 1:
                    break
                pos += 1
                continue

        challenger = current_bidder
        if challenger is None:
            return
        self.resolve(challenger, current_bid, active)

    def resolve(self, challenger, bid, active):
        need = bid
        found = 0
        failed = False
        # must flip ALL own first (top-down)
        while challenger.stack and found < need:
            disc = challenger.stack.pop()
            if disc == "skull":
                failed = True
                break
            found += 1
        # then opponents' top discs
        if not failed:
            while found < need:
                targets = [q for q in active
                           if q is not challenger and q.stack]
                if not targets:
                    failed = True
                    break
                q = self.choose_flip_target(challenger, targets)
                disc = q.stack.pop()
                if disc == "skull":
                    failed = True
                    break
                found += 1

        if not failed and found >= need:
            challenger.points += 1
            self.start = challenger.idx            # winner starts next round
        else:
            self.discard_one(challenger)
            if challenger.active():
                self.start = challenger.idx
            else:
                # next active seat after the eliminated challenger
                nxt = challenger.idx
                for k in range(1, 5):
                    cand = self.players[(challenger.idx + k) % 4]
                    if cand.active():
                        nxt = cand.idx
                        break
                self.start = nxt

    def run_game(self):
        while len(self.active_players()) > 1 and self.rounds < self.max_rounds:
            self.play_round()
            winners = [p for p in self.players if p.points >= 2]
            if winners:
                return winners[0].idx, self.rounds, False
        active = self.active_players()
        if len(active) == 1 and self.rounds < self.max_rounds:
            return active[0].idx, self.rounds, False
        return None, self.rounds, True             # capped / draw


def run(policy, N):
    wins = [0, 0, 0, 0]
    caps = 0
    total_len = 0
    for _ in range(N):
        g = SkullGame(policy)
        w, length, capped = g.run_game()
        total_len += length
        if capped or w is None:
            caps += 1
        else:
            wins[w] += 1
    return {
        "game": "skull",
        "policy": policy,
        "seats": 4,
        "N": N,
        "wins": wins,
        "caps": caps,
        "distribution": " · ".join(str(w) for w in wins),
        "avg_len": round(total_len / N, 2),
    }


if __name__ == "__main__":
    out = {"random": run("random", 500), "john": run("john", 500)}
    print(json.dumps(out, indent=2))
