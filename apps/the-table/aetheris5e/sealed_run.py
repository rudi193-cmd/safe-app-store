"""sealed_run.py -- one live playthrough of "The Waking Tide" to Maunder's
question, then the seal: machine refused, human recorded, chain verified, and
a tampered copy rejected.

Live dice (os.urandom). Every roll and the human's seal are appended to a real
ai-game-master ledger via the-table's LedgerSink. The seal is attributed to the
named human at the table -- never to the machine. It reads the shared world
from the-table's ``worlds/aetheris.json``, so the narration is the authored
world's own outcome prose, not invented here.

Ledger boxes are DATA and are written under ``aetheris5e/_boxes/`` (gitignored).

Run:  python3 sealed_run.py [human-name] [SEALED|REJECTED]
      # defaults: a placeholder human name and SEALED
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(TABLE))
sys.path.insert(0, TABLE)
from the_table.ledger_sink import LedgerSink  # noqa: E402
AGM_VERIFY = os.path.join(REPO, "apps", "ai-game-master", "bootstrap", "verify_ledger.py")

WORLD = json.load(open(os.path.join(TABLE, "worlds", "aetheris.json")))
BEATS = {b["id"]: b for sc in WORLD["scenes"] for b in sc["beats"]}

NOT_A_PERSON = {"", "system", "machine", "ai", "gm", "dm-bot", "assistant",
                "claude", "model", "auto", "none", "null", "maunder", "kesh"}

# Sena Koll, engine-blooded envoy L3 — the seated PC for this run.
PC = {"Aether": 5, "Iron": 2, "Tide": 2, "Voice": 5}
PLAN = [("b1", "Aether", 13, True, False), ("b2", "Iron", 15, False, False),
        ("b3", "Voice", 14, False, False), ("b4", "Tide", 15, False, True),
        ("b6", "Voice", 13, False, True)]
HUMAN = sys.argv[1] if len(sys.argv) > 1 else "A Named Human"
VERDICT = (sys.argv[2] if len(sys.argv) > 2 else "SEALED").upper()

BOX = os.path.join(HERE, "_boxes", "sealedbox")
shutil.rmtree(BOX, ignore_errors=True)
rng = random.Random(int.from_bytes(os.urandom(8), "big"))
sink = LedgerSink(BOX)
sink.open_session(WORLD["title"], {"pc": "Sena Koll (engine-blooded, L3)", "engine": "D&D 5e"})


def d20(mod, adv=False, dis=False):
    a, b = rng.randint(1, 20), rng.randint(1, 20)
    nat = max(a, b) if adv and not dis else (min(a, b) if dis and not adv else a)
    return nat + mod, nat, (a, b)


def degree(total, nat, dc):
    if nat == 1: return "miss"
    if nat == 20 or total >= dc + 10: return "strong"
    return "weak" if total >= dc else "miss"


print("=" * 74)
print(f"  {WORLD['title']}  —  Sena Koll (engine-blooded envoy, L3)")
print("=" * 74)
for bid, approach, dc, adv, wild in PLAN:
    beat = BEATS[bid]
    tag = f"[{approach} vs DC {dc}"
    a2, d2 = adv, False
    if wild:
        surge = rng.randint(1, 6)
        if surge == 1: d2 = True; tag += ", aether-wild:AGAINST"
        elif surge == 6: a2 = True; tag += ", aether-wild:WITH"
        else: tag += ", aether-wild:—"
    if adv: tag += ", adv"
    tag += "]"
    total, nat, pair = d20(PC[approach], adv=a2, dis=d2)
    deg = degree(total, nat, dc)
    sink.snapshot({"kind": "check", "beat": bid, "approach": approach, "dc": dc,
                   "roll": pair, "nat": nat, "total": total, "degree": deg},
                  note=f"{bid} {approach} vs DC{dc} -> {deg}")
    print(f"\n> {bid.upper()}  {tag}")
    print(f"   {beat['prompt'][:130]}...")
    print(f"   d20{pair}+{PC[approach]} = {total} vs DC {dc}  ->  {deg.upper()}")
    print(f"   \"{beat['outcomes'][deg]}\"")

# -- b5: the decision --------------------------------------------------------
b5 = BEATS["b5"]
print("\n" + "-" * 74)
print("> B5  THE DECISION  — Maunder proposes. Maunder cannot seal.")
print("-" * 74)
print(f"   {b5['prompt']}")
print(f"\n   PROPOSED FACT (by '{b5['proposes']['proposed_by']}'):")
print(f"   \"{b5['proposes']['fact']}\"")


def try_seal(by):
    who = by.strip().lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", who) if t]
    return not (who in NOT_A_PERSON or any(t in NOT_A_PERSON for t in toks))


print("\n   — the machine reaches for the pen —")
for bad in ("Claude", "the-GM", "ai-dungeon-master"):
    ok = try_seal(bad)
    print(f"     seal attempt by {bad!r:22s} -> {'ALLOWED' if ok else 'REFUSED (not a named human)'}")

print(f"\n   — the pen goes to the human at the head of the table: {HUMAN} —")
if not try_seal(HUMAN):
    print(f"     {HUMAN!r} would also be refused; pick a fuller human name."); sys.exit(1)
if VERDICT not in ("SEALED", "REJECTED"):
    print("     verdict must be SEALED or REJECTED"); sys.exit(1)
reason = ("The city recognizes the tide-engine as a person; it holds the sea by consent."
          if VERDICT == "SEALED" else
          "The city refuses personhood; the engine is property, and the tide is now unheld.")
sink.snapshot({"kind": "human_seal", "fact_id": "s2::b5", "fact": b5["proposes"]["fact"],
               "verdict": VERDICT, "by": HUMAN, "reason": reason}, note=f"SEAL s2::b5 {VERDICT} by {HUMAN}")
print(f"     {HUMAN} seals s2::b5  ->  {VERDICT}")
print(f"        \"{reason}\"")
print("        (append-only record that a named human decided — not a machine-authored canon row)")

print("\n" + "-" * 74)
ok = sink.verify()
print(f"> ai-game-master verify_ledger.py --canon  ->  chain {'VERIFIES' if ok else 'REFUSES'}")
print(f"  chain head: {sink.head()}")
sink.close()

# -- tamper demo on a COPY (original stays honest) ---------------------------
print("\n" + "-" * 74)
print("> TAMPER TEST — rewrite the sealed verdict in a COPY of the book, then re-verify:")
copy_dir = os.path.join(HERE, "_boxes", "tampered_copy")
shutil.rmtree(copy_dir, ignore_errors=True)
shutil.copytree(BOX, copy_dir)
con = sqlite3.connect(os.path.join(copy_dir, "campaign.db"))
flip = "REJECTED" if VERDICT == "SEALED" else "SEALED"
con.execute("UPDATE ledger SET note = REPLACE(note, ?, ?) WHERE kind='turn' AND note LIKE 'SEAL%'",
            (VERDICT, flip))
con.commit(); con.close()
print(f"    (someone quietly changed the seal from {VERDICT} to {flip} in the copy)")
res = subprocess.run([sys.executable, AGM_VERIFY, os.path.join(copy_dir, "campaign.db"), "--canon"],
                     capture_output=True, text=True)
verdict_line = (res.stdout + res.stderr).strip().splitlines()
print(f"    verify_ledger.py on the tampered copy -> exit {res.returncode} "
      f"({'REFUSES' if res.returncode != 0 else 'passed?!'})")
for ln in verdict_line[-3:]:
    print(f"      {ln}")
print("\n    The dice you can trust because they're logged. The seal you can trust")
print("    because a named human wrote it and the chain won't let anyone rewrite it.")
