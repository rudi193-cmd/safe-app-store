# The Squirrel — Front-Facing Promotion Plan
**Date:** 2026-07-15
**Status:** EXECUTED 2026-07-16 — all phases landed; app at 2.1.0, catalog `beta`.
Security stack (gate/receipts/vault/consent/divider) was wired ahead of the
storage rewrite, so Phase 1 ran with every invariant already pinned by tests.
See CHANGELOG.md for the release summary.
**Scope note:** Security/safety hardening is deliberately OUT of scope. USER has
existing pieces for that layer and will introduce them after this plan is agreed.
This plan defines the *seams* those pieces plug into (Phase 4) and nothing more.

---

## What "front-facing" means here

The bar is already written down. VISION.md (locked 2026-06-08) says a front-facing
flagship app must:

1. Run **local-first with zero Willow and zero Postgres** — local SQLite only,
   graceful no-ops for cloud/LLM extras.
2. Work on a stranger's machine from a cold start (`make run app=the-squirrel`
   → working app, no env vars, no database server, no seed rituals).
3. Have an honest catalog entry and a warm surface.

The Squirrel is currently in the "support/keep" tier at ~80% maturity,
catalog status `coming_soon`. This plan promotes it to the flagship bar.

---

## Where the app actually stands (July 2026)

**Strong — keep as-is:**
- Full three-file stack per the 2026-04-15 design: `squirrel_app.py` (HTTP :8425,
  7 GET routes + write/chat APIs), watcher, responder with complete command grammar.
- Web UI with 4 era skins, People/Tree/Stash/Sources/Stories views.
- GEDCOM import/export, binder promotion engine, 779-archive source registry,
  Jeles personas, test suite across db/commands/gedcom/formatter.
- Level 2 + Level 3 security audits closed (2026-04-15), SAP gate threaded through
  all PII read/write paths in `db/persons.py` and `db/fragments.py`.

**Blocking front-facing status:**

| # | Gap | Evidence |
|---|-----|----------|
| G1 | **Postgres-only storage.** The whole `db/` package rides psycopg2 → schema `the_squirrel` in the Willow Postgres. | `db/__init__.py` pool, `requirements.txt` (single dep: psycopg2-binary) |
| G2 | **Willow import-time dependency.** `db/__init__.py` raises if `WILLOW_CORE` unset; imports `user_lattice` constants. | `db/__init__.py:24` |
| G3 | **The bootstrap shim.** `squirrel_app.py` fakes G2 by *writing a synthetic `user_lattice.py` to disk at import time* and defaults `SAP_AUTHORIZED=1`. It proves the Willow dep is just five constants — and it silently self-authorizes the PII gate. Front-facing code can't ship a self-written fake dependency. | `squirrel_app.py:20-31` |
| G4 | **Catalog entry is wrong.** Description says "Local-first data hoarding and organization" — the genealogy identity is missing entirely. Status `coming_soon`. | `catalog.json` |
| G5 | **Packaging drift.** pyproject v1.0.0 vs manifest v2.0.0; pyproject declares zero dependencies (app needs `markdown`, `watchdog`, `psycopg2` today); README claims `pip install safe-app-the-squirrel` which isn't published. | `pyproject.toml`, `README.md` |
| G6 | **No cold-start path.** First run on a clean machine: no DB, no seeded sources, no sample data, empty views with no guidance. | `migrate.py` targets Postgres only |

---

## The phases

Ordered so each phase is independently landable. Phase 1 is the long pole;
everything else is small by comparison.

### Phase 0 — Truth pass (half a day)

Make every claim the repo makes about The Squirrel true.

- [ ] Rewrite the `catalog.json` entry: genealogy identity, real description
      ("Genealogy companion… put fruit back on the family tree"), tags
      `family, history, local, genealogy`. Keep status `coming_soon` until Phase 5.
- [ ] Sync `.willow/store/` catalog record (store rule: `.willow/store/` is
      authoritative, keep both aligned).
