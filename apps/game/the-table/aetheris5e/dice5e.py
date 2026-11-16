"""dice5e.py -- the aetheris5e dice seam, now the one script's (flatten F-14).

5e dice notation over a generator handed in (cached, with a fast path, the
``dice`` library as its authority) lives in the one script's
``onescript/dice5e.py``. This module IS that module: importing it puts the
one script's in its place, so ``import dice5e`` and ``from dice5e import
total`` read as before. With no one script beside, it raises
``host.Unreachable`` and says why (F-16).
"""
import os
import sys

if __package__ in (None, ""):  # imported as top-level ``dice5e`` from aetheris5e/
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from the_table.host import onescript_module  # noqa: E402

sys.modules[__name__] = onescript_module("dice5e")
