"""pools.py -- where every game at the table pools, and where its outer layer is.

baseline.py measures each game under one random policy. This plays every
registered game N seeded times under two policies and keeps the shape of
what falls out:

* **pools**: the endings, each counted and banded with ``peaks.band_of``, the
  same ``likely`` / ``middle`` / ``outlier`` read the story forecaster uses
  (``likely`` the top pool, ``middle`` at or above ``peaks.MIDDLE_FLOOR``,
  ``outlier`` below it: the outer layer);
* **lumps**: how long games run, as a histogram, with the cap-hits (a game the
  cap cut off) said apart;
* **the funnel**: for games with a leader to read off the public view, how
  often the seat leading at the halfway step is among the winners. High means
  the game has pooled by midgame; near chance means it is still open.

Two policies, because game-lab found random play hides structure that an
identical competent player in every seat reveals (``apps/game-lab/README.md``):

* ``random``: a uniform legal move, drawn from ``random.Random(seed)``;
* ``john``: game-lab's own competent policy where it ships one (Hearts, Liar's
  Dice, Crazy Eights), checkers' capture-most rule from game-lab's self-play,
  and for catgrid the reasoner of ``catgrid/rating.py`` (deduce, then hint,
  then guess). Games with no competent policy are measured under ``random``
  only, said in the output, never filled in.

Every policy sees only what a seat sees: the ``observe(seat)`` view and the
legal moves. Nothing reads a game's private state. Same N, same numbers.

    python3 -m the_table.pools [N] [out.json]
"""
from __future__ import annotations

import json
import random
import re
import sys

from . import registry
from .host import onescript_module
from .peaks import MIDDLE_FLOOR

_pools = onescript_module("pools")  # the run's shape, game-free (flatten F-14)

CAP = 5000
#: Fewer rounds where one round is slow: a 13x13 three-cat board takes seconds
#: to deal and the reasoner's look-ahead seconds a move. Said in the output.
ROUNDS = {"catgrid_3cat": 40}


# -- competent policies, from views only ---------------------------------------

def _hearts(view, legal, rng):
    from hearts import choose_pass_john, play_john

    hand = [tuple(c) for c in view["hand"]]
    if view["phase"] == "pass":
        return ("pass", *[list(c) for c in sorted(choose_pass_john(hand))])
    cards = [tuple(m[1]) for m in legal]
    trick = [(s, tuple(c)) for s, c in view["trick"]]
    return ("play", list(play_john(cards, trick, hand)))


def _liars(view, legal, rng):
    from liars_dice import john_action

    kind, bid = john_action(tuple(view["bid"]) if view["bid"] else None, view["my_dice"],
                            sum(view["dice_left"]))
    return ("challenge",) if kind == "challenge" else ("bid", *bid)


def _eights(view, legal, rng):
    from crazy_eights import choose_john

    plays = [m for m in legal if m[0] == "play"]
    if not plays:
        return legal[0]  # the forced draw or pass
    cards = sorted({tuple(m[1]) for m in plays})
    card, suit = choose_john(cards, [tuple(c) for c in view["hand"]])
    return ("play", card, suit)


def _checkers(view, legal, rng):
    most = max(len(m[3]) for m in legal)
    return rng.choice([m for m in legal if len(m[3]) == most])


def _catgrid(view, legal, rng):
    from catgrid.board import address
    from catgrid.rating import deduce, public

    b = public(view)
    order = list(view["cells"])
    cats = {order.index(a) for a, v in view["cells"].items() if v == "cat"}
    out = {order.index(a) for a, v in view["cells"].items() if v == "x"}
    got, ruled = deduce(b, cats, out, ahead=True)
    for i in sorted(got - cats):
        return ("cat", address(*divmod(i, b.n)))
    for i in sorted(ruled - out - cats):
        return ("x", address(*divmod(i, b.n)))
    if ("hint",) in legal:
        return ("hint",)
    return ("cat", rng.choice([a for a, v in view["cells"].items() if v == ""]))


JOHN = {"hearts": _hearts, "liars_dice": _liars, "crazy_eights": _eights,
        "checkers": _checkers, "catgrid": _catgrid, "catgrid_2cat": _catgrid,
        "catgrid_3cat": _catgrid}


