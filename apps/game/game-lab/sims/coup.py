"""Coup (4 players) self-contained simulator. Stdlib only.

Two policies:
  - "random": pick uniformly among legal concrete moves (bluffing allowed).
  - "john":   identical honest everyman in every seat. Never bluffs, never lies;
              only claims/blocks with cards actually held; challenges only when a
              claim is provably impossible from what he can see; deterministic
              value play, ties broken by lowest seat index.

run(policy, N) plays N games and returns a summary dict.
__main__ runs BOTH policies at N=500 and prints a JSON summary.
"""
import random
import json

CARDS = ["Duke", "Assassin", "Captain", "Ambassador", "Contessa"]
# John's keep-preference value (higher = keep, lower = discard first)
VAL = {"Duke": 5, "Contessa": 4, "Captain": 3, "Assassin": 2, "Ambassador": 1}


class Player:
    def __init__(self, idx):
        self.idx = idx
        self.cards = []   # hidden influence cards
        self.coins = 2

    def alive(self):
        return len(self.cards) > 0


class CoupGame:
    def __init__(self, policy, max_turns=1000):
        self.policy = policy
        self.max_turns = max_turns
        self.deck = []
        for c in CARDS:
            self.deck += [c] * 3
        random.shuffle(self.deck)
        self.players = [Player(i) for i in range(4)]
        for p in self.players:
            p.cards = [self.deck.pop(), self.deck.pop()]
        self.revealed = []   # face-up dead cards, visible to all
        self.turns = 0

    # ---- helpers -------------------------------------------------
    def alive_players(self):
        return [p for p in self.players if p.alive()]

    def opponents(self, p):
        return [q for q in self.players if q is not p and q.alive()]

    def others_in_order(self, p):
        """Alive players except p, ordered by seat starting after p."""
        out = []
        for k in range(1, 4):
            q = self.players[(p.idx + k) % 4]
            if q.alive():
                out.append(q)
        return out

    def known_count(self, viewer, card):
        """Copies of `card` viewer can directly see (own hand + dead pile)."""
        return self.revealed.count(card) + viewer.cards.count(card)

    # ---- influence loss / redraw ---------------------------------
    def choose_card_to_lose(self, p):
        if self.policy == "random":
            return random.choice(p.cards)
        # john: discard the least valuable card to keep
        return min(p.cards, key=lambda c: (VAL[c], CARDS.index(c)))

    def lose_influence(self, p):
        if not p.alive():
            return
        card = self.choose_card_to_lose(p)
        p.cards.remove(card)
        self.revealed.append(card)

    def redraw(self, p, card):
        """p revealed `card` on a winning challenge: shuffle it back, draw one."""
        p.cards.remove(card)
        self.deck.append(card)
        random.shuffle(self.deck)
        if self.deck:
            p.cards.append(self.deck.pop())

    # ---- decisions -----------------------------------------------
    def decide_challenge(self, viewer, claimer, card):
        if self.policy == "random":
            return random.random() < 0.5
        # john: challenge only if provably impossible (all 3 copies seen elsewhere)
        return self.known_count(viewer, card) == 3

    def decide_block(self, q, action, actor):
        """Return the card q claims to block with, or None."""
        if self.policy == "random":
            if action == "foreign_aid":
                return "Duke" if random.random() < 0.5 else None
            if action == "steal":
                if random.random() < 0.5:
                    return random.choice(["Captain", "Ambassador"])
                return None
            if action == "assassinate":
                return "Contessa" if random.random() < 0.5 else None
            return None
        # john: honest blocks only, always when able (self defense / value)
        if action == "foreign_aid":
            return "Duke" if "Duke" in q.cards else None
        if action == "steal":
            if "Captain" in q.cards:
                return "Captain"
            if "Ambassador" in q.cards:
                return "Ambassador"
            return None
        if action == "assassinate":
            return "Contessa" if "Contessa" in q.cards else None
        return None

    def choose_keep(self, p, pool, n):
        if self.policy == "random":
            return random.sample(pool, n)
        ordered = sorted(pool, key=lambda c: (-VAL[c], CARDS.index(c)))
        return ordered[:n]

    def john_target(self, opps):
        if not opps:
            return None
        return sorted(opps, key=lambda q: (-len(q.cards), q.idx))[0]

    def choose_action(self, p):
        opps = self.opponents(p)
        if self.policy == "random":
            if p.coins >= 10:
                return ("coup", random.choice(opps))
            moves = [("income", None), ("foreign_aid", None),
                     ("tax", None), ("exchange", None)]
            if p.coins >= 7:
                for t in opps:
                    moves.append(("coup", t))
            if p.coins >= 3:
                for t in opps:
                    moves.append(("assassinate", t))
            for t in opps:
                moves.append(("steal", t))
            return random.choice(moves)
        # john: honest deterministic value
        target = self.john_target(opps)
        if p.coins >= 10:
            return ("coup", target)
        if p.coins >= 7:
            return ("coup", target)
        if "Assassin" in p.cards and p.coins >= 3 and target is not None:
            return ("assassinate", target)
        if "Duke" in p.cards:
            return ("tax", None)
        if "Captain" in p.cards and target is not None:
            return ("steal", target)
        if "Ambassador" in p.cards:
            return ("exchange", None)
        return ("foreign_aid", None)

    # ---- challenge resolution ------------------------------------
    def resolve_challenge(self, claimer, card, challengers):
        """Returns True if the claim stands (unchallenged, or claimer revealed it);
        False if the claim was busted (claimer lost an influence)."""
        for c in challengers:
            if not c.alive() or not claimer.alive():
                continue
            if self.decide_challenge(c, claimer, card):
                if card in claimer.cards:
                    self.lose_influence(c)      # challenger was wrong
                    self.redraw(claimer, card)
                    return True
                else:
                    self.lose_influence(claimer)  # bluff caught
                    return False
        return True

    # ---- actions -------------------------------------------------
    def execute(self, action, p, target):
        if action == "income":
            p.coins += 1
        elif action == "foreign_aid":
            self.foreign_aid(p)
        elif action == "coup":
            self.coup(p, target)
        elif action == "tax":
            self.tax(p)
        elif action == "steal":
            self.steal(p, target)
        elif action == "assassinate":
            self.assassinate(p, target)
        elif action == "exchange":
            self.exchange(p)

    def foreign_aid(self, p):
        for q in self.others_in_order(p):
            claim = self.decide_block(q, "foreign_aid", p)
            if claim:
                stands = self.resolve_challenge(q, "Duke", self.others_in_order(q))
                if stands:
                    return          # blocked, no coins
                p.coins += 2        # block busted -> aid proceeds
                return
        p.coins += 2

    def coup(self, p, target):
        p.coins -= 7
        if target and target.alive():
            self.lose_influence(target)

    def tax(self, p):
        if self.resolve_challenge(p, "Duke", self.others_in_order(p)):
            p.coins += 3

    def steal(self, p, target):
        if target is None or not target.alive():
            return
        if not self.resolve_challenge(p, "Captain", self.others_in_order(p)):
            return
        claim = self.decide_block(target, "steal", p)
        if claim:
            if self.resolve_challenge(target, claim, self.others_in_order(target)):
                return              # steal blocked
        amount = min(2, target.coins)
        target.coins -= amount
        p.coins += amount

    def assassinate(self, p, target):
        p.coins -= 3
        if target is None or not target.alive():
            return
        if not self.resolve_challenge(p, "Assassin", self.others_in_order(p)):
            p.coins += 3            # bluff caught -> action fails, refund
            return
        claim = self.decide_block(target, "assassinate", p)
        if claim:
            if self.resolve_challenge(target, "Contessa", self.others_in_order(target)):
                return              # blocked, coins spent (not refunded)
        # not blocked, or block busted -> assassination lands
        self.lose_influence(target)

    def exchange(self, p):
        if not self.resolve_challenge(p, "Ambassador", self.others_in_order(p)):
            return
        drawn = []
        for _ in range(2):
            if self.deck:
                drawn.append(self.deck.pop())
        pool = list(p.cards) + drawn
        n = len(p.cards)
        keep = self.choose_keep(p, pool, n)
        remaining = list(pool)
        for c in keep:
            remaining.remove(c)
        p.cards = list(keep)
        self.deck.extend(remaining)
        random.shuffle(self.deck)

    # ---- driver --------------------------------------------------
    def play_turn(self, p):
        self.turns += 1
        action, target = self.choose_action(p)
        self.execute(action, p, target)

    def run_game(self):
        cur = 0
        while len(self.alive_players()) > 1 and self.turns < self.max_turns:
            p = self.players[cur]
            if p.alive():
                self.play_turn(p)
            cur = (cur + 1) % 4
        alive = self.alive_players()
        if len(alive) == 1 and self.turns < self.max_turns:
            return alive[0].idx, self.turns, False
        return None, self.turns, True   # capped / draw


def run(policy, N):
    wins = [0, 0, 0, 0]
    caps = 0
    total_len = 0
    for _ in range(N):
        g = CoupGame(policy)
        w, length, capped = g.run_game()
        total_len += length
        if capped or w is None:
            caps += 1
        else:
            wins[w] += 1
    return {
        "game": "coup",
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
