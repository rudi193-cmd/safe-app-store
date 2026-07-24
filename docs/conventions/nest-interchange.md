# Convention: the Nest interchange (nest-seed ⇄ willow-mcp Nest tools)
b17: SAPS1

Three places carry the *same* Nest model — one SQLite schema of
`sources` + `fragments` + `nest_meta`:

| Where | Role |
|---|---|
| **the-squirrel** | genealogy app; original fragment model (`db.py` note: "Mirrors the Squirrel fragment model") |
| **nest-seed** (this store) | the **portable seeder** — walk a folder, extract, classify, write a `seed.db`. No Postgres, no fleet dependency, runs anywhere |
| **willow-mcp** `willow_mcp.nest` | the **fleet engine + tools** — `nest_scan`, `nest_status`, `nest_digest`, `nest_promote`, `nest_intake_*` |

Measured on 2026-07-24: nest-seed's schema and willow-mcp's `nest/db.py` schema
are **byte-identical** across all three tables (every column of `sources`,
`fragments`, `nest_meta`). They are twins.

## The contract

`seed.db` is the interchange. A Nest built **offline** by nest-seed on a machine
that has never seen the fleet is **fully consumable** by willow-mcp's Nest tools
when the fleet *is* present:

- `nest_status` / `nest_digest` read a nest-seed `seed.db` directly.
- `nest_promote` lifts its *structure* (counts, curated categories, redacted
  secret kinds — never content, filenames, or names) into the KB.

This is the injected-seam pattern the store uses everywhere: nest-seed stays
standalone (its whole reason to exist), and the fleet consumes its output rather
than the app reaching into the fleet. nest-seed does **not** import willow-mcp —
doing so would add the dependency it is designed to avoid.

## The risk this convention pins: silent drift

Twins on one schema drift silently — a column added on one side breaks
cross-consumption with *no error*, just a promotion that quietly loses data. So
both sides now freeze the same contract as a test:

- `apps/nest-seed/tests/test_nest_interchange.py` (this store)
- `willow-mcp/tests/test_nest_interchange.py` (the fleet)

The `CANONICAL_COLUMNS` constant is identical in both; either side drifting
turns a test red instead of losing data. Keep the two copies in sync.

## the-squirrel

the-squirrel already touches Willow only through a reachability probe
(`safe_integration.py` → `os.path.exists` on the store), not a content read, so
it holds rule #1. When it needs to *read* a family-document Nest, it should go
through `nest_status` / `nest_digest` (the walled, structure-only views) rather
than open a `seed.db` itself — same interchange, consumed through the fleet
tools.

## Redundancy flag (Mistletoe)

nest-seed and `willow_mcp.nest` are one engine in two repos. This is exactly the
"designing/holding what already exists" pattern Loki's semantic Mistletoe
watches for. They are kept deliberately separate today — nest-seed *must* run
without the fleet — so the convergence target is **not** deleting one, but
keeping a single canonical schema (enforced by the paired tests above) and, if
the engines themselves drift, extracting the shared classify/ocr/digest core to
a small package both import. Tracked as future work, not done here.

---

*Convention doc. Interchange schema frozen 2026-07-24. Companion to the paired
`test_nest_interchange.py` guards in `nest-seed` and `willow-mcp`. `ΔΣ=42`*
