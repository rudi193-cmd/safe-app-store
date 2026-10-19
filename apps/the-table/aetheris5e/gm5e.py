"""gm5e.py -- a real 5e dice roller for the Aetheris table, wired to the
one-script record (the one chain, flatten F-6).

The AI GM (the machine) rolls and REMEMBERS; it never seals canon. Every roll
is appended as a ``verdict`` row the moment it happens, so no past roll can be
quietly rewritten -- the one-script's own verifier walks the chain. The
one-script is found beside the-table (``the_table/host.py``); with none, every
command says why and exits 2.

Live dice: seeded from os.urandom per roll (real randomness), never re-rolled.
The ledger is the honesty guarantee, not reproducibility.

The box is DATA (it holds played rolls and proposals) and is written under
``aetheris5e/_boxes/`` -- gitignored, never committed; its keys file sits
beside it, never inside. Point elsewhere with the ``AETHERIS_BOX`` env var.

A fact is PROPOSED here, never sealed: ``propose`` writes it as a proposal
the human seals with their own key through the one-script
(``onescript seal proposal:<hash> --proof ...``). No name typed here is a
seal; ``seal`` only says so.

Usage:
  python gm5e.py open  "Aetheris - The Waking Tide"      # start/refresh the campaign box
  python gm5e.py roll  "1d20+5"  "Sena: Investigation vs DC 15"
  python gm5e.py check "Aether"  5  15  --adv  "attune to the broadcast"
  python gm5e.py save  "DEX"     2  13  "Aether Discharge"
  python gm5e.py atk   6  16  "1d10+3"  "Aether Blade vs Kesh AC 16"
  python gm5e.py propose "maunder-is-a-person" "Maunder is recognized as a person."
  python gm5e.py verify
  python gm5e.py head
"""
from __future__ import annotations

import os
import random
import re
import sys

# the-table's host shim to the one-script (flatten F-7).
# aetheris5e/gm5e.py -> the-table root is one directory up.
_HERE = os.path.dirname(os.path.abspath(__file__))
_TABLE = os.path.dirname(_HERE)
sys.path.insert(0, _TABLE)
sys.path.insert(0, _HERE)
from the_table import host  # noqa: E402
import dice5e  # noqa: E402  (MIT `dice` library, wrapped)

BOX = os.environ.get("AETHERIS_BOX", os.path.join(_HERE, "_boxes", "box"))



def _rng() -> random.Random:
    return random.Random(int.from_bytes(os.urandom(8), "big"))


SESSION = "aetheris campaign"  # every row in one campaign session, across processes


def _sink(box) -> host.StateSink:
    s = host.StateSink(box, "aetheris5e")
    s.resume(SESSION)
    return s


def _roll_expr(expr: str, rng: random.Random):
    """Roll any dice-notation ``expr`` via the MIT `dice` library. Returns
    (total, detail). The library owns the RNG (fed ``rng``) and the parsing."""
    total = dice5e.total(expr, rng)
    return total, f"{expr} = {total}"


def _d20(mod: int, rng: random.Random, adv: str = ""):
    """A d20 test via dice5e (2d20 keep-highest/lowest for adv/dis).
    Returns (total, nat, detail)."""
    total, nat = dice5e.d20(rng, mod, adv=(adv == "adv"), dis=(adv == "dis"))
    kind = "adv" if adv == "adv" else "dis" if adv == "dis" else ""
    crit = " CRIT!" if nat == 20 else (" nat-1" if nat == 1 else "")
    return total, nat, f"d20{'('+kind+')' if kind else ''} nat{nat}{'+' if mod >= 0 else ''}{mod} = {total}{crit}"


COMMANDS = ("open", "roll", "check", "save", "atk", "propose", "seal", "verify", "head")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    rng = _rng()

    if cmd not in COMMANDS:
        print(__doc__)
        return 2
    box = host.box_or_exit(BOX)

    if cmd == "open":
        title = sys.argv[2] if len(sys.argv) > 2 else "Aetheris"
        s = host.StateSink(box, "aetheris5e")
        s.open_session(SESSION, {"campaign": title, "engine": "D&D 5e",
                                 "covenant": "machine proposes+remembers; a person seals with their key"})
        print(f"campaign box at {BOX}")
        print(f"session opened: {title}")
        print(f"chain head: {box.head()}")
        return 0

    s = _sink(box)

    if cmd == "roll":
        expr, note = sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "")
        total, detail = _roll_expr(expr, rng)
        s.snapshot({"kind": "roll", "expr": expr, "detail": detail, "total": total, "note": note},
                   note=note or expr)
        print(f"{note or expr}: {detail}")
        return 0

    if cmd == "check":
        # check <ability/skill> <mod> <dc> [--adv|--dis] <note>
        name, mod, dc = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
        rest = sys.argv[5:]
        adv = ""
        if rest and rest[0] in ("--adv", "--dis"):
            adv = "adv" if rest[0] == "--adv" else "dis"
            rest = rest[1:]
        note = rest[0] if rest else ""
        total, nat, detail = _d20(mod, rng, adv)
        outcome = "SUCCESS" if total >= dc else "FAIL"
        if nat == 20:
            outcome = "SUCCESS (nat 20)"
        elif nat == 1:
            outcome = "FAIL (nat 1)"
        s.snapshot({"kind": "check", "check": name, "dc": dc, "detail": detail,
                    "total": total, "outcome": outcome, "note": note}, note=f"{name} vs DC{dc}")
        print(f"{name} check vs DC {dc}{' ('+note+')' if note else ''}: {detail} -> {outcome}")
        return 0

    if cmd == "save":
        ability, mod, dc = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
        note = sys.argv[5] if len(sys.argv) > 5 else ""
        total, nat, detail = _d20(mod, rng)
        outcome = "SAVE" if total >= dc else "FAIL"
        s.snapshot({"kind": "save", "ability": ability, "dc": dc, "detail": detail,
                    "total": total, "outcome": outcome, "note": note}, note=f"{ability} save vs DC{dc}")
        print(f"{ability} save vs DC {dc}{' ('+note+')' if note else ''}: {detail} -> {outcome}")
        return 0

    if cmd == "atk":
        # atk <atk_mod> <target_ac> <dmg_expr> <note>
        atk_mod, ac, dmg_expr = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
        note = sys.argv[5] if len(sys.argv) > 5 else ""
        total, nat, detail = _d20(atk_mod, rng)
        hit = nat == 20 or (nat != 1 and total >= ac)
        line = {"kind": "attack", "atk": detail, "ac": ac, "note": note, "hit": hit}
        if hit:
            dmg, ddetail = _roll_expr(dmg_expr, rng)
            if nat == 20:  # crit: double the dice, keep the modifier
                extra, edetail = _roll_expr(re.sub(r"[+-]\d+$", "", dmg_expr), rng)
                dmg += extra
                ddetail += f" +crit{edetail.split('=')[0].strip()} => {dmg}"
            line.update({"dmg": dmg, "dmg_detail": ddetail})
            print(f"{note}: attack {detail} vs AC {ac} -> HIT for {dmg} ({ddetail})")
        else:
            print(f"{note}: attack {detail} vs AC {ac} -> MISS")
        s.snapshot(line, note=note or "attack")
        return 0

    if cmd == "propose":
        # a fact the machine PROPOSES; the human seals it, with their own key.
        fact_id, fact = sys.argv[2], sys.argv[3]
        subject = s.decision({"fact_id": fact_id, "fact": fact, "world": "aetheris",
                              "proposed_by": "the GM"})
        print(f"proposed for the human's seal: {subject}")
        print(f"  the human seals it: onescript seal {subject} --proof <their proof>")
        return 0

    if cmd == "seal":
        print("REFUSED: a seal is the human's, made with their own key through the one-script "
              "(onescript seal proposal:<hash> --proof ...); no name typed here is a seal. "
              "Use `propose` to put a fact before them.")
        return 1

    if cmd == "verify":
        breaks = box.verify()
        print(f"record verify: {'holds' if not breaks else 'BROKEN'}")
        for b in breaks[:5]:
            print(f"  {b}")
        print(f"chain head: {box.head()}")
        return 0 if not breaks else 1

    if cmd == "head":
        print(box.head())
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
