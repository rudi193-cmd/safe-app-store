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

### D8 — Decisions are Socratic checkpoints, not silent choices

Every time the model is about to make a design/implementation decision on the
builder's behalf — a schema shape, a library choice, an auth flow, an
error-handling strategy, an algorithm — it stops and poses the decision as a
question with real options and their tradeoffs, before writing anything. The
builder answers; the code that gets written matches their answer, not the
model's default. This is deliberately slower than "write it and explain
after" — the point is that the builder is making the call, not rubber-stamping
one made for them.

Scope note, so this doesn't collapse into asking about every variable name: a
"decision" here is anything with a real design consequence — the kind of
choice a domain expert would have an opinion about, not syntax. Where exactly
that line sits is unresolved (see Open/next) but the interaction *mode* isn't:
once something is identified as a decision, it's always asked first, not
explained after.

### D9 — Checkpoints wire into the ecosystem's existing verification-as-learning loop

`VISION.md`'s Pattern 2 already runs through six apps: every human verification
event (approve a translation, confirm a citation, rate a flashcard) both
improves the corpus and fires an SRS review for the verifier. App Forge adds a
seventh row rather than inventing a parallel mechanism:

| App | Verification event | What gets learned |
|-----|--------------------|--------------------|
| App Forge | Confirm a design/implementation decision (D8) | This builder's grasp of the pattern; a personal decision ledger; calibration weight for future checkpoints |

Concretely, this is Nestor's mechanic (not just its signing/keyring modules —
its actual cascade), applied to a new recipe:

- **Matcher**: `normalize(decision)` → a canonical decision-type key (e.g.
  `"auth-flow-for-user-facing-form"`, `"schema-normalization-tradeoff"`).
  Wording varies more than intent here, so this likely wants
  `SemanticMatcher`, not `StringMatcher`.
- **Seal**: once a builder has answered a checkpoint and demonstrated they
  understood the tradeoff (not just picked an option — explained why, or
  answered a follow-up), that decision-type is sealed **for that builder**.
- **Serve**: the next time a similar decision recurs *for that same builder*,
  Nestor's tier-1 hit fires — the checkpoint gets lighter (a confirm-only:
  "you've handled this before, going with X, say so if not") instead of a
  fresh full Socratic pass. A builder who hasn't sealed that decision-type yet
  still gets the full question. This is the SRS-spacing effect, for free, from
  a mechanism this ecosystem already trusts.
- **Domain scoping matters**: the seal domain must be `(builder_id,
  decision_type)`, never just `decision_type` globally. A global seal would
  mean one builder's learning silently skips teaching for everyone else — the
  opposite of the point. Each builder's calibration is their own.
- **Resurfacing**: when a past decision's consequence becomes visible later
  (a bug traced to a schema choice, a security review flags a skipped
  validation), that's a natural point to resurface the original checkpoint —
  "remember choosing X here? here's what that cost" — same shape as
  `Curator.unverifiable()` surfacing something that needs a second look.

### D10 — The pedagogy ledger and the trust gate (D4) are related but distinct

Two different ledgers, not one conflated system:

- **D4's gate** answers "is this manifest signed by who it claims, unaltered
  since." Authorization.
- **D9's checkpoint ledger** answers "did this builder actually engage with
  the decisions in their own build." Pedagogy / attribution quality.

They meet at one point worth naming: D4's manifest signature binds
`(app_id, permissions, store_scope, maker)` — a maker signs off on what their
build does. D9's ledger is what makes that attestation *mean* something
rather than being a nominal click-through: a maker who sealed the checkpoints
behind their own manifest actually reasoned through what they're vouching for.
Not a hard dependency between the two systems, but the gate is more honest
when it exists.

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

## Candidate building blocks (open internet sweep, 2026-07-31)

A broad sweep for real, currently-maintained, license-compatible prior art per
decision — this repo is Apache-2.0, so results are filtered to
Apache-2.0/MIT/BSD. Two real candidates were found and **excluded** on license
grounds: Daytona (moved off Apache-2.0 to AGPL-3.0) and Firejail (GPL-2.0).
Excluding them here rather than silently skipping them, since both are
otherwise-reasonable fits for D2.

**D2 — sandboxing, especially Kart's acknowledged seccomp gap**
- **nsjail** (Apache-2.0, Google) — namespaces + cgroups + rlimits + real
  seccomp-bpf filtering. The direct fix for the specific gap Kart names in its
  own code: could sit alongside Kart's bwrap invocation rather than replacing
  it.
- **gVisor** (Apache-2.0, Google) and **Kata Containers** / **Firecracker**
  (both Apache-2.0) — stronger isolation than namespaces (userspace kernel,
  or microVM per build). Candidates for a higher-trust-boundary tier under
  D6's tenancy model, not a wholesale Kart replacement.
- **Wasmtime** (Apache-2.0 + LLVM exception) — a different axis: capability-
  based sandboxing if generated code can run as Wasm, layerable on top of
  Kart rather than instead of it.
- **E2B** (Apache-2.0, self-hostable) — a complete open-source multi-tenant
  AI-sandbox platform. Worth evaluating end-to-end as an alternative to
  assembling primitives, with the caveat that self-hosting has real
  infrastructure cost (Terraform/Nomad/Consul, reported ~$1,250/mo GCP floor).

