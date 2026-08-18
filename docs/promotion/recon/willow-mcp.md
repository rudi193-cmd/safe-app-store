# Promotion recon — what `rudi193-cmd/willow-mcp` requires of a promoted SAFE app

**Candidate:** `apps/homestead-health` (a local-first family-health-records Python
package `homestead_health/`, pinning the `homestead.keep` engine; `app_id`
`homestead-health`, `privacy_tier` `client_only`, no network, synthetic data).
**Target of analysis:** `rudi193-cmd/willow-mcp` @ `832b3c9` (cloned
`--depth 1`).
**Scout:** vishwakarma · autonomous promotion-readiness pass.

This report answers a narrow question: **when homestead-health is promoted to its
own repo, what does the willow-mcp server demand of it, and does it already
comply?** It cites willow-mcp files by path so each claim can be re-checked.

---

## 0. The one nuance that reframes everything

The cloned `rudi193-cmd/willow-mcp` is the **standalone product**, whose identity
gate is file-system-manifest based:

> `app_id` is passed on every tool call. An app is authorized when a manifest
> JSON file exists at `$WILLOW_HOME/mcp_apps/<app_id>/manifest.json`. The
> manifest's `"permissions"` list controls which tools the app may call.
> — `src/willow_mcp/gate.py:1-18`

This product **does not know the SAFE dev-fallback vocabulary** homestead-health's
`safe-app-manifest.json` speaks. A repo-wide search for `WILLOW_DEV_SAFE_ROOT`,
`safe-app-manifest`, `privacy_tier`, `data_streams`, or `dev_fallback` returns
**zero hits in the product code**. The design doc says why, explicitly:

> Port verification logic from `willow-2.0/sap/core/gate.py::_verify_pgp` — **do
> not port `dev_bypass` / `_DEV_SAFE_ROOT`.**
> — `docs/design/pgp-and-persona.md:51-52`

So SAFE dev-fallback auth (`WILLOW_DEV_SAFE_ROOT` + a root `safe-app-manifest.json`,
which is what `CLAUDE.md` and homestead-health use *today in the playground*)
lives in the **legacy fleet shim** `willow-2.0/sap/sap_mcp.py` — the README warns
`~/.local/bin/willow-mcp` "is often the **fleet** shim (`sap_mcp.py`), not this
product" (`README.md:96-99`, echoed in `docs/OPERATOR-ONBOARD.md:14`). The
standalone product resolves identity from an **operator-owned
`mcp_apps/<app_id>/manifest.json`**, a different file with a different schema from
the app's own `safe-app-manifest.json`.

**Consequence for promotion:** homestead-health's `safe-app-manifest.json` is the
*SAFE-store* manifest (author attribution, privacy tier, data streams — read by
the store's own tooling and the fleet shim). It is **not** the file the standalone
willow-mcp gate reads. If a promoted homestead-health is ever to be *served as a
willow-mcp app* under the standalone product, an operator must additionally author
(or compile) an `mcp_apps/homestead-health/manifest.json`. That file — not
`safe-app-manifest.json` — is where `permissions` and `store_scope` live for
willow-mcp's gate. See §2 and §3.

There is a second, larger nuance: **homestead-health is library-clean and calls
no willow MCP tools at all.** It uses the `homestead.keep` engine directly,
local-first, no network, no listener. willow-mcp's gate only governs code that
*calls willow tools under an app_id*. So for the current architecture, willow-mcp's
runtime demands on homestead-health are **latent/conditional** — they bind only
if/when someone serves homestead-health through willow-mcp. The store's own
`stores/promote_check.py` is what actually gates promotion, and its
"MCP-shaped **OR** library-clean" bar (`stores/promote_check.py:333-352`) lets
homestead-health promote as **library-clean** without ever touching willow-mcp's
gate. This report still enumerates the willow-mcp requirements, because the fleet
treats "scoped to its own SOIL collection, default-deny reach, no fleet-store
writes" (`CLAUDE.md` rules 6-7) as the standing wall, and willow-mcp is what
enforces that wall when the app *is* served.

---

## 1. FRANK — the shared governance ledger

### What FRANK is

FRANK is the fleet's **append-only, hash-chained Postgres ledger** (`frank_ledger`
table) for **settled** governance facts — "decisions taken, leases issued,
envelope citations, probe ids" — not drafts (`skills/frank.md:9-11,26-29`). Three
tools reach it, each separately permissioned:

| Tool | Permission | — |
|------|-----------|---|
| `frank_read` | `frank_read` | recent entries, optional `project` filter |
| `frank_verify` | `frank_read` | re-hash chain; reports break location |
| `frank_append` | `frank_write` | append one settled event |

