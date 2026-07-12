# SAFE App Installer — Design Decision Log

> Status: **design / talk-through** (no implementation yet).
> A living record of decisions for the willow-mcp install tool that installs
> sovereignty-verified local apps onto the host. Append as decisions land.

## Purpose

An MCP tool in willow-mcp that installs applications from an operator-curated,
sovereignty-verified list onto the local machine — safely, through the same
gate / consent / kart / ledger circuit already proven to run together.

## Decisions

### D1 — Install source is the operator-attested sovereignty list
The installer pulls **only** from `rudi193-cmd/awesome-sovereign-software`
(`data/apps.yaml`, 77 entries). Every entry has been **hand-verified by the
operator** against the repo's five-point Sovereignty Test (runs without an
account / without a server / no subscription / data readable without the app /
survives the vendor).

The installer **never re-judges sovereignty** — it honors an allow-list the
operator signed off on out-of-band. (Same trust model as willow-gate: secrets
and ceilings are registered out-of-band; the machine only verifies against that
registration.)

### D2 — Two per-tool properties; one is verified, one is earned
- **Fully local** — attested by the operator via the Sovereignty Test. **Done.**
- **Outwardly-facing compatible** — NOT a claim anyone types. It is an **earned
  receipt**, stamped only after a real install-through-the-system succeeds and
  the app launches. (Same shape as the trust ladder: earned, not asserted.)

  As of this writing, **zero of the 77 have been installed through the system** —
  outward-compatibility is the untested frontier, not an established fact.

### D3 — Install boundary posture: "sandbox with a seam"
All dangerous work — fetching the artifact, verifying checksum/signature,
unpacking, staging — happens **inside kart's bubblewrap sandbox** (with
`task_net`). Only a **verified, declarative placement plan** crosses the seam to
the host.

**The seam moves data, never code, and never at vendor privilege.** No vendor
installer script ever runs with host privilege. The host-side operation is
deliberately dumb and auditable: copy already-fetched, already-checksummed files
to declared destinations. Governed by operator consent + a PGP ledger entry
recording exactly what was placed where.

```
┌─ SANDBOX (kart, task_net) ────────────┐        ┌─ SEAM (host, server uid) ─┐
│ fetch artifact from source            │        │ validate plan vs policy   │
│ verify checksum/signature vs recipe   │ ─plan─► │ (dest in allowlist? no    │
│ unpack / stage                        │        │  /etc, no setuid…)         │
│ emit signed placement plan            │        │ copy staged → dest         │
└───────────────────────────────────────┘        │ ledger (PGP)               │
                                                   └──────────┬────────────────┘
                                                   smoke-launch → stamp receipt
```

### D4 — The seam defines compatibility
An app is "outwardly-facing compatible" iff it can be installed by **verified
file-placement into a user-scope allowlist**. AppImage, Flatpak `--user`, and
static binaries pass; apps needing a root package manager, post-install scripts,
or a GUI click-through **fail the seam** — which is the correct answer, not a
limitation. The mechanism draws the compatibility line; the receipt is stamped
only after a real placement + launch succeeds.

### D5 — Seam holder is the willow-mcp server process
The sandbox produces the plan; the **willow-mcp server process** (the
more-privileged "server uid, full filesystem view" lane it already reasons about
for `integration_net`) performs the placement, gated by consent + ledger. The
privilege split already exists in the architecture; the seam reuses it.

### D6 — On-disk layout: a "SAFE" folder, apps and data separated
Installed apps land in a top-level folder labelled **`SAFE`**:

- **Apps** live under **`SAFE/apps/<app_id>/`**.
- **Stored data** goes to a **separate folder** (NOT under `apps/`) — this is the
  **data vault** (see D7), not a subfolder of the app payload.

Separating app payload from app data keeps installs disposable (uninstall =
remove/-archive the app dir) without touching user data, and gives the seam a
clean destination allowlist to enforce.

### D7 — The data vault: persistent, sovereign, agents-can't-carry-out
The "separate data folder" of D6 is a **data vault** — the persistent, sensitive
counterpart to the replaceable `SAFE/apps/` payload layer. This yields a
three-layer separation:

1. **Compute / agents** — ephemeral, replaceable (kart sandbox, MCP server, the agents).
2. **Apps** — `SAFE/apps/<app_id>/`, replaceable payloads installed via the seam.
3. **The vault** — persistent and sensitive: schemas, KB, DB, sensitive files,
   user-specific files. Agents operate against it **in place** but **cannot carry
   it out**.