- [ ] Version sync: pick one version (recommend `2.1.0-dev`), set it in both
      `pyproject.toml` and `safe-app-manifest.json`.
- [ ] Declare real dependencies in `pyproject.toml`; either publish the package
      or change README install instructions to the honest path
      (`make run app=the-squirrel`).

### Phase 1 — Standalone storage (the gate; the bulk of the work)

Goal: `python squirrel_app.py` works on a machine that has never heard of
Willow or Postgres. This is the one architectural change in the plan.

- [ ] **Vendor the lattice constants.** The shim in `squirrel_app.py` already
      proves `DOMAINS / TEMPORAL_STATES / DEPTH_MIN / DEPTH_MAX / LATTICE_SIZE`
      are five plain constants. Create `db/lattice_constants.py` holding them;
      import from real Willow (`WILLOW_CORE`) only when the env var is present,
      fall back to the vendored module otherwise. Delete the fake-file-writing
      shim from `squirrel_app.py` entirely.
- [ ] **Storage backend seam.** Introduce `db/backend.py` with a minimal
      interface (connect / execute / query / transaction). Two implementations:
      - `SQLiteBackend` — default. File at `~/.squirrel/squirrel.db`. WAL mode.
      - `PostgresBackend` — current behavior, selected only when
        `WILLOW_DB_URL` (or `SQUIRREL_BACKEND=postgres`) is set. Willow
        integration becomes the *optional* mode, exactly per VISION.md
        ("cloud is a demo mode, not the product").
- [ ] **Port the schema.** Translate `migrate.py` levels 1–3 (persons,
      relationships, fragments, tree_branches, lattice cells, sources, events,
      media) to SQLite DDL. Postgres FTS on `source_registry` → SQLite FTS5
      virtual table. Auto-migrate on first connection — no manual migrate step
      for the SQLite path.
- [ ] **Seed sources on first run** from `data/community_history_archives.json`
      (the 779 archives already live in-repo — the seed is free).
- [ ] **Keep the SAP gate calls intact.** Every `authorized()` call site in
      `db/persons.py` / `db/fragments.py` survives the refactor untouched.
      The gate's *policy* is Phase 4 territory (USER's pieces); the plumbing
      must not regress here.
- [ ] **Tests run on SQLite by default.** conftest points at a temp SQLite file;
      the Postgres path keeps a smaller opt-in test marker. This also unblocks
      CI on any runner.

Exit criteria: fresh clone, `pip install -r requirements.txt`,
`python squirrel_app.py` → browser opens, `@squirrel: add person …` works,
`@squirrel: find sources Iowa 1880s` returns acorn cards. No env vars set.

### Phase 2 — First-run experience (1–2 days)

The difference between "runs on a stranger's machine" and "welcomes a stranger."

- [ ] Cold-boot flow: create `~/.squirrel/`, create DB, seed sources, write the
      welcome block into a fresh `Squirrel.md`, print the URL. One command.
- [ ] **Demo tree, opt-in.** Convert `backfill_oscar_mann.py` into
      `@squirrel: demo load` — seeds the Oscar Mann line as clearly-labeled
      sample data (`is_demo` flag) with `@squirrel: demo clear` to remove it.
      A genealogy app with an empty tree sells nothing; a demo line lets the
      Tree/People/Stories views show what they're for.
