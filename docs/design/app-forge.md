# App Forge — Design Decision Log

> Status: **design / talk-through** (no implementation yet).
> A living record of decisions for a SAFE-native, multi-tenant app-building
> playground — the "10,000 other app-building sites" pitch, wearing the store's
> consent/gate/promotion mentality instead of instant deploy. Append as
> decisions land.

## Purpose

Let anyone describe an app and have it scaffolded, built, and iterated on
inside `apps/<tenant>/<name>/` — model-driven (local default, cloud fallback),
sandboxed per build, gated by a trust boundary the store owns outright. Not a
new product bolted alongside the store: a new flagship-shaped app *inside* it,
using the playground → promotion pipeline that already exists.

Multi-tenant from day one — real, unknown users building real apps on shared
infrastructure. That premise is what makes every decision below load-bearing
rather than aspirational.

## Where this sits relative to what already exists

An earlier audit (2026-07-31) of `safe-app-store`, `willow-mcp`, and
`kartikeya` found:

- **`kartikeya` (Kart) — real, tested, working.** `sandbox.py`'s `run_shell()`
  is a genuine bubblewrap wrapper: network unshared by default, PID/IPC/UTS
  namespaces, curated bind mounts, cgroup/`prlimit` resource caps. 112/112
  tests pass. Only self-acknowledged gap: seccomp filtering deferred.
- **`sap-gate`** (the signed-manifest gate CLAUDE.md describes) **does not
  exist anywhere** — not in this repo, not in `willow-mcp` (whose own bug
  ledger confirms it was removed and never rebuilt). `willow-mcp`'s `gate.py`
  is a real, tested, but non-cryptographic manifest-ACL check — file presence,
  not a signature.
- **Everything in `willow-mcp`/`kartikeya` is explicitly single-operator** —
  one `WILLOW_HOME` per host, single-user OAuth PKCE, no per-tenant namespace
  anywhere.
- **The installer design already solved the shape of this problem once**
  (`docs/design/safe-app-installer.md`, D3–D5): dangerous work happens inside
  Kart's sandbox; only a verified, declarative plan crosses a **seam** to a
  more-privileged host-side process, gated by consent + ledger. App Forge
  reuses that seam, applied to build-time and MCP-call-time instead of
  install-time.
- **Nestor** (`rudi193-cmd/Nestor`) is the closest existing prior art for the
  gate itself: `nestor/signing.py` + `nestor/keyring.py` implement exactly
  "signed → allowed, tampered → denied," with per-verifier keys and a
  rotated-vs-compromised revocation split. And `nestor/serve.py` is a working
  example of D1 below — its MCP surface can `nestor_ask` and `nestor_propose`,
  and structurally **cannot** `nestor_seal`. That tool doesn't exist on the
  model-facing surface; sealing only happens host-side.

## Decisions

### D1 — The trust boundary is the store, not any MCP server

`safe-app-store` decides what a build is allowed to touch. Full stop. Any MCP
server the builder connects to — `willow-mcp`, `Nestor`, GitHub, whatever gets
registered next — is a **capability provider**, never an authority. Every one
of them is exposed to the builder/agent through the same restricted contract
(D5): read and propose, never seal, grant, or promote. A compromised or just
badly-written MCP server can say anything it wants over that connection; it
cannot widen its own reach, because the tools that would let it don't exist on
that surface. This is `nestor/serve.py`'s pattern, generalized to every MCP
the store talks to, not just Nestor's own.

### D2 — Kart is a dependency, not part of the trust boundary

Kart answers "did this code run isolated" (no network, capped memory/PIDs,
namespaced) — an already-proven, already-tested fact. It does not and should
not answer "is this tenant/build allowed to exist or be promoted." Keep
`kartikeya` as an external pip dependency invoked per build; never ask it to
make an authorization decision. This is the same reasoning D1 applies to MCP
servers, applied to the one piece of outside software we *do* keep trusting —
Kart is trusted for isolation, not for policy.

### D3 — Reuse the installer's seam, for build-time calls not just install-time placement

Per `safe-app-installer.md` D3: all dangerous work happens inside the sandbox;
only a verified, declarative plan crosses to the trusted side. Applied here:

```
┌─ SANDBOX (kart, per-build) ───────────┐        ┌─ SEAM (store-side) ────────┐
│ run the model, generate/edit code     │        │ validate plan vs gate (D4) │
│ execute/test the generated app        │ ─plan─► │  + this tenant's scope    │
│ stage MCP tool calls as a request     │        │ apply: write to apps/<t>/, │
│   ("write to collection X", "read Y") │        │  or deny + report why      │
└────────────────────────────────────────┘        └─────────────────────────────┘
```

A build never writes to `apps/<tenant>/<name>/` directly, never calls a
plugged-in MCP tool directly, and never touches another tenant's directory or
collection. It emits a plan; the seam — running outside the sandbox, store-side
— checks the plan against the gate and against `store_scope`, and only then
acts. Same seam-holder role the installer design already assigns to the
more-privileged process; same reason (no vendor/generated code runs at host
privilege, ever).

### D4 — Rebuild `sap-gate` inside `safe-app-store`, modeled on Nestor's signing stack

Not in `willow-mcp` — CLAUDE.md's claim that it lives there is exactly the gap
the audit found. New module, `stores/sap_gate.py` (name tbd), shaped directly
on `nestor.signing` / `nestor.keyring`:

