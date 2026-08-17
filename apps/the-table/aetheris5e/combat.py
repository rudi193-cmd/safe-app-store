"""combat.py -- a real 5e combat engine for the Aetheris table, ledger-logged.

Widens the aetheris5e harness from skill checks to full initiative combat, using
the campaign's own stat blocks (statblocks.py). Same covenant, same ledger: the
machine rolls initiative, attacks, saves, damage, and REMEMBERS every swing in a
tamper-evident ai-game-master chain -- it never seals anything.

Two modes, mirroring the rest of the harness:
  * fight <encounter> [--seed N]   -- ONE fight, round by round, every roll
                                       appended to a hash chain that then
                                       verifies (and a tampered copy refuses).
  * sim   <encounter> [rounds]     -- run the encounter many times (seeded) and
                                       report where it rolls out: party win %,
                                       average rounds, average survivors, TPK %.

The engine OWNS its RNG (a random.Random passed through every roll) -- unlike
the-table's SceneSession, it never touches the global random module, so a
Monte-Carlo sweep is reproducible: sim round i is driven by random.Random(i).

Rules modeled (kept faithful but deliberately gridless -- everyone is "in
range"): initiative (d20+init, stable), multiattack, attack vs AC with
advantage/disadvantage from blindness, nat-20 crit (double damage dice),
damage resistance (typed + the Warden's nonmagical-weapon halving), recharge
abilities (d6 at start of turn, recharge on 5-6), AoE saves (full/half or a
condition), Override-Pulse stun, Salt-Spray blind, the Bruiser's Overheat
self-hazard, the Rogue's once-per-turn Sneak Attack, and the Fighter's
Action Surge + one superiority die. Drop at 0 HP (no death saves in this
skeleton). Round cap 50 -> declared a stalemate.

Ledger boxes are DATA (rolls, outcomes) -- written under aetheris5e/_boxes/,
gitignored, never committed.
"""
from __future__ import annotations

import os
import random
import shutil
import sqlite3
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TABLE = os.path.dirname(_HERE)
sys.path.insert(0, _TABLE)
sys.path.insert(0, _HERE)
from the_table.ledger_sink import LedgerSink  # noqa: E402
import statblocks  # noqa: E402
# dice notation + RNG are delegated to the MIT `dice` library via dice5e --
# ai-game-master's reuse-vs-build wall (reuse the roller; build only the seam).
from dice5e import total as roll, crit_expr as _double_dice, d20  # noqa: E402

AGM_VERIFY = os.path.join(os.path.dirname(os.path.dirname(_TABLE)),
                          "apps", "ai-game-master", "bootstrap", "verify_ledger.py")


# ── engine ───────────────────────────────────────────────────────────────────

