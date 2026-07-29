"""A field-acoustics simulator for marching-arts drill design.

Answers one question quantitatively: what changes in the audience when an
ensemble stops facing the front sideline and turns in to face the middle of the
field?
"""

from .atmosphere import A_WEIGHT, BANDS
from .drill import FORMS, Performer, apply_facing, arc_form, block_form, load_csv, save_csv
from .engine import Conditions, Result, simulate
from .field import Stadium, named_seats
from .instruments import CATALOG

__all__ = [
    "BANDS", "A_WEIGHT", "CATALOG", "Conditions", "FORMS", "Performer", "Result",
    "Stadium", "apply_facing", "arc_form", "block_form", "load_csv", "named_seats",
    "save_csv", "simulate",
]
