"""kitchen-pudding — a recipe store where every quantity carries provenance.

Not a Mealie/Tandoor/KitchenOwl fork: those are AGPLv3, and this needed a
from-scratch, permissively-licensed core anyway to carry the one thing none
of them do — treating "2 cups flour" as a claim with a source, not a fact.

P1 of docs/PRODUCT_PLAN.md: every ingredient is ``measured``, ``fitted`` or
``assumed`` (``kitchen_pudding.provenance``), a recipe is worth its weakest
ingredient via ``min()``, and a correction lands beside the original record —
never on top of it (``kitchen_pudding.store``). Both are the store's existing
discipline (CLAUDE.md: "Provenance is a state, not a score"; "Corrections
land beside the record, never on top of it"), applied to something as
mundane as a recipe box specifically because mundane is where the discipline
usually gets skipped.

Import-pure and stdlib-only: no network module is reachable from this
package at import time.
"""
from __future__ import annotations