class Combat:
    def __init__(self, combatants, rng: random.Random, sink: LedgerSink = None, log=None):
        self.cs = combatants
        self.rng = rng
        self.sink = sink
        self.log = log or (lambda *_: None)
        self.round = 0

    def living(self, side=None):
        return [c for c in self.cs if c["hp"] > 0 and (side is None or c["side"] == side)]

    def _record(self, note, state):
        self.log(note)
        if self.sink is not None:
            self.sink.snapshot(state, note=note)

    def _resisted(self, target, dmg, dtype, magical):
        bps = {"bludgeoning", "piercing", "slashing"}
        if dtype in target["resist_types"]:
            return dmg // 2, True
        if target.get("resist_nonmagical_bps") and dtype in bps and not magical:
            return dmg // 2, True
        return dmg, False

    def _apply_damage(self, target, dmg, dtype, magical):
        dmg, resisted = self._resisted(target, dmg, dtype, magical)
        target["hp"] = max(0, target["hp"] - dmg)
        return dmg, resisted

    def attack(self, attacker, target, atk):
        adv = target["blind_turns"] > 0            # blinded target -> attackers have advantage
        dis = attacker["blind_turns"] > 0          # blinded attacker -> disadvantage
        total, nat = d20(self.rng, atk["atk"], adv=adv, dis=dis)
        if nat != 20 and (nat == 1 or total < target["ac"]):
            self._record(f"{attacker['name']} misses {target['name']} with {atk['name']} "
                         f"(d20={total} vs AC {target['ac']})",
                         {"kind": "attack", "by": attacker["name"], "vs": target["name"],
                          "atk": atk["name"], "total": total, "hit": False})
            return
        crit = nat == 20
        dmg = roll(_double_dice(atk["dmg"]) if crit else atk["dmg"], self.rng)
        extra = ""
        # Sneak Attack: once per turn, on a hit, if the attacker has it.
        if attacker.get("sneak_attack") and not attacker["used_sneak_this_turn"]:
            sa_expr = _double_dice(attacker["sneak_attack"]) if crit else attacker["sneak_attack"]
            sa = roll(sa_expr, self.rng)
            dmg += sa
            attacker["used_sneak_this_turn"] = True
            extra += f" +sneak {sa}"
        # One superiority die (Battle Master) on a hit while dice remain.
        if attacker.get("sup_dice", 0) > 0:
            sd = roll("1d8", self.rng)
            dmg += sd
            attacker["sup_dice"] -= 1
            extra += f" +superiority {sd}"
        dealt, resisted = self._apply_damage(target, dmg, atk["type"], atk["magical"])
        tag = f"{' CRIT' if crit else ''}{' (resisted)' if resisted else ''}"
        self._record(
            f"{attacker['name']} hits {target['name']} with {atk['name']} for {dealt}{tag}"
            f"{extra} (d20={total} vs AC {target['ac']}); {target['name']} at {target['hp']}/{target['max_hp']}",
            {"kind": "attack", "by": attacker["name"], "vs": target["name"], "atk": atk["name"],
             "total": total, "hit": True, "crit": crit, "dmg": dealt, "resisted": resisted,
             "target_hp": target["hp"]})
        if target["hp"] == 0:
            self._record(f"{target['name']} falls.",
                         {"kind": "down", "who": target["name"]})

    def save(self, creature, ability, dc, disadvantage=False):
        total, nat = d20(self.rng, creature["saves"].get(ability, 0), dis=disadvantage)
        return (nat == 20 or (nat != 1 and total >= dc)), total

    def use_aoe(self, attacker, special):
        targets = self.living("party" if attacker["side"] == "foe" else "foe")
        eff = special["effect"]
        self._record(f"{attacker['name']} uses {special['name']} — {special['flavor']}",
                     {"kind": "special", "by": attacker["name"], "name": special["name"]})
        for t in targets:
            disadv = special.get("aether_implant_disadv") and t.get("aether_implant")
            saved, total = self.save(t, special["save"], special["dc"], disadvantage=disadv)
            if eff == "damage":
                dmg = roll(special["dmg"], self.rng)
                if saved and special.get("half_on_save"):
                    dmg //= 2
                dealt, resisted = self._apply_damage(t, dmg, special.get("type", "force"), True)
                self._record(
                    f"  {t['name']} {'saves' if saved else 'FAILS'} ({total} vs DC {special['dc']}) "
                    f"— takes {dealt}{' (resisted)' if resisted else ''}; {t['hp']}/{t['max_hp']}",
                    {"kind": "save", "who": t["name"], "vs": special["name"], "saved": saved,
                     "dmg": dealt, "hp": t["hp"]})
                if t["hp"] == 0:
                    self._record(f"  {t['name']} falls.", {"kind": "down", "who": t["name"]})
            else:
                if not saved:
                    if eff == "stun":
                        t["skip_turns"] = max(t["skip_turns"], 1)
                    elif eff == "blind":
                        t["blind_turns"] = max(t["blind_turns"], 2)
                past = {"stun": "stunned", "blind": "blinded"}.get(eff, eff)
                self._record(
                    f"  {t['name']} {'saves' if saved else 'FAILS — ' + past} "
                    f"({total} vs DC {special['dc']})",
                    {"kind": "save", "who": t["name"], "vs": special["name"], "saved": saved,
                     "effect": None if saved else eff})

    def _pick_target(self, attacker):
        foes = self.living("party" if attacker["side"] == "foe" else "foe")
        return min(foes, key=lambda c: c["hp"]) if foes else None

    def take_turn(self, c):
        if c["hp"] <= 0:
            return
        # recharge specials
        for sp in c["specials"]:
            if sp.get("recharge") and not sp.get("available"):
                if roll("1d6", self.rng) >= 5:
                    sp["available"] = True
        # stun: skip a turn
        if c["skip_turns"] > 0:
            c["skip_turns"] -= 1
            self._record(f"{c['name']} is stunned and loses its turn.",
                         {"kind": "stunned_skip", "who": c["name"]})
            return
        c["used_sneak_this_turn"] = False
        # Overheat self-hazard (Bruiser) at start of turn if below half.
        for sp in c["specials"]:
            if sp.get("self_hazard") and c["hp"] * 2 < c["max_hp"]:
                saved, total = self.save(c, sp["save"], sp["dc"])
                if not saved:
                    dmg = roll(sp["dmg"], self.rng)
                    c["hp"] = max(0, c["hp"] - dmg)
                    self._record(f"{c['name']} overheats — {dmg} force ({c['hp']}/{c['max_hp']})",
                                 {"kind": "overheat", "who": c["name"], "dmg": dmg, "hp": c["hp"]})
                    if c["hp"] == 0:
                        self._record(f"{c['name']} burns out.", {"kind": "down", "who": c["name"]})
                        return

        def _act():
            # Prefer an available AoE special when it hits 2+ enemies.
            enemies = self.living("party" if c["side"] == "foe" else "foe")
            for sp in c["specials"]:
                if sp.get("shape") == "aoe" and sp.get("available") and len(enemies) >= 2:
                    self.use_aoe(c, sp)
                    if sp.get("recharge"):
                        sp["available"] = False
                    return
            melee = c["attacks"][0]
            for _ in range(c["multiattack"]):
                target = self._pick_target(c)
                if target is None:
                    return
                self.attack(c, target, melee)

        _act()
        # Action Surge: a second action, once.
        if c.get("action_surge") and self.living("party" if c["side"] == "foe" else "foe"):
            c["action_surge"] = False
            self._record(f"{c['name']} uses Action Surge — a second action.",
                         {"kind": "action_surge", "who": c["name"]})
            _act()
        if c["blind_turns"] > 0:
            c["blind_turns"] -= 1

    def run(self, cap=50):
        order = sorted(self.cs, key=lambda c: (d20(self.rng, c["init"])[0], c["init"]), reverse=True)
        self._record("initiative: " + ", ".join(c["name"] for c in order),
                     {"kind": "initiative", "order": [c["name"] for c in order]})
        while self.living("party") and self.living("foe") and self.round < cap:
            self.round += 1
            self._record(f"— round {self.round} —", {"kind": "round", "n": self.round})
            for c in order:
                if not (self.living("party") and self.living("foe")):
                    break
                self.take_turn(c)
        party, foe = self.living("party"), self.living("foe")
        if party and not foe:
            outcome = "party"
        elif foe and not party:
            outcome = "foe"
        else:
            outcome = "stalemate"
        return {"outcome": outcome, "rounds": self.round,
                "party_survivors": [c["name"] for c in party],
                "foe_survivors": [c["name"] for c in foe]}