- Per-tenant/maker keyring identity (`nestor keys add <name>` shape).
- A build's manifest is signed, bound to `(app_id, permissions, store_scope,
  maker)` — same binding shape as a Nestor seal over `(source, target,
  verifier)`.
- Fail-closed `verify()`, run **before** a Kart task executes (D2/D3's seam
  check) and again before `stores/promote_check.py` runs. Unsigned or
  hash-mismatched (tampered post-generation) → denied, no exceptions.
- Nestor's revocation duality, reused as-is: a maker leaving (`rotate`) keeps
  their already-signed builds valid; a compromised key invalidates everything
  signed with it, and those builds surface for re-verification the way
  `Curator.unverifiable()` surfaces a forged seal.

This is the first time "signed → allowed, tampered → denied" is actually true
of this repo, rather than asserted by it.

### D5 — One capability contract, for every MCP server registered

A thin connector (`app_forge/mcp_connector.py`, name tbd) generalizes
`store_mcp.py`'s existing stdio-launch pattern beyond "willow" specifically:

- Register any MCP server by name + launch command.
- The builder/agent only ever sees that server's **read** and **propose**-
  shaped tools. Anything shaped like a write, grant, seal, or promote gets
  intercepted at the connector and routed through the seam (D3) + gate (D4)
  instead of executing directly — regardless of what the server itself
  advertises. A server that ships a `frank_append`-style write tool doesn't
  get to call it straight through; the plan it represents still crosses the
  seam.
- This is the same enforcement point for `willow-mcp`, `Nestor`, or anything
  registered next — the store doesn't special-case any one server's trust
  level, because none of them have one to begin with (D1).

### D6 — Tenancy lives in the store, because nothing else has it

`willow-mcp` and `kartikeya` are explicitly single-operator (confirmed by
audit, not assumed). Rather than retrofitting multi-tenancy into either,
`safe-app-store` owns tenant identity and scoping itself:

- `apps/<tenant_id>/<app_name>/` as the Kart working directory boundary —
  the bind mount for a build's sandbox is restricted to exactly that path.
- A per-tenant collection namespace (`saps1/tenant-<id>/...`), enforced by the
  gate (D4) at the seam, independent of which MCP server a build happens to
  be talking to.
- Per-tenant quotas layered on top of Kart's existing per-*task* caps (2G mem,
  512 PIDs already enforced) — concurrent builds, sandbox-seconds budget —
  so the isolation Kart already gives one task extends to fairness across many
  tenants sharing the host.
- Real multi-user auth is a prerequisite here, not a follow-on: `willow-mcp`'s
  current OAuth is explicitly single-user PKCE and doesn't carry a tenant
  claim. This needs its own decision before D6 is buildable — see Open/next.

### D7 — Model routing is a declared action, not ambient network access

Local model tried first (Ratatosk / local LLM); cloud fallback is a per-build
decision that shows up in the manifest like any other permission, and only
*then* gets a network-enabled Kart invocation (the sandbox's existing
`allow_net` task directive — off by default, per D2's `--unshare-net`
default). No silent egress; a build that never declares cloud fallback never
gets network, sandboxed or not.

## Reused patterns (not reinvented)

- **The seam** (`safe-app-installer.md` D3–D5) — sandbox does the dangerous
  work, a verified plan crosses to a privileged host-side process.
- **Verify-don't-assert** — same principle the installer doc names explicitly;
  a manifest claiming `sealed`/`signed` is exactly the claim a signature
  exists to distrust (Nestor's own framing, `README.md` "Export and import").
- **Fail-closed gate composition** — `stores/promote_check.py`'s "any gate
  fails, promotion fails" shape, extended one layer earlier (pre-execution,
  not just pre-promotion).
- **Nestor's signing/keyring/revocation** — the concrete shape for D4, not a
  fresh design.
- **`store_mcp.py`'s stdio launch** — the base the generic connector (D5)
  generalizes from.

## Open / next

- **Multi-user auth is the actual prerequisite for D6**, and isn't sketched
  yet. Does the store issue its own session tokens with a tenant claim, or
  extend `willow-mcp`'s OAuth provider to carry one? Given D1 (store owns
  trust), leans toward store-native — but worth a decision of its own before
  any of D6 is buildable.
- **The KB (docs from major software companies) lives locally, not in a
  repo** — no integration shape sketched yet. Whatever plugs it in should go
  through D5's same connector contract once it's reachable at all (local
  filesystem source today, not an MCP server — may need a small local adapter
  that *speaks* the same read/propose contract rather than being a special
  case).
- **Exact plan format for the seam** (D3) — what a "declarative plan" for an
  MCP tool call or a file write actually serializes as. `seam_install.py`'s
  placement-plan shape (`safe-app-installer.md` D3) is the starting reference,
  not yet adapted.
- **Whether Nestor becomes an actual pip dependency** for `sap_gate.py`, or
  just the design reference its signing/keyring modules get reimplemented
  from — Nestor's domain (translation-memory verification) is far from
  manifest-signing; its primitives are generic, but pulling the whole package
  in for two modules' worth of pattern is a separate call.
- **terpsi-music** was brought in as a worked example, not a dependency — its
  three-zone privacy design (`docs/ARCHITECTURE.md` §1: on-prem hub / untrusted
  relay / edge replicas) may be worth a closer read once D6's tenant-isolation
  shape firms up, since it's the same "how little can the shared surface be
  trusted" question this doc keeps landing on.
