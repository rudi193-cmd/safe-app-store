"""gm5e.py -- a real 5e dice roller for the Aetheris table, wired to the-table's
tamper-evident ai-game-master ledger.

The AI GM (the machine) rolls and REMEMBERS; it never seals canon. Every roll
is appended to a hash-chained ledger the moment it happens, so no past roll can
be quietly rewritten -- ai-game-master's own verifier walks the chain.

Live dice: seeded from os.urandom per roll (real randomness), never re-rolled.
The ledger is the honesty guarantee, not reproducibility.

Ledger boxes are DATA (they hold played rolls and human seals) and are written
under ``aetheris5e/_boxes/`` -- gitignored, never committed. Point elsewhere
with the ``AETHERIS_BOX`` env var.

Usage:
  python gm5e.py open  "Aetheris - The Waking Tide"      # start/refresh the campaign box
  python gm5e.py roll  "1d20+5"  "Sena: Investigation vs DC 15"
  python gm5e.py check "Aether"  5  15  --adv  "attune to the broadcast"
  python gm5e.py save  "DEX"     2  13  "Aether Discharge"
  python gm5e.py atk   6  16  "1d10+3"  "Aether Blade vs Kesh AC 16"
  python gm5e.py seal  "maunder-is-a-person" "SEALED" "Ada Vane"  "recognized as a person"
  python gm5e.py verify
  python gm5e.py head
"""
from __future__ import annotations

import os
import random
import re
import sys

# import the-table's LedgerSink (a CONSUMER of ai-game-master, unmodified).
# aetheris5e/gm5e.py -> the-table root is one directory up.
_HERE = os.path.dirname(os.path.abspath(__file__))
_TABLE = os.path.dirname(_HERE)
sys.path.insert(0, _TABLE)
from the_table.ledger_sink import LedgerSink  # noqa: E402

BOX = os.environ.get("AETHERIS_BOX", os.path.join(_HERE, "_boxes", "box"))

# machine ids that may NOT seal canon -- mirrors story_session.NOT_A_PERSON
NOT_A_PERSON = {"", "system", "machine", "ai", "gm", "dm-bot", "assistant",
                "claude", "model", "auto", "none", "null", "maunder", "kesh"}


def _rng() -> random.Random:
    return random.Random(int.from_bytes(os.urandom(8), "big"))


def _sink() -> LedgerSink:
    s = LedgerSink(BOX)
    s._session_num = 1  # keep every row in campaign session 1 across processes
    return s


def _roll_expr(expr: str, rng: random.Random):
    """Roll 'NdM+K' / 'NdM-K' / 'dM' / flat int. Returns (total, detail)."""
    expr = expr.replace(" ", "")
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr)
    if not m:
        return int(expr), str(expr)
    n = int(m.group(1) or "1")
    faces = int(m.group(2))
    mod = int(m.group(3) or "0")
    dice = [rng.randint(1, faces) for _ in range(n)]
    total = sum(dice) + mod
    detail = f"{dice}{'+' if mod >= 0 else ''}{mod if mod else ''} = {total}"
    return total, detail


def _d20(mod: int, rng: random.Random, adv: str = ""):
    a, b = rng.randint(1, 20), rng.randint(1, 20)
    if adv == "adv":
        nat, both = max(a, b), f"adv[{a},{b}]"
    elif adv == "dis":
        nat, both = min(a, b), f"dis[{a},{b}]"
    else:
        nat, both = a, f"[{a}]"
    total = nat + mod
    crit = " CRIT!" if nat == 20 else (" nat-1" if nat == 1 else "")
    return total, nat, f"d20{both}{'+' if mod >= 0 else ''}{mod} = {total}{crit}"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    rng = _rng()

    if cmd == "open":
        title = sys.argv[2] if len(sys.argv) > 2 else "Aetheris"
        s = LedgerSink(BOX)
        s.open_session(title, {"campaign": title, "engine": "D&D 5e",
                               "covenant": "machine proposes+remembers; a named human seals"})
        print(f"campaign box provisioned at {BOX}")
        print(f"session opened: {title}")
        print(f"chain head: {s.head()}")
        return 0

    s = _sink()

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

    if cmd == "seal":
        # a HUMAN seal, recorded append-only (the sink never writes the canon table).
        fact_id, verdict, by = sys.argv[2], sys.argv[3].upper(), sys.argv[4]
        reason = sys.argv[5] if len(sys.argv) > 5 else ""
        who = by.strip().lower()
        tokens = [t for t in re.split(r"[^a-z0-9]+", who) if t]
        if who in NOT_A_PERSON or any(t in NOT_A_PERSON for t in tokens):
            print(f"REFUSED: {by!r} is not a named human -- only a person may seal canon.")
            return 1
        if verdict not in ("SEALED", "REJECTED"):
            print(f"REFUSED: verdict must be SEALED or REJECTED, got {verdict!r}")
            return 1
        s.snapshot({"kind": "human_seal", "fact_id": fact_id, "verdict": verdict,
                    "by": by, "reason": reason},
                   note=f"SEAL {fact_id} {verdict} by {by}")
        print(f"recorded at the table: {fact_id} {verdict} by {by}"
              f"{' -- '+reason if reason else ''}")
        print("(append-only record that a human decided; the canon seal itself stays human-only)")
        return 0

    if cmd == "verify":
        ok = s.verify()
        print(f"ledger verify(): {ok}")
        print(f"chain head: {s.head()}")
        return 0 if ok else 1

    if cmd == "head":
        print(s.head())
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