**Repo is blueprint, not data.** A `willow-data-vault` repo holds only the
**schemas + container bootstrap** needed to stand willow up **as its own box**
(DB/KB schema, migrations, config, structure). A fresh willow instance is
provisioned *from* the repo, then populated **locally** with KB/DB/PII/user data
that is **never committed back to git** — matching existing precedent (Law
Gazelle PII lives in `~/Desktop/Nest/`, never in git). The repo is *how to build
the box*; the running box is *the populated instance that stays home*.

"Cannot carry out" is already enforceable with existing primitives:
- **gate `store_scope`** — an agent only sees its own collections.
- **kart bubblewrap** — a sandboxed task cannot reach host files.
- **consent.py** — presence/sensitive data never leaves the house.

The vault is simply the **named boundary** those three were implicitly
protecting. It is the disciplined opposite of an unstructured PII dump: schema'd,
scoped, and boundary-enforced.

> Off-limits: the operator's existing `sean-data-vault` is a raw PII dump and is
> **never to be read, cloned, searched, or otherwise accessed** by any agent. It
> is not the model here; `willow-data-vault` (structured, blueprint-not-data) is.

### D8 — App data routing: one vault root, no hardcoded home paths
D7 gives the vault a boundary; D8 is the rule that makes apps actually respect
it. **An app must resolve ALL persistence from a single vault-rooted base.** Any
`Path.home() / ".willow" / …` (or other fixed home path) baked into app code is a
**vault leak** — it writes user data *past* the vault to a scattered, unscoped
location, defeating the "agents can't carry it out" boundary.

The vault box is necessary but not sufficient: it captures only what the app
chooses to route through the vault root. Nothing yet forces that choice, so apps
self-select where they write — and today they scatter.

**Worked example — `ask-jeles` (found by running it, 2026-07-12).** Ran with no
`WILLOW_STORE_ROOT` set; real data (binder intake, log) landed in `~/.willow`,
not a vault. Its persistence splits:

| Data | Path | Vault-aware? |
|---|---|---|
| corpus `store.db` | `WILLOW_STORE_ROOT/<collection>/store.db` | ✅ yes — and uses the SOIL `records` schema (`02_soil_records.sql`) |
| KB SOIL reads | `WILLOW_STORE_ROOT` | ✅ yes |
| binder intake (permanent user data) | `APP_DATA` (`~/.willow/apps/ask-jeles`) | ⚠️ env var, wrong root |
| learning_events (consented, sensitive) | `~/.willow/jeles_learning_events` | ❌ hardcoded — leak |
| kb_views / saves / log | `~/.willow/jeles_*` | ❌ hardcoded — leak |

