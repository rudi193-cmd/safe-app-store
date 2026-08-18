"""Homestead · Health — family health records the household holds itself.

Module three on **Homestead · Affairs**, sibling to `homestead-law` and
`homestead-ledger`, incubating in the safe-app-store toward promotion to
`rudi193-cmd/homestead-health`. The design is
`homestead/docs/PLAN-homestead-health.md`. **Bite 1 — the seat** pins the
engine and proves the pin. **Bite 2 — the roster** (`roster.py`) is subjects
before records: opaque ids the counter mints, the id → person mapping stored
through the engine's record layer and served through the gate, and a
`VisibleLog` line that carries the id and nothing of the name (H-1, promoted to
`tests/test_invariants_roster.py`). **Bite 3 — the immunizations pack**
(`packs/immunizations.py`) is health's first real schema, classified at import
in the custody pack's shape, so an authored field with no rung fails the build
naming itself (H-4, promoted to `tests/test_invariants_immunizations.py`).
**Bite 4 — due onto Today** (`due.py`) computes the next dose on calendar days
(a Saturday due date stays Saturday, not `court_days`) and gates the Today line
through the engine's k ≥ 2 re-identification check on the household's subjects,
rendering from a closed vocabulary that has no slot for advice (H-2, promoted to
`tests/test_invariants_due.py`). **Bite 5 — the school form** (`school_form.py`)
is health's first purposed egress: it composes a subject's doses, served through
`S4_EGRESS` with a declared purpose, into one form and exports it through the
engine's export path — one `IntegrityLog` and one `VisibleLog` entry, references
only, head anchor off-tree, so a hand-edited entry fails verification (bite 5,
promoted to `tests/test_invariants_school_form.py`). The pinned reference
snapshot (H-5) and the emergency card (H-3) are still claims in
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
