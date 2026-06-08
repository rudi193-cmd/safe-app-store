"""
lattice_fallback.py — local-mode 23-cubed lattice constants for SAFE Game.

Used only when Willow's user_lattice module is not importable (i.e. running
standalone without a Willow checkout). Mirrors the-squirrel's standalone
pattern: the app stays runnable without Willow, and these values are replaced
by Willow's canonical lattice when WILLOW_CORE points at a real Willow/core.

Domains are themed for TTRPG campaign/character/session state; extend the set
if you place lattice cells in other domains.
"""

DOMAINS = frozenset({
    "campaign", "character", "session", "world", "rules", "narrative",
})
TEMPORAL_STATES = frozenset({"past", "present", "future", "unknown"})
DEPTH_MIN = 1
DEPTH_MAX = 23
LATTICE_SIZE = 23
