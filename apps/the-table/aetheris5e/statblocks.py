"""statblocks.py -- 5e combatants for the Aetheris table.

Every foe here is a faithful transcription of a stat block from the Aetheris
campaign setting (the six "Basic Stat Blocks"): AC, HP, initiative, the saves
that matter, multiattack, and the signature special (Override Pulse, Aether
Discharge, Salt Spray, Overheat, ...). The three player pregens are the same
level-3 sheets the monte_carlo lens uses, given real combat lines (attacks,
AC, HP, sneak attack / superiority die / action surge).

Each entry is a zero-arg factory that returns a FRESH combatant dict, so an
encounter can be rebuilt from scratch every round of a Monte-Carlo sweep
without two runs sharing one mutable creature -- the same freshness rule
the-table's registry.py makes for game factories.

A combatant dict is plain data; combat.py owns all the rules that read it.
Damage typing is tracked so the setting's resistances actually bite: the
Engine-Blooded Bruiser halves force (Sena's Aether Lash), and the Mind-Forge
Warden halves nonmagical weapon hits (the Scout's shortsword) but not magical
force (the Warforged's aether blade).
"""
from __future__ import annotations


def _atk(name, atk, dmg, dtype, *, magical=False, ranged=False):
    return {"name": name, "atk": atk, "dmg": dmg, "type": dtype,
            "magical": magical, "ranged": ranged}


def _base(**kw):
    c = {
        "ac": 10, "hp": 1, "init": 0, "saves": {},
        "attacks": [], "multiattack": 1, "specials": [],
        "resist_types": set(), "resist_nonmagical_bps": False,
        "aether_implant": False, "sneak_attack": None,
        "action_surge": False, "sup_dice": 0,
        # runtime, set/read by combat.py:
        "skip_turns": 0, "blind_turns": 0, "used_sneak_this_turn": False,
    }
    c.update(kw)
    c["max_hp"] = c["hp"]
    return c


# ── foes: the campaign's six stat blocks ─────────────────────────────────────

def aether_construct():
    return _base(
        name="Aether Construct", ac=16, hp=32, init=1,
        saves={"STR": 2, "DEX": 1, "CON": 2, "INT": 0, "WIS": 0, "CHA": -2},
        attacks=[_atk("Slam", 4, "1d8+2", "bludgeoning"),
                 _atk("Integrated Crossbow", 3, "1d10+1", "piercing", ranged=True)],
        multiattack=2)


def mind_forge_warden():
    return _base(
        name="Mind-Forge Warden", ac=17, hp=75, init=2,
        saves={"STR": 3, "DEX": 2, "CON": 5, "INT": 4, "WIS": 3, "CHA": 0},
        attacks=[_atk("Aether Blade", 5, "2d6+3", "force", magical=True),
                 _atk("Integrated Projector", 4, "3d8", "force", magical=True, ranged=True)],
        multiattack=2, resist_nonmagical_bps=True,
        specials=[{"name": "Override Pulse", "recharge": True, "available": True,
                   "shape": "aoe", "save": "INT", "dc": 13, "effect": "stun",
                   "aether_implant_disadv": True,
                   "flavor": "a 15-ft pulse; INT save or stunned"}])


def tide_touched_scout():
    return _base(
        name="Tide-Touched Scout", ac=14, hp=27, init=2,
        saves={"STR": 0, "DEX": 2, "CON": 1, "INT": 0, "WIS": 2, "CHA": 0},
        attacks=[_atk("Shortsword", 4, "1d6+2", "piercing"),
                 _atk("Shortbow", 4, "1d6+2", "piercing", ranged=True)],
        multiattack=2,
        specials=[{"name": "Salt Spray", "recharge": False, "available": True,
                   "shape": "aoe", "save": "CON", "dc": 11, "effect": "blind",
                   "flavor": "a 15-ft cone; CON save or blinded"}])


def engine_blooded_bruiser():
    return _base(
        name="Engine-Blooded Bruiser", ac=15, hp=52, init=1,
        saves={"STR": 3, "DEX": 1, "CON": 5, "INT": 0, "WIS": 0, "CHA": -1},
        attacks=[_atk("Slam", 5, "1d10+3", "bludgeoning")],
        multiattack=2, resist_types={"force", "lightning"},
        specials=[{"name": "Aether Discharge", "recharge": True, "available": True,
                   "shape": "aoe", "save": "DEX", "dc": 13, "effect": "damage",
                   "dmg": "4d6", "type": "force", "half_on_save": True,
                   "flavor": "a 10-ft burst; DEX save, 4d6 force (half on save)"},
                  {"name": "Overheat", "self_hazard": True, "save": "CON", "dc": 13,
                   "dmg": "1d10", "type": "force",
                   "flavor": "below half HP: CON save or 1d10 force each turn"}])