- [ ] Empty states for every web view ("No people yet — try
      `@squirrel: add person …` or `@squirrel: demo load`").
- [ ] Honest degradation notices: Ollama absent → status bar says "Journal mode
      only — install Ollama to invite Jeles in," never a stack trace.

### Phase 3 — The front door (1 day)

The ad, made real. This is the touching-commercial energy pointed at the
honest product.

- [ ] Store card copy + a `docs/front-door.md` landing page: the counter-pitch
      to the genetics-testing ads. Core line of attack: *they sell you the
      feeling and keep your genome; The Squirrel gives you the feeling and
      keeps nothing.* "Your tree stays in your tree."
- [ ] Screenshots: one per skin (mcm/80s/00s/20s), Tree view with the demo
      line loaded. Store the set under `docs/media/`.
- [ ] 60-second walkthrough doc: cold start → add person → link → tree →
      stash → bind → export GEDCOM.

### Phase 4 — Security/safety seams (USER's pieces plug in here)

> **Update 2026-07-15:** the gate-policy seam is FILLED — willow-gate is wired
> in as the backend of `sap/core/gate.py`. Two actors: `journal` (user; Steady —
> read/write/export) and `jeles` (LLM; Rookie — read-only, loud, export denied
> by the trust table). `SAP_AUTHORIZED=1` no longer grants anything; no actor
> context → denied. GEDCOM export gates on the export flag. Ledger at
> `~/.squirrel/willowgate/` (PGP-encrypted when `WILLOWGATE_KEY_FPR` is set).
> Policy pinned by `tests/test_gate.py`.

- [x] **The self-authorization handoff.** `SAP_AUTHORIZED=1` is dead as an
      authorization path — removed from `squirrel_app.py` and `tests/conftest.py`;
      the env var now grants nothing. Authorization = a willow-gate check-in
      with an HMAC-bound identity, capped at a registered trust ceiling.
      `bypass(reason)` remains the explicit operator escape hatch for scripts.
- [ ] **Single PII chokepoint, verified.** One grep-provable invariant:
      no module outside `db/persons.py` and `db/fragments.py` touches PII
      tables. Add a test that enforces it so the invariant survives future work.
- [ ] **Manifest stays truthful.** `data_streams` privacy tiers re-checked after
      the storage refactor (`client_only` becomes literally true once data is
      a local SQLite file). `local_processing` re-scored.
- [ ] Inventory doc: what USER's existing security pieces are, and which seam
      each one claims (gate policy / at-rest encryption / network egress /
      export consent). Written together when the pieces are introduced.

### Phase 5 — Release flip (half a day, after 0–4 land)

- [ ] Version to `2.1.0`. Changelog.
- [ ] Catalog status `coming_soon` → `beta` in both `catalog.json` and
      `.willow/store/`.
- [ ] Verify success criteria 1–7 from the 2026-04-15 design spec still pass,
      now with zero env vars on the SQLite path.

---

## Sequencing and effort

```
Phase 0 (0.5d) ──► Phase 1 (3–5d) ──► Phase 2 (1–2d) ──► Phase 3 (1d) ──► Phase 5 (0.5d)
                        │
                        └──► Phase 4 (define-only, runs alongside 2–3;
                             closes when USER introduces the security pieces)
```

Phase 0 can land today. Phases 2 and 3 are parallelizable once 1 lands.

---

## Risks / open gates

1. **Dual-backend drift.** Two SQL dialects will diverge unless tests run the
   same suite against both. Mitigation: backend test matrix; SQLite is the
   default CI path, Postgres a marker.
2. **FTS parity.** Postgres `tsvector` and SQLite FTS5 rank differently; source
   search results may reorder. Acceptable — assert membership, not order.
3. **Existing data in the Willow Postgres.** USER's current tree lives in schema
   `the_squirrel`. Needs a one-shot export: either GEDCOM round-trip (already
   built) or a direct `pg → sqlite` copy script. Decide before Phase 1 exit.
4. **Lattice constants provenance.** Vendoring assumes the five constants are
   plain configuration, not licensed Willow internals. The shim already
   duplicates them in-repo, so this is de-facto settled — flagging anyway.
5. **Gate posture during the gap.** Between Phase 1 (shim removed) and USER's
   security pieces landing, the app must not be *less* safe than today.
   Default-deny with documented dev override is the interim posture.
6. **`pip install` claim.** Publishing to PyPI is a real commitment (name,
   maintenance). Recommend dropping the claim until there's a reason.

---

ΔΣ=42
