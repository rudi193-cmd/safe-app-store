"""
lattice_fallback.py — local-mode 23-cubed lattice constants for Field Notes.

Used only when Willow's user_lattice module is not importable (i.e. running
standalone without a Willow checkout). Mirrors the-squirrel's standalone
pattern: the app stays runnable without Willow, and these values are replaced
by Willow's canonical lattice when WILLOW_CORE points at a real Willow/core.

Domains mirror Field Notes' own note vocabulary so place_in_lattice() validates
the values this app actually produces.
"""

DOMAINS = frozenset({
    "observation", "thought", "quote", "task", "weather", "location",
})
TEMPORAL_STATES = frozenset({"past", "present", "future", "unknown"})
DEPTH_MIN = 1
DEPTH_MAX = 23
LATTICE_SIZE = 23
