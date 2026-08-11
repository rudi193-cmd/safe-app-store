"""Homestead · Health — family health records the household holds itself.

Module three on **Homestead · Affairs**, sibling to `homestead-law` and
`homestead-ledger`, incubating in the safe-app-store toward promotion to
`rudi193-cmd/homestead-health`. The design is
`homestead/docs/PLAN-homestead-health.md`; this package is **bite 1 — the
seat**: a module that pins the engine and proves the pin, holding nothing
else yet. The roster (bite 2), the immunizations pack (bite 3), due-onto-Today
(bite 4) and the school-form export (bite 5) are claims in
`tests/test_invariants_pending.py`, each `xfail(strict=True)` so none can land
quietly.

**`homestead-affairs` is a pinned dependency** consumed only through
`homestead.keep`'s public API. Do not modify it, propose changes to it, or
generalize app logic into it. Upstream changes are issues on
`rudi193-cmd/homestead`.

What the seat guarantees, each held by a test in
`tests/test_invariants_seat.py`:

* the engine pin is true — `homestead.keep` imports, from the declared
  distribution, floor and cap both stated (I-27);
* nothing imports the network and nothing listens (I-26 / I-30);
* there is no second path resolver and no banned spelling — every path this
  module ever touches comes from `homestead.keep.paths`, and `expanduser`
  does not appear (I-19 / I-20);
* bare `pytest -q` works from a cold checkout (I-28).
"""
from __future__ import annotations

# Load-bearing, not decorative: "a module cannot pin an engine that does not
# exist." Importing the seat verifies the pin — a checkout where the engine is
# missing or broken fails here, at import, naming the real problem, rather
# than three modules later inside whatever first reached for `serve()`.
import homestead.keep  # noqa: F401

__all__: list[str] = []
