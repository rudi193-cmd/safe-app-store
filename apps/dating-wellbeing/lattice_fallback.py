"""
lattice_fallback.py — local-mode 23-cubed lattice constants for Dating Wellbeing.

Structural constants (DEPTH_MIN/MAX, LATTICE_SIZE) come from the shared
lattice-constants lib. This file defines only the app-specific domain vocab.
"""

from lattice_constants import DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE  # noqa: F401

DOMAINS = frozenset({"patterns", "history", "relationships"})
TEMPORAL_STATES = frozenset({"evolving", "established"})
