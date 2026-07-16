# Changelog — The Squirrel

## 2.1.0 — 2026-07-16 · the front-facing release

The flagship bar, cleared: zero Willow, zero Postgres, zero network.

### Storage
- SQLite is the default backend — one file in `$SQUIRREL_HOME` (default
  `~/.squirrel`), auto-migrated on first connection, 779-archive source
  registry seeded from the repo. Postgres is now the opt-in Willow mode
  (`SQUIRREL_BACKEND=postgres` / `WILLOW_DB_URL`).
- The 23-cube lattice was excised — `DOMAINS`/`TEMPORAL_STATES`/depth,
  the `*_lattice_cells` tables, `place_in_lattice`/`_validate_lattice`,
  and the `WILLOW_CORE`/`user_lattice` import machinery (including the
  boot-time fake-module shim). willow-2.0 retired that model for
  canonical lanes; nothing live in the app wrote or read the cells, so
  "zero Willow" is now literal rather than "zero except a defunct import."

### Security (the stack, in the order it was wired)
- **Gate** — `sap/core/gate.py` backed by willow-gate: HMAC-bound actors
  `journal` (Steady: read/write/export) and `jeles` (Rookie: read-only,
  export denied by the trust table). `SAP_AUTHORIZED=1` grants nothing.
- **Receipts** — every tool call logged locally in the willow-data-vault
  schema; `@squirrel: receipts` reads the trail.
- **Vault** — Fernet secret store + provisioned box (0700, keys 0600);
  secrets enter by terminal prompt, never through the journal.
- **Consent + the divider** — the Privacy page: ONLINE, THE AI, THE
  TRAIL, GO QUIET. Wikipedia demoted to a deep link; the app makes zero
  outbound calls (localhost Ollama excepted), enforced by test.
- **Chokepoint** — no PII SQL outside `db/`, proven by test; GEDCOM
  export, binder, and person edits rerouted through gated functions.

### First run
- `@squirrel: demo load` / `demo clear` — the fictional Acorn line:
  nine persons, full three-generation pedigree, stash fragments.
- `@squirrel: status` reports vault and Jeles availability honestly.

### Docs
- `docs/front-door.md`, `docs/walkthrough.md`, screenshots in
  `docs/media/` taken from the app running cold in a fresh container.

## 2.0.0 — 2026-04-15 · Level 2 rebuild
Full-stack build per the April design: three-file stack, command
grammar, four era skins, GEDCOM import/export, binder, web views,
stories room. Postgres storage; SAP gate stub.

ΔΣ=42
