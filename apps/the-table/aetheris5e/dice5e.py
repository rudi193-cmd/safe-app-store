"""dice5e.py -- the aetheris5e dice seam (cached, with a fast path).

Delegates dice-notation AUTHORITY to the MIT-licensed `dice` library
(borntyping/python-dice, https://pypi.org/project/dice/) -- the reuse-vs-build
wall from `apps/ai-game-master/docs/DECISION.md` (an AI Game Master reuses the
dice plumbing and builds only the seam). But the library is pyparsing-based and
re-parses every call, and its AST memoizes its result per object (so a parsed
AST cannot be re-evaluated for a fresh roll). So this seam adds two speedups
without owning the grammar:

  * CACHE — each distinct expression is COMPILED ONCE into a native roller
    closure, keyed by the expression string (`_COMPILED`). Repeat calls never
    re-parse.
  * FAST PATH — for the simple forms the harness actually rolls (``NdM``,
    ``NdM±K``, and ``AdBh1``/``AdBl1`` keep-highest/lowest for
    advantage/disadvantage), the compiled closure computes the result directly
    with ``rng.randint``. Anything the fast path does NOT recognize falls back
    to the real `dice` library (re-parsed each call), which also stays the
    validator: EVERY expression is `parse_expression`'d by the library once, at
    compile time, so an illegal expression is refused by the library, not by us
    -- the grammar is never ours. `test_combat.TestDiceSeam` asserts the fast
    path never diverges from the library (die faces, count, keep semantics,
    bounds).

The RNG stays the caller's: every path draws from the injected ``rng`` (a
``random.Random``), never the global module, so seeded fights and Monte-Carlo
sweeps remain reproducible.

R6 LIMIT (W4 break 6, T15): the ``dice`` library's keep-highest/keep-lowest
operators ignore an injected ``random`` and shuffle with the GLOBAL module
(``dice/elements.py:409-418`` builds the kwargs and drops them; ``:625``
falls back to ``random``; third party, not ours to edit). So keep forms are
rolled here, never by the library: ``AdBhK`` / ``AdBlK`` on the fast path
above, over the injected ``rng``. Any other expression the library rolls is
watched: if it moves the global ``random`` state while an ``rng`` was handed
in, the state is put back and the roll is REFUSED (``ValueError``), never
returned from the wrong source.
"""
from __future__ import annotations

import random as _random
import re
import threading

import dice as _dice  # MIT — borntyping/python-dice

_SIMPLE = re.compile(r"(\d*)d(\d+)([+-]\d+)?")          # NdM, NdM±K, dM, (with mod)
_KEEP = re.compile(r"(\d+)d(\d+)([hl])(\d+)")            # AdB h/l K  (advantage forms)

_COMPILED: dict = {}   # expr -> callable(rng) -> int   (the cache)


_GLOBAL_LOCK = threading.Lock()


class GlobalRandomUsed(ValueError):
    """The ``dice`` library drew from the global ``random`` though an ``rng``
    was injected (its keep operators do; R6 limit)."""


def _lib_total(expr: str, rng) -> int:
    """The library's roll, refused if it touched the global ``random`` while
    ``rng`` was injected (the state is put back first)."""
    if rng is _random:
        v = _dice.roll(expr, random=rng)
    else:
        with _GLOBAL_LOCK:
            before = _random.getstate()
            v = _dice.roll(expr, random=rng)
            moved = _random.getstate() != before
            if moved:
                _random.setstate(before)
        if moved:
            raise GlobalRandomUsed(
                f"{expr!r}: the dice library rolled part of this with the global "
                "random, not the injected stream (its keep-highest/lowest operators "
                "ignore `random=`); write keep forms as AdBhK or AdBlK, which this "
                "seam rolls on the stream (R6 limit)")
    return int(v) if isinstance(v, int) else sum(int(x) for x in v)


def _compile(expr: str):
    """Compile ``expr`` once into a roller closure. Simple forms become native
    ``rng.randint`` arithmetic (the fast path); anything else stays with the
    library. Either way the library validates the notation once here."""
    e = expr.replace(" ", "")
    _dice.parse_expression(e)   # the library is the grammar authority (raises on illegal notation)

    m = _SIMPLE.fullmatch(e)
    if m:
        n = int(m.group(1) or "1")
        faces = int(m.group(2))
        mod = int(m.group(3) or "0")
        return lambda rng: sum(rng.randint(1, faces) for _ in range(n)) + mod

    k = _KEEP.fullmatch(e)
    if k:
        n, faces, which, keep = int(k.group(1)), int(k.group(2)), k.group(3), int(k.group(4))

        def _keep_roller(rng):
            rolls = sorted((rng.randint(1, faces) for _ in range(n)), reverse=(which == "h"))
            return sum(rolls[:keep])
        return _keep_roller

    # not a fast-path form: let the library own it entirely (re-parsed per call).
    return lambda rng: _lib_total(e, rng)


def total(expr: str, rng) -> int:
    """Roll ``expr`` using ``rng`` for every die, returning a plain int total.
    First call for a given expression compiles+caches a roller; later calls hit
    the cache (and, for simple forms, never touch pyparsing again)."""
    f = _COMPILED.get(expr)
    if f is None:
        f = _COMPILED[expr] = _compile(expr)
    return f(rng)


def crit_expr(expr: str) -> str:
    """Double the DICE COUNT of ``expr`` for a 5e crit, keeping the flat
    modifier (``1d10+3`` -> ``2d10+3``). Pure string surgery -- no randomness."""
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr.replace(" ", ""))
    if not m:
        return expr
    n = int(m.group(1) or "1") * 2
    return f"{n}d{m.group(2)}{m.group(3) or ''}"


def d20(rng, mod: int = 0, adv: bool = False, dis: bool = False):
    """A 5e d20 test: roll 1d20 (or 2d20 keep-highest/lowest for
    advantage/disadvantage), add ``mod``, and return ``(total, nat)`` so the
    caller can still see a natural 20/1 for crits."""
    expr = "2d20h1" if adv and not dis else "2d20l1" if dis and not adv else "1d20"
    nat = total(expr, rng)
    return nat + mod, nat
