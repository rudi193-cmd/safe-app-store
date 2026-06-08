"""
lattice_fallback.py — local-mode 23-cubed lattice constants for Dating Wellbeing.

Used only when Willow's user_lattice module is not importable (i.e. running
standalone without a Willow checkout). Mirrors the-squirrel's standalone
pattern: the app stays runnable without Willow, and these values are replaced
by Willow's canonical lattice when WILLOW_CORE points at a real Willow/core.

Domains/temporal states cover the values this app's backfill actually places.
"""

DOMAINS = frozenset({"patterns", "history", "relationships"})
TEMPORAL_STATES = frozenset({"evolving", "established"})
DEPTH_MIN = 1
DEPTH_MAX = 23
LATTICE_SIZE = 23
