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

## Reused patterns (already in the corpus)
- **Verify-don't-assert** — sovereignty and outward-compat are both verified/earned, never self-declared.
- **Path-containment allowlist** at the seam — same check as the utety-chat C6 path-traversal fix and the gate's `store_scope`.
- **Consent + PGP ledger** — install is a privileged, host-mutating, hard-to-reverse act; it is consented and ledgered like every other privileged lane.

## Open / next
- **Vault ↔ box provisioning** — how a fresh willow box is stood up from the
  `willow-data-vault` blueprint, and where the running vault lives on disk
  relative to `SAFE/`.
- How **apps in `SAFE/apps/`** are granted scoped access to vault collections
  (per-app `store_scope`, so an installed app reaches only its own data).
- Per-app **install recipe** format (the "how": AppImage/Flatpak/binary) —
  `apps.yaml` currently carries homepages, not install methods.
- Destination allowlist specifics and uninstall/archive semantics.
