"""sealed_run.py -- one live playthrough of "The Waking Tide" to Maunder's
question, then the decision: the machine refused the pen, the beat proposed
for the human's seal, the chain verified, and a tampered copy rejected.

Live dice (os.urandom). Every roll and the decision are ``verdict`` rows in a
one-script record (the one chain, flatten F-6), found beside the-table
(``the_table/host.py``); with no one-script beside, it says why and exits 2.
The decision beat is a PROPOSAL. This script never seals it and never takes a
name as a seal: the human seals it with their own key, through the one-script
(``onescript seal proposal:<hash> --proof ...``). It reads the shared world
from the-table's ``worlds/aetheris.json``, so the narration is the authored
world's own outcome prose, not invented here.

The box is DATA and is written under ``aetheris5e/_boxes/`` (gitignored).

Run:  python3 sealed_run.py
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(TABLE))
sys.path.insert(0, TABLE)
sys.path.insert(0, HERE)
from the_table import host  # noqa: E402
import dice5e  # noqa: E402  (MIT `dice` library, wrapped)

WORLD = json.load(open(os.path.join(TABLE, "worlds", "aetheris.json")))
BEATS = {b["id"]: b for sc in WORLD["scenes"] for b in sc["beats"]}

NOT_A_PERSON = {"", "system", "machine", "ai", "gm", "dm-bot", "assistant",
                "claude", "model", "auto", "none", "null", "maunder", "kesh"}

# Sena Koll, engine-blooded envoy L3 — the seated PC for this run.
PC = {"Aether": 5, "Iron": 2, "Tide": 2, "Voice": 5}
PLAN = [("b1", "Aether", 13, True, False), ("b2", "Iron", 15, False, False),
        ("b3", "Voice", 14, False, False), ("b4", "Tide", 15, False, True),
        ("b6", "Voice", 13, False, True)]
BOX = os.path.join(HERE, "_boxes", "sealedbox")
shutil.rmtree(BOX, ignore_errors=True)
rng = random.Random(int.from_bytes(os.urandom(8), "big"))
box = host.box_or_exit(BOX)
sink = host.StateSink(box, "aetheris5e")
sink.open_session(WORLD["title"], {"pc": "Sena Koll (engine-blooded, L3)", "engine": "D&D 5e"})


def d20(mod, adv=False, dis=False):
    total, nat = dice5e.d20(rng, mod, adv=adv, dis=dis)
    return total, nat


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
        surge = dice5e.total("1d6", rng)
        if surge == 1: d2 = True; tag += ", aether-wild:AGAINST"
        elif surge == 6: a2 = True; tag += ", aether-wild:WITH"
        else: tag += ", aether-wild:—"
    if adv: tag += ", adv"
    tag += "]"
    total, nat = d20(PC[approach], adv=a2, dis=d2)
    deg = degree(total, nat, dc)
    sink.snapshot({"kind": "check", "beat": bid, "approach": approach, "dc": dc,
                   "nat": nat, "total": total, "degree": deg},
                  note=f"{bid} {approach} vs DC{dc} -> {deg}")
    print(f"\n> {bid.upper()}  {tag}")
    print(f"   {beat['prompt'][:130]}...")
    print(f"   d20 nat{nat}+{PC[approach]} = {total} vs DC {dc}  ->  {deg.upper()}")
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

print("\n   — the pen goes to the human at the head of the table —")
subject = sink.decision({"fact_id": "s2::b5", "fact": b5["proposes"]["fact"], "world": "aetheris",
                         "proposed_by": b5["proposes"]["proposed_by"]})
print(f"     proposed for the human's seal: {subject}")
print("     the human seals it with their own key, through the one-script:")
print(f"       onescript seal {subject} --proof <their proof>")
state = box.beat_seal(subject).get("state")
print(f"     sealed now? {state}  (code never seals it)")

print("\n" + "-" * 74)
breaks = box.verify()
print(f"> one-script verify_chain + verify_anchor  ->  chain {'HOLDS' if not breaks else 'BROKEN: ' + breaks[0]}")
print(f"  chain head: {box.head()}")
print(f"  record: {box.record_path}")

# -- tamper demo on a COPY (original stays honest) ---------------------------
print("\n" + "-" * 74)
print("> TAMPER TEST — rewrite a logged check in a COPY of the record, then re-verify:")


def _flip(rows):
    for i, r in enumerate(rows):
        if r.get("what") == "step" and isinstance(r.get("state"), dict):
            st = dict(r["state"])
            st["degree"] = "strong" if st.get("degree") != "strong" else "miss"
            rows[i] = {**r, "state": st}
            print(f"    (someone quietly changed {st.get('beat')}'s degree to {st['degree']} in the copy)")
            break
    return rows


copy = box.tampered_copy(_flip)
tampered = box.verify(copy)
print(f"    verify on the tampered copy -> {'REFUSES (' + tampered[0] + ')' if tampered else 'passed?!'}")
shutil.rmtree(os.path.dirname(copy), ignore_errors=True)
print("\n    The dice you can trust because they're on the record. The decision you can")
print("    trust only once a person seals it with their own key; no name typed here is a seal.")