# -- what a pool is, per game --------------------------------------------------

def ending(name, res, terminal) -> str:
    """The pool a finished round falls in: its ending, named plainly."""
    if not terminal:
        return "cut off by the cap"
    s, w = res.summary, res.winners
    if name == "hearts":
        pts = sorted(res.scores.values())
        if pts == [0.0, 26.0, 26.0, 26.0]:
            return "shot the moon"
        return "lowest alone" if len(w) == 1 else f"{len(w)} share the lowest"
    if name in ("liars_dice", "crazy_eights", "catgrid_duel"):
        return (f"seat {w[0]} wins" if len(w) == 1 else "a tie" if w else
                re.sub(r"\d+", "#", s))
    if name == "checkers":
        how = s.split(": ", 1)[-1]
        how = ("adjudicated on material" if how.startswith("adjudicated")
               else "the other side had no move" if "no legal move" in how else how)
        who = f"seat {w[0]}" if w else "draw"
        return f"{who}: {how}"
    if name == "backgammon":
        return f"seat {w[0]}, " + ("gammon" if "gammon" in s else "adjudicated" if "adjudicated" in s
                                   else "single game")
    if name.startswith("catgrid"):
        return s  # "solved with 2 heart(s) left": the hearts left are the pool
    if name == "bureau":
        return "enrolled" if "enrolled" in s else "voided" if "voided" in s else re.sub(r"\d+", "#", s)
    if name == "scene":
        return f"{'went well' if w else 'went sideways'}: {int(res.scores.get(0, 0))} successes"
    return re.sub(r"\d+", "#", s)


def leader(name, view):
    """The seat leading on the public view, or None (a tie, or no such read)."""
    def only(xs, best):
        top = best(xs)
        return xs.index(top) if xs.count(top) == 1 else None
    if name == "checkers":
        return only(view["material"], max)
    if name == "backgammon":
        me, them = view["me"]["pips"], view["them"]["pips"]
        return None if me == them else (view["seat"] if me < them else 1 - view["seat"])
    if name == "hearts" and view["phase"] == "play":
        return only(view["points"], min)
    if name == "liars_dice":
        return only(view["dice_left"], max)
    if name == "crazy_eights":
        return only([len(view["hand"])] + view["opponent_hand_sizes"], min)
    if name == "catgrid_duel":
        return only(view["score"], max)
    return None


# -- play and measure --------------------------------------------------------

def _round(name, seed, policy):
    game = registry.make(name)
    game.reset(seed)
    rng = random.Random(seed)
    leads, steps = [], 0
    while not game.is_terminal() and steps < CAP:
        seat = game.current_seat()
        legal = list(game.legal_moves(seat))
        move = (rng.choice(legal) if policy == "random"
                else JOHN[name](game.observe(seat).view, legal, rng))
        game.step(seat, move)
        steps += 1
        leads.append(leader(name, game.observe(0).view))
    return steps, game.is_terminal(), game.result(), leads


def measure(name, policy, rounds):
    """Play ``rounds`` seeded rounds of ``name`` under ``policy`` and hand what
    a seat could see of each to the one script's ``pools.measure``."""
    rows = []
    for seed in range(rounds):
        steps, terminal, res, leads = _round(name, seed, policy)
        rows.append({"steps": steps, "terminal": terminal,
                     "ending": ending(name, res, terminal), "winners": res.winners,
                     "mid_leader": leads[len(leads) // 2] if leads else None})
    return _pools.measure(rows, registry.make(name).seats)


def run(rounds=200) -> dict:
    out = {"rounds": rounds, "middle_floor": float(MIDDLE_FLOOR), "cap": CAP, "games": {}}
    for name in registry.games():
        n = min(rounds, ROUNDS.get(name, rounds))
        g = {"description": registry.describe(name), "seats": registry.make(name).seats,
             "policies": {"random": measure(name, "random", n)}}
        if name in JOHN:
            g["policies"]["john"] = measure(name, "john", n)
        else:
            g["no_competent_policy"] = "measured under random only; none is shipped for it"
        out["games"][name] = g
    return out


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    rounds = int(args[0]) if args else 200
    data = run(rounds)
    text = json.dumps(data, indent=1)
    if len(args) > 1:
        with open(args[1], "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
