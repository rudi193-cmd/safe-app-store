"""dice5e.py -- the aetheris5e dice seam.

Delegates ALL randomness and dice-notation parsing to the MIT-licensed `dice`
library (borntyping/python-dice, https://pypi.org/project/dice/) instead of a
hand-rolled regex parser. This is the reuse-vs-build wall from
`apps/ai-game-master/docs/DECISION.md` made literal: an AI Game Master is a
"yes-and bookkeeper, not a rules referee," so it REUSES the off-the-shelf dice
plumbing (SRD 5.1/5.2 rules text + an MIT dice roller are the named reuse tier)
and BUILDS only the seam — the loop that proposes, rolls, remembers, and routes
every "is this true now?" through a human seal. The dice are plumbing, not a
moat; nothing about d20 arithmetic is ours to own.

Crucially, `dice.roll(expr, random=rng)` accepts an injected RNG, so the engine
keeps owning its own `random.Random` — seeded fights and Monte-Carlo sweeps stay
reproducible, and no code here ever touches the global `random` module.

The library returns a list-like `Roll` (the kept dice) for a bare `NdM`/keep
expression and an int-like `Integer` (the total) for an arithmetic expression;
`total()` normalizes both to a plain summed int.
"""
from __future__ import annotations

import re

import dice as _dice  # MIT — borntyping/python-dice


def total(expr: str, rng) -> int:
    """Roll ``expr`` using ``rng`` for every die, returning a plain int total.

    ``rng`` is any object with a ``randint`` (a ``random.Random``); it is passed
    straight through to the library so the caller keeps ownership of the stream.
    """
    v = _dice.roll(expr, random=rng)
    return int(v) if isinstance(v, int) else sum(int(x) for x in v)


def crit_expr(expr: str) -> str:
    """Double the DICE COUNT of ``expr`` for a 5e crit, keeping the flat
    modifier (``1d10+3`` -> ``2d10+3``). Pure string surgery — no randomness —
    so it lives beside the roller rather than inside it."""
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr.replace(" ", ""))
    if not m:
        return expr
    n = int(m.group(1) or "1") * 2
    return f"{n}d{m.group(2)}{m.group(3) or ''}"


def d20(rng, mod: int = 0, adv: bool = False, dis: bool = False):
    """A 5e d20 test: roll 1d20 (or 2d20 keep-highest/lowest for
    advantage/disadvantage) via the library, add ``mod``, and return
    ``(total, nat)`` so the caller can still see a natural 20/1 for crits."""
    expr = "2d20h1" if adv and not dis else "2d20l1" if dis and not adv else "1d20"
    nat = total(expr, rng)
    return nat + mod, nat