def scorched_belt_raider():
    return _base(
        name="Scorched Belt Raider", ac=13, hp=22, init=2,
        saves={"STR": 1, "DEX": 2, "CON": 1, "INT": 0, "WIS": 0, "CHA": 0},
        attacks=[_atk("Scimitar", 4, "1d6+2", "slashing"),
                 _atk("Shortbow", 4, "1d6+2", "piercing", ranged=True)],
        multiattack=1)


def concord_enforcer():
    return _base(
        name="Concord Enforcer", ac=16, hp=39, init=1,
        saves={"STR": 4, "DEX": 1, "CON": 4, "INT": 0, "WIS": 1, "CHA": 1},
        attacks=[_atk("Longsword", 4, "1d10+2", "slashing"),
                 _atk("Hand Crossbow", 3, "1d6+1", "piercing", ranged=True)],
        multiattack=2)


# ── the party: the three level-3 pregens, given combat lines ─────────────────

def sena_koll():
    return _base(
        name="Sena Koll", ac=13, hp=20, init=2, aether_implant=True,
        saves={"STR": -1, "DEX": 2, "CON": 4, "INT": 0, "WIS": 1, "CHA": 5},
        attacks=[_atk("Aether Lash", 5, "1d10+3", "force", magical=True, ranged=True)],
        multiattack=1)


def tide_scout_pc():
    return _base(
        name="Tide-touched Scout", ac=15, hp=21, init=3,
        saves={"STR": 0, "DEX": 3, "CON": 1, "INT": 1, "WIS": 2, "CHA": 0},
        attacks=[_atk("Shortsword", 5, "1d6+3", "piercing"),
                 _atk("Shortbow", 5, "1d6+3", "piercing", ranged=True)],
        multiattack=1, sneak_attack="2d6")


def warforged_pc():
    return _base(
        name="Warforged", ac=18, hp=31, init=1, aether_implant=True,
        saves={"STR": 3, "DEX": 1, "CON": 3, "INT": 0, "WIS": 1, "CHA": -1},
        attacks=[_atk("Aether Blade", 5, "1d10+3", "force", magical=True)],
        multiattack=1, action_surge=True, sup_dice=4)


FOES = {
    "aether_construct": aether_construct,
    "mind_forge_warden": mind_forge_warden,
    "tide_touched_scout": tide_touched_scout,
    "engine_blooded_bruiser": engine_blooded_bruiser,
    "scorched_belt_raider": scorched_belt_raider,
    "concord_enforcer": concord_enforcer,
}

PARTY = {
    "sena": sena_koll,
    "scout": tide_scout_pc,
    "warforged": warforged_pc,
}

# Named encounters: which pregens stand, and which foes they face (name, count).
ENCOUNTERS = {
    "warden": {"desc": "the full party vs a Mind-Forge Warden (the gallery's guardian wakes)",
               "party": ["sena", "scout", "warforged"],
               "foes": [("mind_forge_warden", 1)]},
    "enforcers": {"desc": "the party vs a Concord press-gang: 2 Enforcers + an Aether Construct",
                  "party": ["sena", "scout", "warforged"],
                  "foes": [("concord_enforcer", 2), ("aether_construct", 1)]},
    "raiders": {"desc": "the party ambushed by 4 Scorched Belt Raiders",
                "party": ["sena", "scout", "warforged"],
                "foes": [("scorched_belt_raider", 4)]},
    "bruiser": {"desc": "the party vs an Engine-Blooded Bruiser and a Tide-Touched Scout",
                "party": ["sena", "scout", "warforged"],
                "foes": [("engine_blooded_bruiser", 1), ("tide_touched_scout", 1)]},
}


def build_encounter(name: str) -> list:
    """Return a fresh list of combatants for the named encounter, each tagged
    with side ('party' | 'foe') and a unique display id when duplicated."""
    if name not in ENCOUNTERS:
        raise KeyError(f"no encounter {name!r}; known: {sorted(ENCOUNTERS)}")
    enc = ENCOUNTERS[name]
    combatants = []
    for pc in enc["party"]:
        c = PARTY[pc]()
        c["side"] = "party"
        combatants.append(c)
    for foe_name, count in enc["foes"]:
        for i in range(count):
            c = FOES[foe_name]()
            c["side"] = "foe"
            if count > 1:
                c["name"] = f"{c['name']} #{i + 1}"
            combatants.append(c)
    return combatants