# ── modes ────────────────────────────────────────────────────────────────────

def simulate(encounter: str, rounds: int) -> dict:
    wins = {"party": 0, "foe": 0, "stalemate": 0}
    total_rounds = 0
    party_surv = 0
    tpk = 0
    n_party = len([1 for _ in statblocks.ENCOUNTERS[encounter]["party"]])
    for seed in range(rounds):
        cs = statblocks.build_encounter(encounter)
        res = Combat(cs, random.Random(seed)).run()
        wins[res["outcome"]] += 1
        total_rounds += res["rounds"]
        party_surv += len(res["party_survivors"])
        if not res["party_survivors"]:
            tpk += 1
    return {"encounter": encounter, "runs": rounds, "wins": wins,
            "avg_rounds": total_rounds / rounds, "avg_party_survivors": party_surv / rounds,
            "party_size": n_party, "tpk": tpk}


def _fmt_sim(s):
    r = s["runs"]
    L = ["=" * 70,
         f"AETHERIS 5e COMBAT · {s['encounter']} · {r} runs · seeds 0..{r-1}",
         f"  {statblocks.ENCOUNTERS[s['encounter']]['desc']}",
         "=" * 70,
         f"  party wins : {s['wins']['party']:4d}  ({100*s['wins']['party']/r:5.1f}%)  "
         + "█" * round(40 * s['wins']['party'] / r),
         f"  party loss : {s['wins']['foe']:4d}  ({100*s['wins']['foe']/r:5.1f}%)",
         f"  stalemate  : {s['wins']['stalemate']:4d}  ({100*s['wins']['stalemate']/r:5.1f}%)",
         f"  avg rounds : {s['avg_rounds']:.1f}",
         f"  avg party survivors: {s['avg_party_survivors']:.2f} of {s['party_size']}",
         f"  total party wipes (TPK): {s['tpk']}  ({100*s['tpk']/r:.1f}%)",
         "=" * 70]
    return "\n".join(L)


