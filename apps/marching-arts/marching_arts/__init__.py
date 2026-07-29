"""marching_arts — the authorization core for a marching-program platform.

Placeholder name. This is P1 of docs/BUILD_PLAN.md:
storage and the authorization resolver, built first because everything else
depends on it — including the sync spine, which is this same component wearing
a different hat. A device receives only what its holder may see, so the filter
that decides a query is the filter that decides a sync, and it is built once.

Import-pure and stdlib-only by design: no network module is reachable from this
package at import time, which tests/test_no_egress.py verifies by walking the
AST rather than by trusting this sentence.
"""
from __future__ import annotations

from .bands import Band
from .policy import GrantState, Policy, Principal
from .rules import Effect, Rule, compile_rules
from .store import Fact, Store

__all__ = [
    "Band",
    "Effect",
    "Fact",
    "GrantState",
    "Policy",
    "Principal",
    "Rule",
    "Store",
    "compile_rules",
]

__version__ = "0.1.0"
