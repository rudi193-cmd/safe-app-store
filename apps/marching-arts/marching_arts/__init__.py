"""marching_arts — the authorization core for a marching-program platform.

Placeholder name. This is P1 of docs/BUILD_PLAN.md:
storage and the authorization resolver, built first because everything else
depends on it — including the sync spine, which is this same component wearing
a different hat. A device receives only what its holder may see, so the filter
that decides a query is the filter that decides a sync, and it is built once.

P2 — identity, roles and consent — is the ``consent`` submodule, which binds
``libs/subject-consent`` onto the very connection this store opens, so grants,
the hash-chained disclosure log and the domain data are one file.

``marching_arts.consent`` is deliberately **not** imported here. Importing this
package must pull in nothing but the standard library — that is what
``test_import_is_stdlib_only`` checks, and it is what keeps the browser port a
port rather than a rewrite of a dependency tree. The binding is one import away
for anyone who wants it::

    from marching_arts.consent import ConsentedRoster

Import-pure and stdlib-only by design: no network module is reachable from this
package at import time, which tests/test_no_egress.py verifies by walking the
AST rather than by trusting this sentence.
"""
from __future__ import annotations

from .bands import Band
from .policy import MAJORITY_AGE, GrantState, GrantVia, Policy, Principal
from .rules import Effect, Rule, compile_rules
from .store import Fact, Store

__all__ = [
    "Band",
    "Effect",
    "Fact",
    "GrantState",
    "GrantVia",
    "MAJORITY_AGE",
    "Policy",
    "Principal",
    "Rule",
    "Store",
    "compile_rules",
]

# Left at 0.1.0 deliberately: apps/marching-arts/safe-app-manifest.json and the
# store's catalog.json both carry this number and are shared files this branch
# does not touch. Bump all three together, or not at all.
__version__ = "0.1.0"
