"""
gatefirst — the counterfactual slice of The Squirrel.
b17: SAPS1

Same two actors, same trust table, same WillowGate underneath — but the gate
is the constructor of capability, not a check inside functions. See README.md
for the diff you should spot against sap/core/gate.py + db/*.py.
"""

from .identity import Gatehouse, ReadHandle, WriteHandle, StewardHandle, ROLES
from .store import Store, Denied

__all__ = [
    "Gatehouse", "ReadHandle", "WriteHandle", "StewardHandle", "ROLES",
    "Store", "Denied",
]
