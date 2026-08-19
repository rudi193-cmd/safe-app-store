"""
Shared 23-cubed lattice structural constants.

Apps provide their own DOMAINS and TEMPORAL_STATES via their local
lattice_fallback module. This package owns only the structural geometry
that every lattice consumer shares.
"""

DEPTH_MIN = 1
DEPTH_MAX = 23
LATTICE_SIZE = 23


def load_lattice(app_domains, app_temporal_states):
    """Try Willow's canonical user_lattice; fall back to the app-supplied vocab.

    Returns (DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE).
    """
    import os, sys
    _willow_core = os.environ.get(
        "WILLOW_CORE", os.path.expanduser("~/github/Willow/core")
    )
    if os.path.isfile(os.path.join(_willow_core, "user_lattice.py")):
        sys.path.insert(0, _willow_core)
    try:
        from user_lattice import (
            DOMAINS, TEMPORAL_STATES,
            DEPTH_MIN as _dmin, DEPTH_MAX as _dmax, LATTICE_SIZE as _lsz,
        )
        return DOMAINS, TEMPORAL_STATES, _dmin, _dmax, _lsz
    except ImportError:
        return app_domains, app_temporal_states, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE
