# The Forge — Design Decision Log

> Status: **design / talk-through** (no implementation yet).
> A living record of decisions for a SAFE-native, multi-tenant app-building
> playground — the "10,000 other app-building sites" pitch, wearing the store's
> consent/gate/promotion mentality instead of instant deploy. Named **The
> Forge**: built inside `safe-app-store` first, designed from day one to clear
> the same promotion bar Nestor and Jeles already did (D13) and leave as its
> own repo under that name. Append as decisions land.

## Purpose

Let anyone describe an app and have it scaffolded, built, and iterated on
inside `apps/<builder_id>/<name>/` — model-driven (local default, cloud fallback),
sandboxed per build, gated by a trust boundary the store owns outright. Not a
new product bolted alongside the store: a new flagship-shaped app *inside* it
at first, using the playground → promotion pipeline that already exists — and,
per D13, built to actually leave through that pipeline as its own repo,
**The Forge**, rather than staying embedded indefinitely.

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
  more-privileged host-side process, gated by consent + ledger. The Forge
  reuses that seam, applied to build-time and MCP-call-time instead of
  install-time.
- **Nestor** (`rudi193-cmd/Nestor`) was the original prior art for the gate's
  *shape* — `nestor/signing.py` + `nestor/keyring.py` show "signed → allowed,
  tampered → denied" with per-verifier keys and rotated-vs-compromised
  revocation. **D4 ended up adopting Sigstore instead of this crypto** (see
  D4) — Nestor's lasting role in this design is D12's memory/pedagogy store
  and D5's MCP-allowlist reference (below), not the manifest-signing gate.
  And `nestor/serve.py` is a working example of D1 below — its MCP surface
  can `nestor_ask` and `nestor_propose`, and structurally **cannot**
  `nestor_seal`. That tool doesn't exist on the model-facing surface; sealing
  only happens host-side.

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
│ execute/test the generated app        │ ─plan─► │  + this builder's scope   │
│ stage MCP tool calls as a request     │        │ apply: write to apps/<b>/, │
│   ("write to collection X", "read Y") │        │  or deny + report why      │
└────────────────────────────────────────┘        └─────────────────────────────┘
```

A build never writes to `apps/<builder_id>/<name>/` directly, never calls a
plugged-in MCP tool directly, and never touches another builder's directory
or collection. It emits a plan; the seam — running outside the sandbox, store-side
— checks the plan against the gate and against `store_scope`, and only then
acts. Same seam-holder role the installer design already assigns to the
more-privileged process; same reason (no vendor/generated code runs at host
privilege, ever).

**The seam validates *where*, not *what* — fixed 2026-07-31, corrected
2026-08-01.** The plan schema above checks destination paths against
`store_scope`; it says nothing about what's actually inside a generated
file, and that file will later execute (inside Kart, at minimum — D2). The
first fix pass made two claims about this repo; a second independent review
checked both against the actual code and found one of them **false**:

- **The pre-crossing static-scan citation was wrong.** `tools/vault_leak_lint.py`
  is **not** AST-based — it's line-by-line regex (`safe-app-installer.md`
  says so directly: "the linter is line-based"). The real AST work in this
  repo is `stores/promote_check.py`'s `_toplevel_dynamic_net` /
  `_toplevel_imports`, and it's deliberately **top-level-only** — it skips
  function bodies by design, because it's answering an import-time question.
  That means even the real precedent wouldn't catch `def f(): os.system(...)`,
  exactly the runtime-behavior class a pre-crossing scan for generated code
  needs to catch. A scan for D3 has to be built to cover function bodies, not
  adapted from either existing file as-is — both are narrower than this
  needs, in different ways. Still a floor, not a proof, once built: it
  catches the obvious/accidental case, not a determined adversary; Kart's
  sandbox (D2) is what actually contains execution, not this scan.
- **"Generated code is never executed host-side" was asserted and is
  currently false in this repo.** `stores/promote_check.py` runs
  `subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=cand)` — the
  candidate's actual test suite, host uid, unsandboxed, no Kart involved.
  Worse: the files that get AST-scanned and the files that get executed are
  **disjoint sets** — `_py_files()` filters out anything with `test` in the
  filename before scanning, which is precisely what pytest then runs. This
  isn't a Forge-specific hypothetical — it's a real gap in this repo's
  *existing* promotion pipeline today, for every app that goes through it,
  independent of whether The Forge ever ships. Filed separately in
  Open/next, since fixing it is bigger than this design doc's scope.
- **What D3 actually requires going forward**: `promote_check.py`'s test
  execution step has to move inside Kart (or an equivalent sandbox) before
  "generated code is never executed host-side" is *true* of this repo,
  rather than merely stated as a rule for The Forge's own new code to
  follow while an existing path violates it.

### D4 — Rebuild `sap-gate` inside `safe-app-store`

Not in `willow-mcp` — CLAUDE.md's claim that it lives there is exactly the gap
the audit found. New module, `stores/sap_gate.py` (name tbd):

- Per-builder keyring identity: one Ed25519 keypair per `builder_id` (D11),
  generated and held by the store's own signing service, via **Sigstore**
  static-keypair mode (see Adopted dependencies) — not Nestor's HMAC
  pattern. Nestor's shape was the original inspiration ("Where this sits,"
  above), but D4 adopted an audited standard instead of hand-rolling one.
- A build's manifest is signed, bound to `(app_id, permissions, store_scope,
  maker)`.
- Fail-closed `verify()`, run **before** a Kart task executes (D2/D3's seam
  check) and again before `stores/promote_check.py` runs. Unsigned or
  hash-mismatched (tampered post-generation) → denied, no exceptions.

This is the first time "signed → allowed, tampered → denied" is actually true
of this repo, rather than asserted by it — with one honest caveat the next
section exists specifically to name.

**Key custody and the rotate/compromise gap — fixed 2026-07-31, tightened
2026-08-01.** Static-keypair Sigstore doesn't by itself give the
rotate-vs-compromise duality this decision wants — that lives in Fulcio/Rekor,
which static mode deliberately avoids.

- **Custody is store-held, named honestly rather than implied to be
  stronger.** The signature's job is tamper-evidence and a stable audit
  binding, not non-repudiation against the store itself — consistent with D1
  (the store *is* the trust boundary by design), but the original "signed →
  allowed" framing implied builder-authored attestation it doesn't actually
  deliver. Key material lives in the vault this ecosystem already built for
  exactly this problem — `safe-app-installer.md` D7's Fernet-keyed secrets
  vault (`vault.py`, `vault.key` at 0600, never touches git) — not a fresh
  secrets-management design.
- **Rotate vs. compromise needs a ledger the store itself can't quietly
  rewrite — an ordinary in-repo ledger isn't enough on its own.** A
  signing-event ledger — `(builder_id, key_id, manifest_hash, timestamp)`,
  append-only, hash-chained, modeled on Nestor's `ledger.py` but its **own
  instance** (not D12's pedagogy ledger — see D10) — gives rotate and
  compromise real timing to check against. But the store holds the signing
  keys *and* would write that ledger, so a store/vault compromise
  invalidates both at once; "compromise" only means something distinct from
  "everything's already broken" if the ledger's tip is pinned somewhere the
  store's own compromise can't reach. Nestor already ships the primitive for
  this — `nestor ledger head` / `ledger verify --expect-head=…`, an
  **operator-held tip** outside the store's own trust domain (see "Ops
  hooks," below). D4 adopts the same posture: the signing-event ledger's
  head gets pinned externally — operator-held, or mirrored the way
  `nestor.frank` mirrors into willow-mcp FRANK — not just verified against
  itself. `rotate` retires a key going forward while every past ledger entry
  for it stays trusted; `compromise` records a timestamp, and any entry for
  that key after it, per the externally-pinned tip, stops being trusted.

### D5 — One capability contract, for every MCP server registered, enforced by an explicit allowlist

A thin connector (`the_forge/mcp_connector.py`, name tbd) generalizes
`store_mcp.py`'s existing stdio-launch pattern beyond "willow" specifically:

- Register any MCP server by name + launch command.
- **Default-deny, not shape-classification.** The connector holds an
  explicit, per-server tool allowlist — reviewed once when a server is
  registered, never inferred at call time from what a tool's name or schema
  suggests. A tool not on the allowlist is refused by name, full stop. This
  replaces the earlier "anything shaped like read/propose passes through"
  framing, which the 2026-07-31 review correctly flagged as fail-open:
  classifying by a server's own claimed shape trusts exactly the thing D1
  says can't be trusted.
- **`nestor.serve.Server` is the reference implementation, not an
  inspiration** — see "Nestor inventory" below for its actual tool list and
  `WITHHELD` set. It already does default-deny-by-name, not shape-inference.
  Every other registered server needs the same explicit-list treatment
  authored for it; none of them get to self-classify.
- Anything not on a server's allowlist — including a write/grant/promote
  call from a server that *is* registered — still routes through the seam
  (D3) + gate (D4) rather than executing directly.
- Same enforcement point for `willow-mcp`, `Nestor`, or anything registered
  next — the store doesn't special-case any one server's trust level,
  because none of them have one to begin with (D1).

### D6 — Tenancy lives in the store, because nothing else has it

`willow-mcp` and `kartikeya` are explicitly single-operator (confirmed by
audit, not assumed). Rather than retrofitting multi-tenancy into either,
`safe-app-store` owns tenant identity and scoping itself:

- `apps/<builder_id>/<app_name>/` as the Kart working directory boundary —
  the bind mount for a build's sandbox is restricted to exactly that path.
- A per-builder collection namespace (`saps1/builder-<builder_id>/...`),
  enforced by the gate (D4) at the seam, independent of which MCP server a
  build happens to be talking to.
- Per-builder quotas layered on top of Kart's existing per-*task* caps (2G
  mem, 512 PIDs already enforced) — concurrent builds, sandbox-seconds
  budget — so the isolation Kart already gives one task extends to fairness
  across many builders sharing the host.
- Real multi-user auth is a prerequisite here, not a follow-on — resolved by
  D11's store-native session layer (`builder_id` is D11's canonical
  identity; see there for the fix and why GitHub isn't the identity root).

**Naming note, fixed 2026-08-01:** this decision originally used `tenant_id`;
D11 later made `builder_id` canonical across the whole doc but this section's
body was never actually edited to match — same identity throughout, one name
for it now.

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
improves the corpus and fires an SRS review for the verifier. The Forge adds a
seventh row rather than inventing a parallel mechanism:

| App | Verification event | What gets learned |
|-----|--------------------|--------------------|
| The Forge | Confirm a design/implementation decision (D8) | This builder's grasp of the pattern; a personal decision ledger; calibration weight for future checkpoints |

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

### D10 — Three audit trails, not one conflated system

The count crept from two to three across fixes without ever being written
out together, and both the 2026-07-31 and 2026-08-01 reviews flagged the
drift — the "seam ledger" the Nestor-inventory table references was never
actually defined anywhere in this doc until D3's correction, above. Stated
plainly now:

| Ledger | Lives in | Answers | Written by |
|--------|----------|---------|------------|
| **Seam ledger** (D3) | store-side, per seam decision | What plan did a build submit, and did the seam apply or deny it, and why? | The seam itself, on every plan it processes |
| **Signing-event ledger** (D4) | store-side, own instance, externally-pinned tip | When was this manifest actually signed, under which key — before or after that key's compromise timestamp? | `stores/sap_gate.py`, on every signature |
| **Pedagogy ledger** (D9/D12) | Nestor, per-builder domain | Did this builder actually engage with and understand this decision? | Nestor's `memory`/`cascade`, on every checkpoint seal/reject |

None of these substitutes for another:

- **D4's gate** answers "is this manifest signed by who it claims, unaltered
  since." Authorization.
- **D9's checkpoint ledger** answers "did this builder actually engage with
  the decisions in their own build." Pedagogy / attribution quality.
- **D3's seam ledger** answers "what did the trust boundary actually let
  through, and on what basis." Operational audit of D1's front line, day to
  day — not the same question as either of the other two.

D4 and D9 meet at one point worth naming: D4's manifest signature binds
`(app_id, permissions, store_scope, maker)` — a maker signs off on what their
build does. D9's ledger is what makes that attestation *mean* something
rather than being a nominal click-through: a maker who sealed the checkpoints
behind their own manifest actually reasoned through what they're vouching for.
Not a hard dependency between the systems, but the gate is more honest when
it exists.

## Reused patterns (not reinvented)

- **The seam** (`safe-app-installer.md` D3–D5) — sandbox does the dangerous
  work, a verified plan crosses to a privileged host-side process.
- **Verify-don't-assert** — same principle the installer doc names explicitly;
  a manifest claiming `sealed`/`signed` is exactly the claim a signature
  exists to distrust (Nestor's own framing, `README.md` "Export and import").
- **Fail-closed gate composition** — `stores/promote_check.py`'s "any gate
  fails, promotion fails" shape, extended one layer earlier (pre-execution,
  not just pre-promotion).
- **Nestor's ledger pattern** (`ledger.py`'s tamper-evident, fail-closed
  hash-chain) — reused twice, not once: D12's pedagogy memory (Nestor
  itself, adopted as a dependency) and D4's signing-event ledger (the
  *pattern* only, a separate instance — D4's actual crypto is Sigstore, not
  Nestor's).
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
Original framing here judged candidates against D5's *first* draft —
classifying tool calls by shape (read/propose vs. write/grant). D5 no
longer works that way (see D5, fixed 2026-07-31: default-deny via an
explicit per-server allowlist). Re-read against the corrected target:
**mcp-gateway-registry** (`agentic-community`, Apache-2.0) is a closer match
than this section originally credited it — its per-tool scoping and
fail-closed admission gate for newly registered servers is close to
allowlist-per-server, not just "adjacent." Still not adopted as a dependency
(see Adopted dependencies), but that call now rests on its own merits rather
than a comparison to a version of D5 that no longer exists. **mcp-filter**
(MIT) still has a usable tool-list-filtering technique as a building block,
though its own author calls it "a schema reducer, not a security boundary."
**Pomerium** and **IBM/mcp-context-forge** (both Apache-2.0) remain real but
general-purpose/federation-shaped, heavier than D5 needs.

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

## Adopted dependencies (2026-07-31)

Decisions made against the sweep above — recorded as decisions, not just
survey notes, since each one commits this design to a real external
dependency.

- **D2 → Kart + nsjail, nothing further for now.** nsjail (Apache-2.0)
  closes Kart's acknowledged seccomp gap directly. gVisor / Kata Containers /
  Firecracker / E2B stay noted as a future higher-trust tier (D6) —
  deliberately not adopted yet, since The Forge has no real multi-tenant
  traffic yet to justify the added infrastructure (E2B's self-hosted floor
  alone is real money: ~$1,250/mo).
- **D4 → Sigstore, static-keypair mode, plus a signing-event ledger.** Real
  audited signing (`sign-blob`/`verify-blob`), no new infrastructure
  dependency — explicitly *not* keyless mode, which would pull in
  Fulcio/Rekor. **Static mode alone does not give rotate-vs-compromise
  semantics** — that correction landed after this bullet was first written;
  see D4's "Key custody" section for the actual mechanism (a dedicated,
  externally-pinned signing-event ledger). Replaces the hand-rolled HMAC
  pattern borrowed from Nestor; `stores/sap_gate.py` becomes a thin wrapper
  over cosign's static-key flow rather than a fresh crypto implementation.
- **D1/D5 → Casbin, in-process.** Matches D1's "lightweight in-repo gate"
  framing exactly — no sidecar, no daemon. OPA and Cedar stay noted as an
  escalation path if the policy shape outgrows what Casbin's model/policy DSL
  can express; not a decision to revisit until that pressure actually shows
  up.
- **D5 (connector) → build the minimal version in-repo, no dependency
  adopted.** Re-affirmed after D5's fix (default-deny, explicit per-server
  allowlist, `nestor.serve.Server` as reference): `mcp-gateway-registry`'s
  admission-gate is closer to this than the original sweep credited it, but
  its authorization model is still OAuth-scope/role-based, not the
  explicit-allowlist-per-tool shape D5 actually needs — worth reading for
  structure, still not quite a fit to depend on.
- **D7 → vLLM** as the local engine, not Ollama — chosen specifically because
  D6 already commits to multi-tenant from day one, and vLLM is built for real
  concurrent throughput where Ollama is shaped around single-user local use.
  LiteLLM stays the routing/proxy layer on top (per the sweep), with the
  manifest-driven fallback gate remaining this repo's own code either way.
- **D9 → py-fsrs.** The real algorithm the Nestor-shaped sketch was
  approximating by hand; `sm-2`/`py-irt`/`openskill.py` stay unadopted (sm-2
  strictly weaker, py-irt's PyTorch dependency too heavy, openskill missing
  the interval-scheduling piece D9's "resurface later" actually depends on).

### D11 — Multi-user auth: store-native session layer, GitHub OAuth only, store-minted identity

Not an extension of `willow-mcp`'s OAuth — that provider is explicitly
single-user PKCE, and stretching it for multi-tenancy is real surgery on code
that wasn't built for this. Per D1 (the store owns trust, not any MCP
server), `safe-app-store` issues its own session tokens after a GitHub OAuth
handshake completes. No password storage, no reset flow to build.

GitHub specifically, not a generic OAuth menu: every sibling repo this design
already leans on — Kart, Nestor, willow-mcp — lives there, so a builder
plausibly already has an account, and it's where they'd be pulling this down
from anyway.

**`builder_id` is store-minted, not GitHub's account ID — fixed 2026-07-31.**
The original shape derived `builder_id` directly from GitHub's stable user
ID, which makes GitHub the root of the store's identity namespace — exactly
what D1 rules out. Corrected:

- At first successful GitHub OAuth login, the store mints a new internal
  `builder_id` (store-generated, not derived from anything GitHub returns)
  and records one row binding it to an **authenticator**:
  `{provider: "github", external_id: <github user id>, linked_at}`.
- Every downstream system keys off the store-minted `builder_id`, never off
  the GitHub ID directly — this part of the original design still holds:
  - D4's signing keyring (one Sigstore keypair per `builder_id`)
  - D6's collection/working-directory scoping (`apps/<builder_id>/<name>/`,
    `saps1/builder-<builder_id>/...`)
  - D9/D12's Nestor domain (`domain=f"builder:{builder_id}"`)
  - every Casbin (D1/D5) policy check's `caller` field
- GitHub becomes what D1 already says every external system should be — a
  **capability provider** ("this session belongs to GitHub account X"), not
  an authority over identity. A renamed, deleted, or reused GitHub account
  never moves the authorization graph; only the authenticator-binding row
  changes. A second authenticator (another provider, later) could bind to
  the same `builder_id` without touching anything D4/D6/D9/D12 already built.
- **Uniqueness is enforced at bind time, not assumed.** The authenticator
  table has a uniqueness constraint on `(provider, external_id)` — a GitHub
  account can bind to at most one `builder_id`, checked before the bind
  commits. Without this, the fix is cosmetic: anything that could claim an
  `external_id` during binding would still get to claim someone else's
  identity, just one indirection later.
- **`builder_id` is a filesystem path component (D6) and follows the
  charset rule this repo already enforces for the same problem** —
  `stores/promote_check.py`'s `_APP_ID_PATTERN`
  (`^[A-Za-z0-9][A-Za-z0-9_.-]*$`) applied to `builder_id` at mint time, not
  a fresh rule invented for D11.
- v1 scope: one authenticator per `builder_id`, minted once, no re-linking
  flow yet — a real gap (see Open/next), but it doesn't undermine the
  identity model itself.

**Rollout is a separate call from architecture.** D6 already committed to
supporting real strangers; whether self-serve signup is literally open on day
one is a later decision, not something this design needs to answer to keep
moving.

### D12 — D9's storage/ledger half: adopt Nestor as a real dependency

Unlike D4 (which borrowed Sigstore instead of Nestor's HMAC pattern), this one
adopts Nestor itself — `pip install nestor`, not a pattern reference. This is
Nestor's actual domain (matching a query against a memory of confirmed
answers), the core package has zero runtime dependencies, and — unlike the
arm's-length OSS elsewhere in this stack — it's a sibling repo CLAUDE.md
already treats as the worked standard for exactly this kind of promoted
dependency.

Concrete recipe: `EntityResolver(store, domain=f"builder:{builder_id}")`.
A decision description resolves against canonical decision-types this
specific builder has already sealed — a hit at/above threshold triggers D8's
lighter-touch confirm, a miss or near-miss triggers the full Socratic
checkpoint.

**Rejection is included, not just sealing.** `reject_pair` — "I was wrong
about this generally, unseal it everywhere" — and `reject_match` — "that
explanation didn't fit this specific case, the general understanding still
holds" — are both real things that happen while someone is actually learning,
and Nestor already distinguishes them correctly rather than this design
needing to work out that distinction itself.

**Division of labor, stated plainly:** Nestor answers "has this been sealed"
(memory). py-fsrs (D9's earlier adoption) answers "is it due for review"
(schedule). No overlap between the two dependencies.

**Storage isolation: one Nestor database per `builder_id`, not a shared DB
with domain scoping — decided 2026-08-01.** Nestor's domain-tag scoping
(`domain=f"builder:{builder_id}"`) would work inside one shared database, but
that makes cross-builder isolation depend on the seam never mis-scoping a
domain string — one bug away from leaking. A separate `SqliteStore` file per
`builder_id` (the same directory-per-builder boundary D6 already uses for
`apps/<builder_id>/`) makes that class of bug structurally unable to cross a
builder boundary — a mis-scoped domain string can still misfile within one
builder's own memory, but has no other builder's file to reach at all.

### D13 — Build for promotion from day one; the promoted repo is named **The Forge**

This won't stay embedded in `apps/`. It's designed to eventually clear the
same bar Nestor and Jeles already did (`CLAUDE.md` §8, the worked standard):
injected storage, a dependency-light/import-pure core, its own tests,
`stores/promote_check.py`'s gates passing, the host (`safe-app-store`)
repointed as a consumer rather than an owner. The promoted repo's name is
**The Forge** — Vishwakarma forges; this is where things get forged.

Practically, this is a day-one constraint, not a later refactor:
- The core never imports `safe-app-store` internals directly — everything it
  needs (the gate, the seam, the catalog, tenant/session state) comes in
  through an injected interface, the same shape as `nestor.storage.Storage`.
- `stores/promote_check.py`'s inversion check ("core doesn't import its
  host") has to pass from the first commit, not get retrofitted right before
  promotion.
- This is also a partial answer to the open scope concern raised in review: a
  core that has to stand alone, with its own tests, resists dependency creep
  more than code written to live permanently inside the monorepo. Each of
  D2/D4/D5/D7/D9/D12's adopted dependencies has to earn a place in something
  that will ship standalone, not just something convenient to reach for
  inside a shared repo.

## Nestor inventory — shipped primitives (code-backed, 2026-07-31)

Sibling repo audit from the Nestor side (`rudi193-cmd/Nestor`, `master` after
PR #26). This section **supplements D12** (adopt Nestor for D9 memory) and **D1/D5**
(MCP contract); it does **not** replace D4's Sigstore choice for manifest signing.

**Division of labor (restated with code names):**

| Concern | The Forge (this design) | Nestor (shipped) |
|---------|-------------------------|------------------|
| Artifact / build manifest signed? | D4 → Sigstore static-keypair (`stores/sap_gate.py`) | — |
| Tool call allowed by policy? | D1/D5 → Casbin + connector | — |
| Has this builder sealed this decision-type? | D12 → `EntityResolver` + domain | `memory` + `lookup` / `ask` |
| When to resurface a checkpoint? | D9 → py-fsrs schedule | — |
| Hash-chained audit of human actions? | Store seam ledger (D3) | `data/ledger.jsonl` + `_ledger_preflight()` |

### D1 / D5 — `nestor serve` is the reference MCP allowlist

`nestor.serve.Server` exposes a **closed tool list**; any other `nestor_*` name
is refused with a message pointing at `nestor_propose`. The withheld verbs are
data (`WITHHELD`: seal, unseal, reject, override, import, edit ledger).

| MCP tool | Use in The Forge connector |
|----------|----------------------------|
| `nestor_ask` | Three-state cascade (`sealed` / `draft` / `pending`) + ranked candidates — model must not paraphrase verified text |
| `nestor_resolve` | Entity recipe: alias → canonical when sealed |
| `nestor_check` | Numeric recipe: figure vs sealed baseline |
| `nestor_match` | Bare seam: `string` / `numeric` / `semantic` matcher |
| `nestor_provenance` | Verifier, timestamps, origin, rejections for a `pair_id` |
| `nestor_ledger_verify` | Hash-chain integrity + memory counts |
| `nestor_propose` | **Only write** on the model surface → always `draft` |

`nestor serve --read-only` drops even `nestor_propose`. Host-side sealing uses
**`nestor ui`** (HTTP API: seal, unseal, reject-pair, reject-match) — same
human/machine split as D3's seam, already two entrypoints (`serve` vs `ui`).

`Server.describe()` returns wiring text for MCP hosts; D5 can treat that as the
canonical read/propose surface rather than re-deriving tool shapes.

### D4 — Do not conflate manifest signing with Nestor's seal crypto

D4 adopted **Sigstore**, not Nestor HMAC, for build manifests. Nestor still
matters for **verification semantics** on the D12 store:

- **`_ledger_preflight()`** (`nestor.memory`) refuses seals when the ledger is
  missing or broken — the failure mode of a **db backup without its chain**
  (Nestor ships `nestor db checkpoint --out` with `<basename>.ledger.jsonl` for
  hot copies; `nestor export` for portable bundles).
- **`signing.py`**: three MAC domains (seal, rejection, embedding cache) so
  signatures cannot be replayed across object types; **`SemanticMatcher`** serve
  paths also sign cached row embeddings (store-writer cannot swap vectors under
  a sealed row).
- **`keyring`**: per-verifier keys; **rotate** vs **compromised** revocation;
  `Curator` / `servable` surfaces rows that must not be served.

Ed25519 upgrade for *seals* is still open in Nestor (willow-mcp
`egress_authorization.py` is the fleet reference); unrelated to D4 cosign.

### D12 / D9 — Recipe detail beyond `EntityResolver`

D12's `EntityResolver(store, domain=f"builder:{builder_id}")` is one recipe.
The same store can hold others without new infrastructure:

- **Checkpoint Q→A**: seal `decision_prompt` → `chosen_option + rationale` as
  source/target in a dedicated language-pair or use `domain` as decision-type key.
- **`reject_match`**: wrong application of a sealed pattern for *this* query;
  pair stays valid elsewhere (false-positive teaching).
- **`reject_pair`**: retire the mapping globally.
- **`nestor calibrate`**: measured false-verification rate on a corpus — honest
  "how hard is this decision class" before tuning thresholds.
- **`Curator.rejection_signals()`** / **`nestor rejections`**: aggregate refusals
  → threshold vs pair-quality hints (no new analytics layer).

**`memory.is_verified_seal` / `servable`**: tier-1 serve requires valid
signature under configured keys — maps to D8 "confirm only" when sealed hit is
**servable**, not merely `status=sealed`.

**Multi-tenant:** Nestor is **per database instance** — D12 resolves this as
separate db paths per `builder_id` (defense in depth over domain-tag scoping
within one shared file; see D12). No global seal across builders either way.

**Import caution:** `nestor import` **downgrades** seals whose signatures do
not verify under *this* instance's keys to `draft`. Not a trustless way to move
D12 memory between hosts without shared key material.

### Promotion ratification (store `master`, not Forge-only)

`stores/promote_check.py` on `safe-app-store` **master**:

- Mechanical + attested gates; **`verified_by != author`** enforced on `--record`.
- Nestor/Jeles are worked examples (`semantic_seam`: `nestor.matcher:Matcher`).
- **`--record`** writes `stores/{major}/promoted/<app_id>.json` — Nestor passed
  gates in #88 but **no record minted yet** (`docs/store_refit_plan.md`).

D13 promotion of **The Forge** should use the same gate; D10's pedagogy ledger
(D12) is orthogonal to `promotion.json` ratification.

### Ops hooks (tenant audit, optional)

- `nestor ledger head` / `ledger verify --expect-head=…` — operator-held tip.
- `nestor.frank` — optional mirror into willow-mcp FRANK (governance chain).

Pin Nestor at promotion time the way terpsi's `FLEET-READS.md` pins Nestor SHA.

## Open / next

- **All four critical gaps from the 2026-07-31 review now have a concrete
  mechanism; a second review (2026-08-01, `docs/design/the-forge-review-2026-07-31.md`
  plus an independent Opus pass) checked the fixes themselves and found one
  of them contained a false claim, now corrected below. Still pure design —
  nothing here is implemented.**
  - **D11** (GitHub was the root of the identity namespace): fixed by a
    store-minted `builder_id` with GitHub bound as one authenticator, not
    the identity itself, with uniqueness enforced at bind time and a
    path-safe charset rule borrowed from `promote_check.py`'s existing
    `_APP_ID_PATTERN`.
  - **D4** (no key custody, rotate/compromise unearned by static Sigstore):
    fixed by naming custody as store-held (living in the existing
    `safe-app-installer.md` D7 Fernet vault) and a signing-event ledger
    whose tip is pinned *externally* — operator-held, not just verified
    against itself — closing the circularity of the store both holding the
    keys and writing the ledger that would prove compromise timing.
  - **D5** (fail-open shape classification): fixed by default-deny via an
    explicit per-server allowlist, modeled on `nestor.serve.Server`'s closed
    tool list + `WITHHELD` set.
  - **D3** (seam validated *where*, not *what*) — **the fix itself was
    partly wrong, now corrected.** The original fix claimed
    `tools/vault_leak_lint.py` was AST-based (it's regex/line-based) and
    that generated code is never executed host-side in this repo (false —
    `promote_check.py` runs candidate pytest suites unsandboxed; see the
    new item below). D3 now states what's actually needed: a scan built to
    cover function bodies, not adapted from either existing file, plus
    fixing `promote_check.py` itself as a real prerequisite, not an
    assumption.
  - What each fix still needs before it's more than design: D11 has no
    authenticator re-linking flow (one GitHub account per `builder_id`,
    permanently, for v1); D4's signing-ledger storage/ops story (where the
    externally-pinned tip actually lives) is still unspecified; D5 still
    needs an allowlist authored for every server besides Nestor, and
    nothing yet stops a server from being registered without one; D3's
    dangerous-pattern list for the pre-crossing scan is unenumerated, same
    open-ended shape as D8's "where exactly a decision starts."
- **`promote_check.py` executes candidate code host-side, unsandboxed —
  newly found 2026-08-01, repo-wide, not Forge-specific.** It runs
  `subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=cand)` on
  every promotion candidate's real test suite, and the files that get
  AST-scanned for safety and the files that get executed are disjoint sets
  (the scanner explicitly skips anything with `test` in the filename).
  This affects every app going through promotion today, not just future
  Forge builds — D3 depends on it being fixed (test execution moved inside
  Kart or an equivalent sandbox), but fixing it is bigger than this design
  doc's scope to resolve alone.
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
- **GitHub OAuth app registration specifics** (D11) — scopes requested (read
  access to the builder's identity only, presumably; no repo access needed
  unless a later feature wants to push a promoted build straight to a
  builder's own GitHub), callback/session-token lifetime, and whether this
  reuses any existing GitHub App this org already has registered or needs its
  own.
- ~~Whether `willow-mcp`'s existing single-user OAuth gets touched at all~~
  — **confirmed, 2026-08-01, checked against the real code at
  `/workspace/willow-mcp`, not assumed.** `GroveOAuthProvider`
  (`src/willow_mcp/oauth.py`) authenticates against **Google/Apple**, not
  GitHub — zero identity-provider overlap with D11's plan, and it keeps its
  own state at a caller-supplied `token_path`, independent of anything
  safe-app-store would build. D11 is additive, confirmed, not assumed.

  Found something more useful than the answer to this question along the
  way: `src/willow_mcp/identity_binding.py` already implements almost
  exactly D11's shape — `propose_binding(idp, subject_id, email)` creates
  an *unconfirmed* record on first sign-in, `resolve_app_id` only returns
  standing for a **confirmed** one, and confirmation is deliberately **not**
  reachable from any MCP tool — operator-only, local CLI, so a remote caller
  can never confirm their own binding. That's a materially more conservative
  posture than D11's "mint and bind in one operation on first login" (still
  correct per what D11 actually says, but worth naming as a real design
  tension, not resolving unilaterally here): should first login grant
  standing immediately, or only after an operator confirms it, the way this
  sibling component already does? Also worth reusing regardless of that
  call: `identity_binding.py`'s filename-safety charset
  (`^[A-Za-z0-9_.\-:]{1,256}$`) and its atomic write (temp file + `os.replace`)
  are both patterns this codebase's own `sap_gate.py`/`plan.py` arrived at
  independently but don't yet use the atomic-write half of.
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
- **Scope cut proposed in review, not yet decided**: whether to build a
  minimal single-tenant slice first — no auth (D11), no signing (D4), no
  Casbin (D1/D5), just the seam with a real plan schema (D3) + Kart + LiteLLM
  — and treat D9/D10/D12 (the learning layer) as a fully separable follow-on
  with zero security weight, cut from v1 entirely.
- **Spend/abuse metering is undesigned.** D7 gates *permission* to use cloud
  fallback, never *cost* — nothing here bounds what a tenant can actually
  spend once cloud fallback is on.
- **Prompt injection isn't in the threat model yet.** Third-party content
  (KB documents, MCP tool results) reaches the model that authors the seam's
  plan; D2/D3 treat that model as trusted-but-sandboxed, not as something an
  attacker could steer.
- **`apps/<builder_id>/<name>/` vs. CLAUDE.md rule 10** — rule 10 hardcodes
  `app_id = directory name` for playground apps; D6's nested builder
  directory breaks that assumption for every existing consumer
  (`promote_check.py`, the catalog, `make run`). Unaddressed.
- **`kartikeya` isn't actually wired into this repo yet** — it's a sibling
  repo, not a declared dependency of `safe-app-store` today. `tools/seam_install.py`
  currently shells to `bwrap` "when available" and proceeds silently without
  it if not — the opposite of what D2/D3 assume holds.
- **terpsi-music** was brought in as a worked example, not a dependency — its
  three-zone privacy design (`docs/ARCHITECTURE.md` §1: on-prem hub / untrusted
  relay / edge replicas) may be worth a closer read once D6's tenant-isolation
  shape firms up, since it's the same "how little can the shared surface be
  trusted" question this doc keeps landing on.
