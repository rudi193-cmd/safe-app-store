"""Health record packs — kinds of health record the household holds.

The two-level rule from the face doc governs the module's internals: **modules**
are sibling repos on the org; **packs** live inside a module. Law's packs are
kinds of legal matter (custody, bankruptcy, workers' comp); health's packs are
kinds of health record — immunizations, medications, conditions, allergies,
providers, insurance.

**v1 builds immunizations and nothing else** — *"one pack proves the seam; three
prove nothing that one does not"* is standing, and inventing stubs for the later
packs now would be the hand-kept phantom I-23 forbids, one level up. Each pack is
a closed schema classified at import by `homestead.keep.rungs.classify_schema`,
so an authored field with no rung stops the build naming itself (I-11) — the
custody pack's shape, on health's schemas.
"""