The corpus is already vault-shaped (point `WILLOW_STORE_ROOT` at the box and it
lands in the vault, on the vault's own schema). Everything else — including the
*sensitive* streams (binder deposits, learning events) — hardcodes home paths and
leaks. Collection-scoping (`<root>/<collection>/store.db`) is the natural hook for
per-app `store_scope`: collection-scoped is app-scoped.

**Rule:** installer/compat check should flag any `Path.home()/".willow"` (or
equivalent fixed-home) write in an app as a vault leak before it earns the
outward-compatible receipt. An app is vault-clean only when every persistence
path derives from the vault root.

#### D8.1 — Fleet scan + the data-vs-config refinement
Scanned all 23 apps (2026-07-12). Two refinements fell out of reading the
*actual* paths (raw grep counts over-report):

**The leak that matters is user DATA, not config/cache.** A DB of user data in a
fixed home path is a leak; a config file (`~/.squirrel/config.json`) or an XDG
cache (`~/.cache/nest-seed`) is fine. The linter MUST classify — otherwise it
cries wolf on `the-squirrel` (config only; store is vault-routed) and `nest-seed`
(cache only). Leak = data (DBs, case files, deposits) at a fixed path; allowed =
config/cache in home/XDG.

**Fleet alignment:**

| Verdict | Apps |
|---|---|
| ✅ vault-aware (data routed) | utety-chat, the-binder, public-ledger, nasa-archive, the-squirrel, llmphysics-bot, UTETY-Reddit-Bots |
| ✅ config/cache in home (fine) | nest-seed (`~/.cache`), the-squirrel (`~/.squirrel`) |
| ⚠️ MIXED — vault-aware layer but leaks data | **law-gazelle**, ask-jeles, private-ledger, field-notes |
| ❌ data leak, no vault routing | story-timeline, civics-check, semantic-translator, ratatosk |
| — no local persistence | bt-controller, llmphysics, vision-board |

**Priority leak — `law-gazelle` (highest stakes in the fleet).** Its
`safe_integration.py` uses `WILLOW_STORE_ROOT`, but the legal **case files and
client PII** are hardcoded: `case_store.py` → `~/.willow/apps/law-gazelle/cases/`
**and** `~/Desktop/Nest/`; `client_profile.py` → `~/persona.md`. The most
sensitive data in the fleet sits in two ad-hoc home locations, honoring neither a
single root nor the vault. "Not in git" (`fleet_paths`) is not the same as "in
the vault" — it is still outside the boundary. Consolidating this into the
never-git vault box is the single strongest argument for D7.

**Subtle case — `story-timeline`.** Writes `timeline.db` to a *hardcoded*
`~/.willow/store/story-timeline/` — lands near the default vault path but ignores
a `WILLOW_STORE_ROOT` override. "Near the vault by luck" ≠ "honors the vault
root." The linter must catch hardcoded-default paths, not just non-`.willow`
ones.

## Reused patterns (already in the corpus)
- **Verify-don't-assert** — sovereignty and outward-compat are both verified/earned, never self-declared.
- **Path-containment allowlist** at the seam — same check as the utety-chat C6 path-traversal fix and the gate's `store_scope`.
- **Consent + PGP ledger** — install is a privileged, host-mutating, hard-to-reverse act; it is consented and ledgered like every other privileged lane.

## Appendix A — willow's persistence surface (extracted from willow-mcp)

D7 starting artifact. The blueprint is built from what willow **actually**
persists today (per `willow-mcp` @ `dcb87d2`), not invented. willow already
ships a Fernet secrets vault (`vault.py`) and a bootstrap (`willow-mcp-init`) —
so `willow-data-vault` is **extraction + separation**, not greenfield.

| Store | Module | Schema → **blueprint (repo)** | Data → **box (local, never git)** | Sensitivity |
|---|---|---|---|---|
| Secrets vault | `vault.py` | `secrets(name, value BLOB)` DDL | `vault.db` **+ `vault.key` (Fernet, 0600)** | **CRITICAL** |
| SOIL KV store | `db.py` | `records(id, data, created_at, updated_at, deviation, action, deleted)` DDL | record rows | user data |
| Receipts ledger | `receipts.py` | `receipts(id, ts, app_id, tool, outcome, detail)` DDL | tool-call audit trail | activity |
| Kart task queue | `task_queue.py` | `kart.db` DDL / `docs/schema/tasks.postgres.sql` | task rows | ops |
| KB (Postgres) | `schema_profile.py` | adapts to existing `tasks`/KB table (`schema-adaptation.md`) | KB rows | user knowledge |

Plus the `WILLOW_HOME` layout `willow-mcp-init` lays down — `config/`
(consent, roster, specialists), `mcp_apps/<app_id>/manifest.json` (the ACL),
`ledgers/` (PGP gate ledger), `personas/`, `skills/`, `seeds/`, `templates/`,
`hooks/`. The **structure** is blueprint; the **populated instance** is box.

**Linchpin:** the Fernet `vault.key` (0600) is the crypto root. It **never**
touches git. Copy the box's `vault.db` without the key and every secret in it is
meaningless — which is precisely the "agents can't carry it out" property, made
cryptographic rather than merely policy-enforced.

**So the blueprint = DDL (5 schemas above) + the `willow-mcp-init` bootstrap
structure + schema-adaptation logic.** The box = every populated store + the
key + real config + PGP ledger + user/sensitive files.

## Build status
- **D7 blueprint — SCAFFOLDED** at `rudi193-cmd/willow-data-vault` (`main`):
  owned schemas (secrets, SOIL, receipts, Kart SQLite+Postgres) extracted
  verbatim; KB shipped as adaptive reference; `bootstrap/provision.sh` stands up
  an empty box (CLI-optional). `.gitignore` hard-guarantees blueprint-not-data;
  verified schemas apply and no key/DB can be committed.

## Open / next
- **Where the running vault lives on disk** relative to `SAFE/` (the box path),
  and provisioning it end-to-end against a real willow-mcp box.
- **A vault-leak linter** (D8) — scan an app for `Path.home()/".willow"` and
  other fixed-home writes; make "vault-clean" a precondition of the
  outward-compatible receipt. `ask-jeles` is the first fix candidate
  (learning_events, kb_views, saves, log, intake → vault root).
- How **apps in `SAFE/apps/`** are granted scoped access to vault collections
  (per-app `store_scope`, so an installed app reaches only its own data).
- Per-app **install recipe** format (the "how": AppImage/Flatpak/binary) —
  `apps.yaml` currently carries homepages, not install methods.
- Destination allowlist specifics and uninstall/archive semantics.
