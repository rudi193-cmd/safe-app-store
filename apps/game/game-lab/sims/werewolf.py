"""Self-contained Werewolf/Mafia simulator.

8 players: 2 Werewolves (informed minority, know each other), 1 Seer, 5 Villagers.
Loop: NIGHT (wolves kill 1, seer investigates 1) -> DAY (announce victim, lynch 1).
WIN: Villagers when all wolves dead; Werewolves at PARITY (wolves >= non-wolves).

Two policies:
  - "random": every action/vote uniform random among legal targets.
  - "john": competent, honest, coordinated townsfolk; competent bloc-voting wolves.

stdlib only. run(policy, N) + __main__ runs BOTH at N=500 and prints JSON.
"""

import random
import json

WOLF = "wolf"
SEER = "seer"
VILLAGER = "villager"

MAX_CYCLES = 100  # sane cap; a real 8-player game ends in <= 7 day cycles


class Player:
    __slots__ = ("idx", "role", "alive")

    def __init__(self, idx, role):
        self.idx = idx
        self.role = role
        self.alive = True


def new_game():
    roles = [WOLF, WOLF, SEER] + [VILLAGER] * 5
    random.shuffle(roles)
    return [Player(i, r) for i, r in enumerate(roles)]


def living(players):
    return [p for p in players if p.alive]


def wolves_alive(players):
    return [p for p in players if p.alive and p.role == WOLF]


def game_over(players):
    """Return 'wolves', 'village', or None."""
    w = len(wolves_alive(players))
    nonw = len([p for p in players if p.alive and p.role != WOLF])
    if w == 0:
        return "village"
    if w >= nonw:
        return "wolves"
    return None


# --------------------------------------------------------------------------- #
# RANDOM policy
# --------------------------------------------------------------------------- #
def run_random_game(players):
    cycles = 0
    while cycles < MAX_CYCLES:
        cycles += 1
        # NIGHT: wolves pick a random living non-wolf victim.
        wolves = wolves_alive(players)
        targets = [p for p in living(players) if p.role != WOLF]
        if targets:
            random.choice(targets).alive = False
        # Seer investigates a random living player (no effect on outcome for random).
        seer = next((p for p in players if p.alive and p.role == SEER), None)
        if seer:
            others = [p for p in living(players) if p.idx != seer.idx]
            if others:
                random.choice(others)  # investigate; info unused in random policy
        res = game_over(players)
        if res:
            return res, cycles
        # DAY: lynch a uniformly random living player.
        alive = living(players)
        random.choice(alive).alive = False
        res = game_over(players)
        if res:
            return res, cycles
    return game_over(players) or "wolves", cycles


# --------------------------------------------------------------------------- #
# JOHN policy: competent, honest, coordinated
# --------------------------------------------------------------------------- #
def run_john_game(players):
    """
    Town: the seer investigates each night, building a set of verified reads.
    Publicly known info (shared truthfully) = confirmed wolves and confirmed
    innocents. Day: if a confirmed wolf is alive, town lynches it; else town
    lynches the lowest-index living un-cleared player (fixed deterministic rule).

    Wolves: know each other. Avoid killing already-cleared players (waste);
    prioritize killing the seer once her identity is exposed, otherwise kill an
    un-cleared townsperson (lowest index). Wolves vote as a bloc; with a
    confirmed wolf up they can't save it (town majority), so the town target
    dies deterministically.

    Seer identity becomes "exposed" to the wolves as soon as she publicly claims
    her first read (honest coordination requires her to reveal so the town acts
    on her info). No bluffing beyond the wolves' inherent concealment.
    """
    confirmed_wolf = set()      # indices town knows are wolves
    confirmed_innocent = set()  # indices town knows are innocent (incl. seer self)
    seer_exposed = False
    investigated = set()

    def seer_player():
        return next((p for p in players if p.alive and p.role == SEER), None)

    cycles = 0
    while cycles < MAX_CYCLES:
        cycles += 1

        # ---------------- NIGHT ----------------
        wolves = wolves_alive(players)
        seer = seer_player()

        # Wolf kill choice.
        town = [p for p in living(players) if p.role != WOLF]
        victim = None
        if town:
            if seer_exposed and seer is not None:
                victim = seer
            else:
                # Un-exposed seer looks like any villager, so target the
                # lowest-index town member not already confirmed a wolf.
                pref = [p for p in town if p.idx not in confirmed_wolf]
                pool = pref if pref else town
                victim = min(pool, key=lambda p: p.idx)
        if victim is not None:
            victim.alive = False

        # Seer investigation: investigate an un-investigated living player,
        # prioritising un-cleared ones (maximise information).
        seer = seer_player()
        if seer is not None:
            confirmed_innocent.add(seer.idx)  # seer knows herself innocent
            candidates = [p for p in living(players)
                          if p.idx != seer.idx and p.idx not in investigated]
            if candidates:
                # investigate lowest-index un-cleared player
                target = min(candidates, key=lambda p: p.idx)
                investigated.add(target.idx)
                if target.role == WOLF:
                    confirmed_wolf.add(target.idx)
                else:
                    confirmed_innocent.add(target.idx)
                # Honest coordination: the seer PUBLICLY shares this read so the
                # town will act on it. Claiming exposes her as the town's info
                # engine, so from the next night the wolves know to hunt her.
                seer_exposed = True

        res = game_over(players)
        if res:
            return res, cycles

        # ---------------- DAY ----------------
        alive = living(players)
        # Determine town's lynch target (shared truthfully).
        live_confirmed_wolves = [p for p in alive if p.idx in confirmed_wolf]
        if live_confirmed_wolves:
            target = min(live_confirmed_wolves, key=lambda p: p.idx)
        else:
            # Fixed rule: lynch lowest-index living player not confirmed innocent.
            uncleared = [p for p in alive if p.idx not in confirmed_innocent]
            pool = uncleared if uncleared else alive
            target = min(pool, key=lambda p: p.idx)

        # Voting: town votes for `target`. Wolves vote as a bloc. If a confirmed
        # wolf is up, town holds the majority and it dies. Otherwise wolves also
        # back the town target (they can't reveal without exposing themselves).
        # Net deterministic result: `target` is lynched.
        target.alive = False

        res = game_over(players)
        if res:
            return res, cycles

    return game_over(players) or "wolves", cycles


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def run(policy, N):
    assert policy in ("random", "john")
    wolves_wins = 0
    village_wins = 0
    total_cycles = 0
    for _ in range(N):
        players = new_game()
        if policy == "random":
            result, cycles = run_random_game(players)
        else:
            result, cycles = run_john_game(players)
        if result == "wolves":
            wolves_wins += 1
        else:
            village_wins += 1
        total_cycles += cycles
    return {
        "game": "werewolf",
        "policy": policy,
        "N": N,
        "wolves_win_pct": round(100.0 * wolves_wins / N, 1),
        "village_win_pct": round(100.0 * village_wins / N, 1),
        "avg_cycles": round(total_cycles / N, 2),
    }


if __name__ == "__main__":
    N = 500
    results = {p: run(p, N) for p in ("random", "john")}
    print(json.dumps(results, indent=2))