**D4 — the manifest-signing gate**
- **Sigstore (cosign)** (Apache-2.0) — closest drop-in replacement for the
  hand-rolled HMAC approach borrowed from Nestor. `sign-blob`/`verify-blob`
  works directly on a small JSON manifest; keyless identity mode maps onto
  per-maker identity; already distinguishes rotation from compromise, the
  exact duality D4 wants. Static-keypair mode avoids the OIDC/Fulcio/Rekor
  infrastructure dependency if that's unwanted.
- **TUF** (MIT/Apache-2.0 dual) — the most rigorous existing model of
  rotate-vs-compromise specifically (root-key-signed role rotation, threshold
  signing), but shaped for a repository-of-updates, not one manifest. Worth
  reading for the rotation model even if not adopted whole.
- **in-toto** (Apache-2.0) and **Notary/notation** (Apache-2.0) — real, but
  poorer fits: in-toto's multi-step chain verification is more machinery than
  one manifest needs; Notary is OCI-registry-shaped specifically.

**D1 / D5 — centralized policy decision, independent of the calling MCP server**
- **Casbin / pycasbin** (Apache-2.0) — the only candidate with true in-process
  Python embedding (`pip install casbin`, no sidecar). Least infra, less
  expressive for complex context-dependent policy than the two below.
- **OPA/Rego** (Apache-2.0) — closest conceptual match (arbitrary JSON input,
  so a tool call maps in as `{server, tool, args, caller}`), but Python means
  a sidecar/REST call to the `opa` binary or WASM bindings — no native
  in-process embedding.
- **Cedar** (Apache-2.0, AWS) — cleanest semantic fit
  (`principal/action/resource/context` ≈ `caller/tool/target/args`), formally
  verified core, but Python bindings (`cedarpy`) are community-maintained,
  not AWS-official.
- **OpenFGA** and **Topaz** (both Apache-2.0) — real, but lean toward
  relationship-graph or full-PDP-service shapes further from D5's "one
  lightweight in-repo gate" framing.

**D5 — MCP gateway/connector prior art**
No project already does D5's exact shape-based interception (classify by
read/propose vs. write/grant, not by trusting what the server itself claims)
— every real option leans on OAuth scopes or static allow/deny instead.
Closest adoption candidates: **mcp-gateway-registry**
(`agentic-community`, Apache-2.0) already has per-tool scoping and a
fail-closed admission gate for newly registered servers — adaptable, not a
rewrite. **mcp-filter** (MIT) has a usable tool-list-filtering technique as a
building block, though its own author calls it "a schema reducer, not a
security boundary." **Pomerium** and **IBM/mcp-context-forge** (both
Apache-2.0) are real but general-purpose/federation-shaped, heavier than D5
needs.

**D7 — local-default, gated cloud-fallback model routing**
- **Ollama** (MIT) or **vLLM** (Apache-2.0) as the local engine.
- **LiteLLM** (MIT core — the `enterprise/` subdirectory carries a different
  license, avoid pulling that path in) as the routing layer: its `fallbacks`
  config is the closest real mechanism to "local first, cloud on signal," but
  the trigger is error/failure-based, not an explicit declared permission.
  The manifest-driven gating D7 actually wants still has to be this repo's
  own code, wrapping LiteLLM's routing rather than inherited from it.
- **RouteLLM** (Apache-2.0) auto-routes by predicted quality, not explicit
  signal — weaker fit than LiteLLM for D7's "declared, not ambient"
  requirement.

**D9 — the checkpoint-ledger's calibration mechanic**
- **py-fsrs** (MIT) — the actual algorithm Nestor's seal/serve mechanic was
  only loosely imitating. A real `Scheduler`/`Card` pair keyed on
  `(builder_id, decision_type)` gives a principled `difficulty`/`stability`
  calibration signal in place of a hand-rolled weight — this is the strongest
  single upgrade available to the current sketch.
- **sm-2** (MIT, same maintainer org as py-fsrs) — a lighter classic-SM-2
  fallback with the same `Scheduler`/`Card`/`ReviewLog` shape, if FSRS's
  parameter count is more than D9 needs.
- **py-irt** (MIT) — Bayesian Item Response Theory; would give a statistically
  grounded per-builder ability estimate instead of an ad-hoc weight, at the
  cost of a PyTorch dependency — weigh against D9's implicit
  dependency-light preference.
- **openskill.py** (MIT) — simplest option: one `(mu, sigma)` pair per
  `(builder_id, decision_type)`, updated per checkpoint outcome, no batch fit
  or memory model required.
- No reusable **iNaturalist-style** calibration package exists — its
  confidence mechanism is bespoke, unpublished as a library. Design
  inspiration only, not a candidate dependency, as already noted in
  `VISION.md`.

## Open / next

- **Where exactly "a decision" starts** (D8) — the line between "ask first"
  and "just write it" is asserted, not drawn. Needs a working pass over real
  build sessions to find where it actually falls before this is more than a
  guess.
- **Checkpoint fatigue has no escape hatch yet.** D8 is deliberately pure
  Socratic per the call that shaped it, but a genuine beginner facing their
  first unsealed checkpoint on every decision-type in a session could stall
  out before anything ships. Worth deciding whether "I don't know, you
  choose" is a legitimate answer that still seals *as a taught decision*
  (builder saw the tradeoff, deferred deliberately) versus something that
  should block progress.
- **Whether Nestor becomes an actual dependency, not just D4's pattern
  reference** — D9's checkpoint ledger is much closer to Nestor's actual
  domain (matching a query against a memory of confirmed answers) than D4's
  gate is. Stronger case here for `pip install nestor` and a real
  `EntityResolver`-shaped recipe than for D4's borrow-the-shape approach.
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