(`skills/frank.md:17-20`; `README.md:157-159` — `frank_append` is "separately
gated").

The adapter is `src/willow_mcp/governance_ledger.py`; the append path
(`append()` → `_chain_insert()`, lines 89-140) takes a Postgres advisory lock,
reads the current head, and chains each row via `entry_hash_v2` over
`{id, project, event_type, content}` (lines 71-86).

### How a promoted app's own ledger relates to FRANK (the "#280" anchor)

Nestor is the worked example: it "**mirrors its hash-chained ledger into FRANK**"
— `a nestor ledger entry → frank_append → the hash chain` (`README.md:69-70`,
`README.md:87`). FRANK is therefore the **shared mirror target**: an app's own
ledger relates to FRANK by (optionally) mirroring settled events into it, which
buys the "someone else remembers" property.

But that property is only real with an **externally-held head anchor** — the
"willow-mcp #280" threat model, written down in
`src/willow_mcp/governance_ledger.py:1-33`:

> The chain is tamper-EVIDENT … NOT tamper-proof against the database operator:
> `rechain()` re-hashes rows from their current content … the migration and the
> forgery are the same operation. … The close is a head recorded somewhere the
> chain's writer cannot reach: `verify()` takes `expected_head` …
> **FRANK mirroring into this table gives Nestor "someone else remembers" ONLY
> to the extent that this someone's head is anchored outside; without an anchor
> it degrades to "someone else has a copy that will agree with whatever it now
> says."**

The anchor has a concrete home:
`$WILLOW_HOME/constitutional/frank_head_anchor.json`, **CLI-written only** — no
MCP tool wraps `write_anchor()` (`src/willow_mcp/frank_head_anchor.py:22-26,110-117`),
mirroring the "an agent may request standing, never mint it" invariant. `rechain()`
refuses to migrate if the on-disk anchor disagrees with the live head, and
fail-closes on an untrusted/unreadable anchor file
(`governance_ledger.py:207-275`).

### Must a promoted app register/mirror into FRANK?

**No — not as a hard requirement, and not by default.** Findings:

1. **FRANK is opt-in and permission-gated.** Writing requires `frank_write` in the
   app's `mcp_apps/<app_id>/manifest.json`; a manifest without it is denied
   (`gate.py:12` fail-closed). Nothing in willow-mcp *forces* an app to hold
   `frank_write`.
2. **FRANK is for *governance* facts, not app data.** The append discipline is
   explicit: "Write **settled** events only … Do not use `frank_append` for
   speculative or draft state" (`skills/frank.md:26-29,48-49`). Nestor mirrors
   because Nestor *is* the fleet's governance witness. A `client_only`,
   no-network family-records app has no governance facts to contribute.
3. **FRANK needs Postgres.** All three tools "require Postgres … If Postgres is
   down, tools return `postgres_unavailable`" (`skills/frank.md:21-23`).
   homestead-health is local-first and Postgres-free by design.

**homestead-health is already FRANK-*compatible* in the one way that matters,
without being FRANK-*dependent*.** Its own ledger — `homestead.keep`'s
`IntegrityLog` — already implements the exact #280 discipline FRANK asks of a
mirror source: per the app README, bite 5 keeps "the head anchor held **off the
log's own tree** and returned to record off the machine, so a hand-edited entry
fails `verify(expected_head=…)`", and the living lane (H-8) writes a
`living_replaced` line "carrying the thing's ref and the SHA-256 of the value it
replaced, anchor off-tree, `verify(expected_head)` catches a hand-edit"
(`apps/homestead-health/README.md:37-43,73-79`). `docs/DECISION-living-lane-ledger.md`
records the deliberate read of Nestor's ledger before choosing to reuse keep's
`IntegrityLog`. That is the same externally-held-head close FRANK's
`frank_head_anchor.py` provides — arrived at independently.

**Verdict:** ✅ **Satisfied / N-A.** No FRANK registration or mirror is required
of a promoted homestead-health. Should the fleet ever want its egress/record acts
mirrored into FRANK, the app already carries a #280-shaped ledger with an
off-tree anchor, so the seam would graft cleanly — but that is a future opt-in
(operator grants `frank_write`, Postgres present), not a promotion gate.

---

## 2. dev-fallback auth, the manifest, and `WILLOW_DEV_SAFE_ROOT`

### What the standalone product actually reads

- **Identity** = `app_id` on every tool call + an operator-owned
  `$WILLOW_HOME/mcp_apps/<app_id>/manifest.json` (`gate.py:1-6,33-35,497-499`).
- **`app_id` charset:** `^[a-zA-Z0-9_\-]{1,64}$` (`gate.py:30`, `_validate_app_id`
  `gate.py:38-41`).
- **Manifest schema the gate consumes:** `app_id`, `permissions` (list of group
  names and/or literal tool names — `PERMISSION_GROUPS`, `gate.py:51-53`),
  optional `store_scope`, `collection_aliases`, `egress_secret_exempt`,
  `deny_tools` (`registry.py:74-88`, `gate.py:621-706`).
- **Fail-closed everywhere:** "missing app_id, missing manifest, or empty
  permissions → deny" (`gate.py:12`).
- **Optional PGP enforcement:** set `WILLOW_PGP_FINGERPRINT` and an unsigned or
  tampered manifest "is treated exactly like a missing one (deny)"
  (`gate.py:13-18,505-524`). Off by default (single-operator file-system trust).

### `WILLOW_DEV_SAFE_ROOT` / `safe-app-manifest.json`

As established in §0, **these are not part of the standalone product.** They are
the legacy fleet-shim (`sap_mcp.py` / `sap/core/gate.py`) dev bypass, explicitly
**not** ported (`docs/design/pgp-and-persona.md:51-52`). homestead-health's
`safe-app-manifest.json` (app_id, permissions `["file_write"]`, `privacy_tier`
`client_only`, `data_streams`, `local_processing`) is the **SAFE-store** manifest
— read by the store and the dev shim, not by this gate.

### Does homestead-health satisfy this?

| willow-mcp requirement (standalone gate) | homestead-health today | Verdict |
|---|---|---|
| Well-formed `app_id` (`gate.py:30`) | `homestead-health` (17 chars, hyphen OK) | ✅ |
| A gate manifest at `mcp_apps/<app_id>/manifest.json` with a non-empty `permissions` list | Ships only `safe-app-manifest.json` (SAFE schema); no willow gate manifest | ⚠️ **Gap — but only if served via willow-mcp.** The `file_write` permission in `safe-app-manifest.json` is a SAFE permission, **not** a willow tool group (willow's `KNOWN_PERMISSIONS` are `store_*`, `knowledge_*`, `task_*`, `frank_*`, … — `manifest_admin.py:33-35`, `gate.py:51-53`). If homestead-health is to be a served willow app, an operator must author/compile a separate `mcp_apps/homestead-health/manifest.json` naming actual willow tool groups. Because the app currently calls **no** willow tools, this manifest is not needed for its function; it is an operator-side install artifact, authored at deploy time, not something the app repo must ship. |
| PGP-signed manifest (only if `WILLOW_PGP_FINGERPRINT` set) | N-A until served; signing is operator-side | ✅ N-A (off by default) |

**Verdict:** ✅ for identity shape; ⚠️ **conditional gap**: no willow gate manifest
exists, but one is only required at *deployment as a served willow app*, and it is
an **operator-owned** artifact (see §4) — not a file the promoted repo must carry.

---

## 3. Store-scope / SOIL collections — the default-deny lane wall

### What willow-mcp enforces

Each app is confined to its own SOIL collection(s) by the manifest `store_scope`
field. `gate.store_scope()` (`gate.py:621-663`) has three outcomes, and the
difference is the whole point:

- **Field absent, or explicit `null` → `None` → *unrestricted*** — the app sees
  "every collection in whatever store `WILLOW_STORE_ROOT` resolved to"
  (`gate.py:626-630`, `db.py:38-47`). Opt-in isolation, not retroactive lockdown.
- **Present and well-formed → that list.** Exact names and/or `prefix*` wildcards;
  `[]` denies everything (`gate.py:631-632`, `db.collection_in_scope`
  `db.py:35-57` — `*`-suffix = prefix match, else exact).
- **Undeterminable (bad app_id / missing / unreadable / malformed `store_scope`)
  → `[]` → deny-all**, fail-closed (`gate.py:633-662`). A typo like
  `"store_scope": "myapp_*"` (a string, not a list) confines rather than releases.

`collection_permitted()` (`gate.py:666-669`) is the enforcement call; the store
tools (`store_put/get/search/search_all/…`) are narrowed to it, and
`store_collections`/`store_stats` only show collections within scope
(`README.md:114-116`). This is exactly `CLAUDE.md` rule 6: "a collection outside
an app's `store_scope` is denied."

### What an app must declare

To be *confined* (rather than unrestricted-within-the-store), the app's willow
gate manifest **must carry a `store_scope`** naming its own collection(s), e.g.
`["homestead_health_*"]` or the explicit collection names it writes. Omitting it
means unrestricted reach on whatever store the process resolved — which, on a
**shared** store, defeats the lane wall. The app **cannot self-grant** scope
(§4).

### Does homestead-health satisfy this?

- homestead-health **does not use willow's SOIL store at all** — it persists
  through `homestead.keep`'s own record layer (`roster.py`, the packs, the export
  path), keyed by opaque subject ids, `client_only`, no network. So at runtime it
  touches **no** willow collection, and the store-scope wall has nothing to gate.
  This is *stronger* than compliance: the app has no fleet-store reach to confine.
- Its `safe-app-manifest.json` has **no `store_scope` field** — expected, since
  that file is not the willow gate manifest and the app has no willow store lane.

**Verdict:** ✅ **Satisfied by construction** for the current architecture (no
willow store use → nothing to over-reach). **Gap to close only at
willow-served deployment:** if homestead-health is ever wired to willow's SOIL
store, its operator-authored `mcp_apps/homestead-health/manifest.json` **must**
declare a `store_scope` (a `homestead_health_*` prefix is the natural choice), or
it is silently unrestricted within the resolved store. Recommend recording this as
a promotion note so the deploy step isn't left to default.

---

## 4. Self-grant wall — sandboxed, cannot mint its own authority

willow-mcp enforces `CLAUDE.md` rule 7 ("Playground builds are sandboxed and
cannot self-grant") structurally, on two layers:

1. **The manifest is operator-owned; the app cannot write it.** `manifest_admin.py`
   backs the `willow-mcp allow-permission` / `deny-permission` **CLI** subcommands
   only — "writing it must never be reachable from an MCP tool call — an agent
   could otherwise grant itself whatever it was just denied … **Do not wire this
   into an `@mcp.tool()`**" (`manifest_admin.py:1-14`). Manifests are normally
   compiled from the `specialists.json` registry via `registry.compile_manifests`
   (`registry.py:100-202`), an operator/CLI path.
2. **The PreToolUse hook blocks self-grant attempts** — minting a net lease under
   `mcp_apps/_net_leases/`, editing a `manifest.json` to add an egress capability
   (`task_net`/`integration_net`/`web_net`), or adding a write-capable permission
   group or a bare `"store_scope": ["*"]` (`hooks/pre_tool_use.py:26-34,501-509,
   549-658`). `mcp_apps/` is mounted `bound_ro` so the write fails with EROFS even
   if the guard is bypassed (`pre_tool_use.py:506`).

**Does homestead-health satisfy this?** ✅ **Yes, trivially.** It ships no
willow-manifest-writing code, mints no leases, requests no egress, and runs no
listener (the seat's own tests assert "nothing imports the network, nothing
listens" — `apps/homestead-health/README.md:59-61`). A top-level network-import
scan of `homestead_health/*.py` is clean (matches `promote_check.py`'s
`import_pure_core` gate, `stores/promote_check.py:382-394`). There is no authority
for it to widen.

---

## 5. Attestation / governance a promoted app registers

**willow-mcp does not run a promotion-attestation mechanism for external apps.**
Its governance surface is exactly three things, all covered above:

- the **manifest ACL gate** (§2), optionally PGP-signed;
- the **FRANK ledger** (§1), opt-in and Postgres-backed;
- the **self-grant wall** (§4).

The *promotion attestation* itself is the **store's** concern, enforced by
`stores/promote_check.py`, which reads a `promotion.json` and checks nine gates
(witnessed / own-repo / host-repointed / manifest / tests-green / vault-leak /
import-pure-core / inversion / semantic-seam). Its optional `trust` block is the
only place the two worlds touch: a cryptographic seal path that lazily imports
`willow_gate.custody`, `forge.trust`, and `nestor.keyring`/`nestor.signing`
(`stores/promote_check.py:197-298`). That seal is **opt-in**; the floor is the
string check `verified_by` set and `≠ author` (§0.2), and a promotion with no
`trust` block "keeps this script stdlib-only" (`promote_check.py:42-44`).

**homestead-health readiness against the store gate (for context, not
willow-mcp's ask):**

| `promote_check.py` gate | homestead-health | Status |
|---|---|---|
| `promotion.json` present | **absent** | ❌ **Must author before promotion** (`author`, `verified_by`≠author, `repo_url` = its own repo, `host`, `core_module: homestead_health`, `semantic_seam`, `host_repointed`) |
| `witnessed` — `verified_by ≠ author` | README says the extension is "proposed, not ratified (`verified_by ≠ author`)"; author is `USER` | ⚠️ needs a distinct verifier named in `promotion.json` |
| `own_repo` — not the store monorepo | target `rudi193-cmd/homestead-health` | ✅ (once repo exists) |
| `manifest` (safe-app-manifest **or** pyproject) | both `safe-app-manifest.json` and `pyproject.toml` (`[project].name = homestead-health`) present | ✅ |
| `tests_green` | `tests/` present; README claims **128 passed / 0 xfailed** | ✅ (verify at gate time) |
| `import_pure_core` | no top-level network imports in `homestead_health/` | ✅ |
| `inversion` — core doesn't import host | consumes `homestead.keep` only through its public API, host not imported | ✅ (assert via `host` field) |
| `semantic_seam` — `module:symbol` defined | `homestead_health/reference_lane.py` defines `class Reader` / `def ask` (`reference_lane.py:212,231`) — an **injected reader over its own knowledge corpus**, exactly the bar's "semantic-search seam over its own injectable knowledge" | ✅ propose `semantic_seam: "homestead_health.reference_lane:Reader"` |
| `vault_leak` — no user data at a fixed path | `client_only`, keep-mediated storage; verify at gate time | ✅ (run the lint) |

This table is the store's bar, included because it is where the concrete
pre-promotion work sits; **willow-mcp asks none of it.**

---

## 6. Summary — requirements vs. compliance

| # | willow-mcp requirement of a promoted SAFE app | homestead-health | Gap to close |
|---|---|---|---|
| 1 | Register/mirror into **FRANK** | Not required; opt-in, `frank_write`-gated, Postgres-backed, for governance facts only. App already carries a #280-shaped off-tree-anchored ledger via `homestead.keep` | **None.** (Optional future opt-in if fleet wants mirroring.) |
| 2 | Well-formed `app_id` on every tool call | `homestead-health` matches `^[a-zA-Z0-9_\-]{1,64}$` | None |
| 3 | Operator-owned gate manifest `mcp_apps/<app_id>/manifest.json` with non-empty `permissions` | Ships SAFE `safe-app-manifest.json` only; calls no willow tools | **Conditional:** author a willow gate manifest **only if** served as a willow app. Not required for the library-clean promotion path. Operator-side artifact. |
| 4 | **`store_scope`** confining the app to its own SOIL collections (else unrestricted-in-store) | Uses no willow SOIL store; nothing to over-reach | **Conditional:** if ever wired to willow's store, declare `store_scope` (`homestead_health_*`) in the gate manifest. Record as a deploy note. |
| 5 | **No self-grant** (sandboxed; can't write manifest, mint leases, add egress/scope="*") | No manifest-writing code, no leases, no egress, no listener, network-pure core | None |
| 6 | PGP-signed manifest (only when `WILLOW_PGP_FINGERPRINT` set) | Operator-side, off by default | None (N-A) |
| 7 | (store gate, not willow-mcp) `promotion.json` + nine `promote_check.py` gates | Most gates already green; `reference_lane:Reader` is the semantic seam | **Author `promotion.json`** with a verifier `≠ author`; run `stores/promote_check.py` at gate time |

### The two real, actionable items

1. **`promotion.json`** (store-side gate, not willow-mcp): author it before
   promotion, with `verified_by ≠ author`, `core_module: homestead_health`, and
   `semantic_seam: homestead_health.reference_lane:Reader`. This is what actually
   blocks promotion today.
2. **A deploy note** recording that *if* the promoted app is ever served through
   the **standalone** willow-mcp, the operator must author
   `mcp_apps/homestead-health/manifest.json` with willow tool-group `permissions`
   and a `store_scope` of `homestead_health_*` — because that product ignores
   `safe-app-manifest.json` and `WILLOW_DEV_SAFE_ROOT` (the dev-fallback lives in
   the legacy `sap_mcp.py` shim and was deliberately not ported —
   `docs/design/pgp-and-persona.md:51-52`).

Neither is a willow-mcp *blocker* for a **library-clean** promotion:
homestead-health calls no willow tools, holds no fleet-store reach, and keeps its
own #280-anchored ledger — so willow-mcp's runtime wall (scope confinement,
self-grant denial, FRANK gating) has nothing to enforce against it and nothing to
withhold. The gaps are all **operator-side, deployment-time** artifacts, not
changes the promoted repo must carry.

---

*Sources are `rudi193-cmd/willow-mcp` @ `832b3c9`, paths relative to that repo
unless prefixed `apps/homestead-health/…` or `stores/…` (this repo).*