def fight(encounter: str, seed: int | None, human_readable=True):
    lines = []
    box = os.path.join(_HERE, "_boxes", f"fight-{encounter}")
    shutil.rmtree(box, ignore_errors=True)
    sink = LedgerSink(box)
    sink.open_session(f"combat-{encounter}", {"encounter": encounter, "engine": "D&D 5e"})
    rng = random.Random(seed) if seed is not None else random.Random(int.from_bytes(os.urandom(8), "big"))
    cs = statblocks.build_encounter(encounter)
    print("=" * 70)
    print(f"AETHERIS 5e COMBAT · {encounter}" + (f" · seed {seed}" if seed is not None else " · live"))
    print(f"  {statblocks.ENCOUNTERS[encounter]['desc']}")
    print("=" * 70)
    for c in cs:
        print(f"  [{c['side']:5s}] {c['name']:22s} AC {c['ac']:2d}  HP {c['hp']:3d}")
    print("-" * 70)
    res = Combat(cs, rng, sink=sink, log=lambda s: print("  " + s)).run()
    sink.close_session(res)
    print("-" * 70)
    print(f"OUTCOME: {res['outcome'].upper()} in {res['rounds']} rounds")
    print(f"  standing: {', '.join(res['party_survivors'] + res['foe_survivors']) or '(none)'}")
    ok = sink.verify()
    head = sink.head()
    sink.close()
    print(f"  ledger verify(): {ok}   head: {head[:16]}…")
    # tamper a copy: bump a damage number and re-verify
    copy = os.path.join(_HERE, "_boxes", f"fight-{encounter}-tampered")
    shutil.rmtree(copy, ignore_errors=True)
    shutil.copytree(box, copy)
    con = sqlite3.connect(os.path.join(copy, "campaign.db"))
    con.execute("UPDATE ledger SET note = note || ' (edited)' WHERE kind='turn' "
                "AND note LIKE '%hits%' LIMIT 1")
    con.commit(); con.close()
    r = subprocess.run([sys.executable, AGM_VERIFY, os.path.join(copy, "campaign.db"), "--canon"],
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()
    print(f"  tampered copy (one hit edited): verify exit {r.returncode} "
          f"({'REFUSES' if r.returncode else 'passed?!'})")
    if tail:
        print("    " + tail[-2] if len(tail) > 1 else "    " + tail[-1])
    return res


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] == "list":
        print("encounters:")
        for name, e in statblocks.ENCOUNTERS.items():
            print(f"  {name:12s} — {e['desc']}")
        print("\nusage:  combat.py fight <encounter> [--seed N]")
        print("        combat.py sim   <encounter> [rounds]")
        return 0
    cmd = argv[0]
    if cmd == "sim":
        enc = argv[1]
        rounds = int(argv[2]) if len(argv) > 2 else 500
        print(_fmt_sim(simulate(enc, rounds)))
        return 0
    if cmd == "fight":
        enc = argv[1]
        seed = None
        if "--seed" in argv:
            seed = int(argv[argv.index("--seed") + 1])
        fight(enc, seed)
        return 0
    print(f"unknown command {cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
