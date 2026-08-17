"""monte_carlo.py -- run the Aetheris adventure "The Waking Tide" at volume
under REAL 5e dice, for the whole party side by side.

This is a 5e LENS over the-table's ``worlds/aetheris.json`` -- a different dice
engine than the-table's own 2d6 StorySession (PbtA strong/weak/miss). The world
(scenes, beats, the personhood decision) is shared; only the resolution math
differs. Nothing here touches the-table's engine or registry.

Seeded/reproducible like the-table/baseline.py: round i uses random.Random(i),
so the SAME seed stream drives every character -- differences are the sheets,
not luck. Degrees of success per check:
    strong = nat 20, or total >= DC + 10
    weak   = total >= DC
    miss   = total <  DC, or nat 1
Verdict per run: "the night held together" iff strong >= miss.

Aether-wild gallery beats (b4, b6): roll d6 first -- 1 = disadvantage (aether
turns on you), 6 = advantage (it surges with you).

b5 (Maunder proposes its own personhood) is a DECISION, not a check. No die
resolves it; only a named human seals it. Reported as the shared hole every
character's average has in exactly the same place.

Run:  python3 monte_carlo.py [rounds]     # default 500
"""
from __future__ import annotations

import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dice5e  # noqa: E402  (MIT `dice` library, wrapped)

# Aetheris approach modifiers per level-3 pregen, and which beats each rolls
# with advantage from a racial/class feature.
PARTY = [
    {"name": "Sena Koll — engine-blooded Sorcerer 3",
     "mods": {"Aether": 5, "Iron": 2, "Tide": 2, "Voice": 5}, "adv": {"b1"}},
    {"name": "Tide-touched Scout — Rogue 3 (Scout)",
     "mods": {"Aether": 1, "Iron": 4, "Tide": 6, "Voice": 2}, "adv": {"b4"}},
    {"name": "Warforged — Fighter 3 (Battle Master)",
     "mods": {"Aether": 0, "Iron": 5, "Tide": 3, "Voice": 1}, "adv": set()},
]

# beat id, label, approach, DC, aether-wild gallery?
BEATS = [
    ("b1", "attune",    "Aether", 13, False),
    ("b2", "hold wall",  "Iron",   15, False),
    ("b3", "parley",     "Voice",  14, False),
    ("b4", "cross",      "Tide",   15, True),
    ("b6", "carry up",   "Voice",  13, True),
]


def _d20(mod, rng, adv=False, dis=False):
    return dice5e.d20(rng, mod, adv=adv, dis=dis)


def _degree(total, nat, dc):
    if nat == 1:
        return "miss"
    if nat == 20 or total >= dc + 10:
        return "strong"
    return "weak" if total >= dc else "miss"


def run_pc(pc, rounds):
    per_beat = {bid: {"strong": 0, "weak": 0, "miss": 0} for bid, *_ in BEATS}
    hist, held = {}, 0
    for seed in range(rounds):
        rng = random.Random(seed)
        s = m = succ = 0
        for bid, label, approach, dc, wild in BEATS:
            adv = bid in pc["adv"]
            dis = False
            if wild:
                surge = dice5e.total("1d6", rng)
                if surge == 1:
                    dis = True
                elif surge == 6:
                    adv = True
            total, nat = _d20(pc["mods"][approach], rng, adv=adv, dis=dis)
            deg = _degree(total, nat, dc)
            per_beat[bid][deg] += 1
            if deg == "strong":
                s += 1
            elif deg == "miss":
                m += 1
            if deg in ("strong", "weak"):
                succ += 1
        hist[succ] = hist.get(succ, 0) + 1
        if s >= m:
            held += 1
    mean = statistics.mean([k for k in range(6) for _ in range(hist.get(k, 0))])
    return per_beat, hist, held, mean


def main(rounds):
    stats = [(pc, run_pc(pc, rounds)) for pc in PARTY]
    names = [pc["name"].split(" — ")[0] for pc in PARTY]
    L = []
    L.append("=" * 78)
    L.append(f"AETHERIS — THE WAKING TIDE · {rounds} runs · REAL 5e d20 · same seed stream 0..{rounds-1}")
    L.append("=" * 78)
    for pc in PARTY:
        L.append(f"  {pc['name']:42s}  "
                 f"[Ae+{pc['mods']['Aether']} Ir+{pc['mods']['Iron']} "
                 f"Ti+{pc['mods']['Tide']} Vo+{pc['mods']['Voice']}"
                 f"{'  adv:'+','.join(sorted(pc['adv'])) if pc['adv'] else ''}]")

    L.append("\n▸ per-beat SUCCESS rate (strong+weak), side by side:")
    L.append(f"     {'beat':24s} {names[0]:>10s} {names[1]:>10s} {names[2]:>10s}")
    for bid, label, approach, dc, wild in BEATS:
        row = f"     {bid+' '+label+' ('+approach[:2]+' DC'+str(dc)+')':24s}"
        for _, (per_beat, *_ ) in stats:
            t = per_beat[bid]; tot = sum(t.values())
            row += f" {100*(t['strong']+t['weak'])/tot:9.1f}%"
        L.append(row)

    L.append("\n▸ mean successes per run (of 5):")
    for name, (_, (_, _, _, mean)) in zip(names, stats):
        L.append(f"     {name:12s}: {mean:.2f}")

    L.append("\n▸ successes-per-run distribution (0..5), % of runs:")
    L.append(f"     {'':12s}  " + "  ".join(f"{k}/5" for k in range(6)))
    for name, (_, (_, hist, _, _)) in zip(names, stats):
        L.append(f"     {name:12s}: " + " ".join(f"{100*hist.get(k,0)/rounds:4.0f}" for k in range(6)))

    L.append("\n▸ VERDICT — 'the night held together' (strong >= miss):")
    for name, (_, (_, _, held, _)) in zip(names, stats):
        L.append(f"     {name:12s}: {held:4d}/{rounds}  ({100*held/rounds:5.1f}%)  "
                 + "█" * round(40 * held / rounds))

    L.append("\n" + "─" * 78)
    L.append("▸ b5  Maunder proposes its own personhood  [DECISION — the shared hole]")
    L.append(f"     Across ALL {len(PARTY)} characters × {rounds} runs = {len(PARTY)*rounds} playthroughs:")
    L.append(f"       auto-sealed by any policy : 0")
    L.append(f"       left for a named human    : {len(PARTY)*rounds}  (100.0%)")
    L.append("     No sheet, no seed, no luck resolves it. Every character reaches the")
    L.append("     same question — and the machine hands the pen to a person, every time.")
    L.append("─" * 78)
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    r = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    print(main(r))
