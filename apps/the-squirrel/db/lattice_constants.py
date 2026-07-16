"""
db.lattice_constants — vendored 23-cubed lattice constants.
b17: NNA92
ΔΣ=42

Five plain constants, vendored so the Squirrel runs with zero Willow.
When WILLOW_CORE is set, db/__init__.py imports the live user_lattice
instead and these are ignored — Willow remains the source of truth on
boxes that have it; this file is the truth on boxes that don't.

(The old squirrel_app.py bootstrap shim used to write exactly these
values into a fake user_lattice.py at boot — which proved they are
configuration, not code. Now they're honest configuration.)
"""

DOMAINS = frozenset({"biography", "geography", "genealogy", "culture", "migration"})
TEMPORAL_STATES = frozenset({"past", "present", "future", "unknown"})
DEPTH_MIN = 1
DEPTH_MAX = 23
LATTICE_SIZE = 23
