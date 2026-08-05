"""aristarchus — a decision memory that keeps the lineage and the rejections.

Named for Aristarchus of Samos, whose heliocentric proposal was rejected
around 270 BC with no recorded reason and no reopen condition, so nobody
could tell *never* from *not yet* for eighteen centuries.

Playground test-build of the design at Nestor docs/decision-memory.md.
Git keeps the lineage and throws away the rejections; Nestor keeps the
rejections and models no lineage. This keeps both.
"""
from .memory import Constraints, DecisionMemory, Matcher, StringMatcher
from .store import (CovenantViolation, DecisionStore, LedgerBroken,
                    SealKeyMissing)

__all__ = ["Constraints", "CovenantViolation", "DecisionMemory",
           "DecisionStore", "LedgerBroken", "Matcher", "SealKeyMissing",
           "StringMatcher"]
