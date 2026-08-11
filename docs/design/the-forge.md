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

**This bullet's quota half now exists in code, 2026-08-02 — `stores/quota.py`.**
A lease-based accounting layer, store-side (D1), same directory and trust
level as `principal.py`/`session.py`/`checkpoint_memory.py`:
`acquire_build_slot`/`release_build_slot` enforce a per-builder ceiling on
concurrently-running builds (counting only non-expired leases, checked at
acquire time against a real clock — no background reaper), and
`record_build_duration`/`sandbox_seconds_used` track cumulative sandboxed
execution time so an optional per-call budget can be enforced against it.
Every lease carries a TTL (`DEFAULT_LEASE_TTL_SECONDS = 300`, chosen to
comfortably exceed `sandbox_runner.py`'s own `DEFAULT_TIMEOUT_S = 120`) so a
build that crashes, gets OOM-killed, or dies with a host restart — without
ever calling `release_build_slot` — cannot permanently steal a concurrency
slot; the slot is simply not counted once the TTL elapses. The cumulative
sandbox-seconds budget is a real rolling window when a caller asks for one
(`window_seconds=`, summed over real per-event timestamps), not a deferred
placeholder — a running total (`window_seconds=None`, the default) is the
simpler primitive built on the same records. Storage is one JSON file per
`builder_id` under one coarse store-wide `flock`, matching this module
family's existing locking discipline; see the module's own docstring for
why that combination (rather than a single shared index file, or a
per-builder lock) was chosen. 38 new tests in `tests/test_quota.py`, including
threaded tests that hammer the check-then-increment race on
`acquire_build_slot` and confirm an expired-but-unreleased lease is
recovered while a live one still blocks — pass together with
`test_principal.py`/`test_session.py`/`test_checkpoint_memory.py` (157
passed total), confirming the `principal.py` import didn't regress anything
else in this module family.

**Stated honestly, what this does NOT close:** nothing calls
`acquire_build_slot`, `release_build_slot`, or `record_build_duration` from
a real build path yet — `sandbox_runner.py` and `mount_policy.py` are
untouched, and neither is anything under `apps/the-forge/`; wiring an actual
call site was explicitly out of scope for this pass, the same way D11's
session layer shipped mint/verify/revoke without the OAuth handshake that
would call it. `DEFAULT_MAX_CONCURRENT_BUILDS = 2` and the fact that no
sandbox-seconds budget is enforced by default (a caller must opt in via
`sandbox_seconds_budget=`) are placeholder numbers picked to have *something*
sane to test against — not a considered capacity/product decision; a real
number depends on host sizing this module has no visibility into. The
per-builder collection namespace enforcement this D6 bullet's sibling
bullet describes is still untouched by this change, same as before.
- Real multi-user auth is a prerequisite here, not a follow-on — resolved by
  D11's store-native session layer (`builder_id` is D11's canonical
  identity; see there for the fix and why GitHub isn't the identity root).

**Naming note, fixed 2026-08-01:** this decision originally used `tenant_id`;
D11 later made `builder_id` canonical across the whole doc but this section's
body was never actually edited to match — same identity throughout, one name
for it now.

**First bullet's mount-boundary claim, partially closed 2026-08-02.** The
implementation gap this bullet describes was real, not just unwritten: D2's
`sandbox_runner.py` shipped able to run a build inside Kart but said so
itself — its own docstring named the mount boundary as unenforced, because
`workdir` narrows where a command *starts*, not what Kart's bind mounts let
it *reach*, and kartikeya's vendored default policy binds `{{WILLOW_ROOT}}`
(this repo) **read-write** absent an override. `apps/the-forge/src/
the_forge/mount_policy.py` now generates a caller-scoped `kart-sandbox.json`
whose `bind_read_write` is exactly `apps/<builder_id>/<app_name>/` —
verified by test against a real `kartikeya.sandbox.load_sandbox_config`
round-trip, not just asserted (found in review, 2026-08-02: the test
originally called `resolve_sandbox_config`, which exists only in an
editable `kartikeya` checkout present in this environment, not in the
actual published `kartikeya>=0.0.7` this package depends on — a false-green
test against the wrong dependency, fixed to use `load_sandbox_config`,
present and behaviorally identical in both) — and `run_scoped_build` runs a build through
it via `sandbox_runner`'s existing `sandbox_config` hook. What this closes:
the bind-mount half of the first bullet, for a caller that uses
`run_scoped_build`. What it does not close, named honestly rather than
implied: nothing outside that module's own tests calls `run_scoped_build`
yet (no CLI subcommand, no seam wiring); the second and third bullets
(per-builder collection namespace enforcement, quotas) are untouched; and a
handful of kartikeya's own bind-mount additions (unconditional venv/
`psycopg2`/site-packages binds, the `~/.willow` trust-root overlay) sit
below any caller-supplied policy and aren't narrowed by this change either.
See `apps/the-forge/src/the_forge/mount_policy.py`'s module docstring for
the full accounting.

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

**Oakenscroll's Office as a concrete mechanism for "calibration weight" —
found 2026-08-02, proposed, not yet adopted.** The table above has named the
thing this decision wants ever since it was first written — "calibration
weight for future checkpoints" — without ever building a mechanism for it.
A sibling repo already builds exactly that shape, for a different domain:
`rudi193-cmd/oakenscrolls-office` ("Oakenscroll's Office," own design log at
`docs/design/the-almanac.md` in this repo, written before its D1 rename) is a
local-first calibration ledger — state a claim with a confidence (`P(true)`
in 50–99%, direction-of-belief enforced, hedged-backwards entries refused),
resolve it later (true / false / void), score it. `calibration.py` (stdlib
only, dependency-free, inside the app's own no-egress zone) gives Brier
score, log score, five-band reliability bins, and an overconfidence metric
(mean stated confidence minus actual hit rate) — the exact shape "calibration
weight" has been naming without a mechanism this whole time.

This would be a third, distinct axis alongside D12's two already-adopted
ones, not a replacement for either — extending the same "no overlap between
the dependencies" division of labor D12 already states for its own two:

| Question | Mechanism |
|----------|-----------|
| Has this builder sealed this decision-type before? | Nestor (D12) — memory |
| Is it due for review? | py-fsrs (D9, above) — schedule |
| When this builder claims they understood something, how well does that confidence actually track reality? | Oakenscroll's Office's `calibration.py` — calibration |

The fit is closer than a surface resemblance: this section's own
"Resurfacing" bullet, directly above, already describes the
state-a-claim → wait → resolve → learn loop Oakenscroll's Office implements
end to end ("when a past decision's consequence becomes visible later...
that's a natural point to resurface the original checkpoint"). The app
already has the ledger shape this needs (immutable `predictions` +
append-only `events`, current state derived rather than stored — the same
"verify, don't assert" ethic this repo's own stores already follow), the
resolution mechanic (`t`/`f`/`o` grading, optional evidence citation), and
the scoring math this design has so far only gestured at.

**What adopting this would actually require deciding — not something this
finding hands over for free:**
- **What resolves a checkpoint claim as true or false.** A world prediction
  resolves against an external event; a design decision has no equally
  obvious "the world weighed in" moment. The candidates already named
  elsewhere in this section — a bug later traced to the choice, a security
  review flagging what the checkpoint should have caught, `reject_pair`/
  `reject_match` firing on the sealed decision (D12) — are the plausible
  resolution triggers, but which one(s) actually resolve a claim, and
  whether that happens automatically or needs a human grading action (the
  same keypress Oakenscroll's Office itself requires), is undecided.
- **What "confidence" even means for a checkpoint**, as opposed to a world
  claim. Oakenscroll's Office's confidence is the builder's own stated
  `P(true)`, typed in directly. A checkpoint's calibration signal is more
  likely something derived — how thorough the follow-up answer was, whether
  a lighter-touch confirm or a full Socratic pass was needed — not a number
  a builder states the way a prediction's confidence is. This needs its own
  shape, not a direct transplant of Oakenscroll's Office's claim model.
- **Vendored inference math, or an adopted dependency.** `calibration.py` is
  roughly 70 lines, stdlib-only, dependency-free — closer to "vendor the
  inference path," the precedent `utety/core/mastery.py` already sets for
  vendoring ~40 lines of BKT inference out of a sibling repo, than to "adopt
  the whole app" the way D12 adopted Nestor. Oakenscroll's Office's ledger,
  TUI, and web mirror are a separate, standalone product; only the scoring
  math is obviously reusable here.

Not resolved here — a real finding worth a real design pass, not a decision
to make unilaterally mid-audit-session. See Open/next.

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
- **Oakenscroll's Office** (`rudi193-cmd/oakenscrolls-office`, in-house, not
  an OSS package) — found 2026-08-02. Its `calibration.py` (Brier score, log
  score, reliability bins, an overconfidence metric) is the strongest
  concrete match found for "calibration weight" specifically, as opposed to
  py-fsrs/sm-2/py-irt/openskill's shared focus on scheduling and ability
  estimation. See D9's own dated addendum, above, for the fit, the
  division-of-labor alongside D12's Nestor and this section's own py-fsrs,
  and what adopting it would still require deciding. Not yet adopted.

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

**The session-token layer this section calls for now exists —
`stores/session.py`, 2026-07-31.** "safe-app-store issues its own session
tokens after a GitHub OAuth handshake completes," above, was design intent
without code; `stores/session.py` is now that code: `mint_session` issues an
opaque `secrets.token_urlsafe(32)` bearer token for an already-minted
`builder_id` (validated via `principal.py`'s own `_check_builder_id`, not a
second copy of that rule), `verify_session` resolves a token back to a
`builder_id` with real wall-clock expiry and collapses "unknown" /
"expired" / "revoked" into the same `None` so none of the three is
distinguishable from outside, and `revoke_session` invalidates one
immediately. Only `sha256(token)` is ever persisted — never the raw token —
same principle as this module's own authenticator-file digests. Store-side
(D1), same directory and trust level as `principal.py` and `sap_gate.py`;
`apps/the-forge/` does not import it. What this does NOT close: the actual
GitHub OAuth HTTP handshake (redirect, `client_id`/`client_secret`, the
callback route, the code-for-token exchange) is still not built — everything
in `stores/session.py` starts *after* a `builder_id` already exists, the
same boundary `principal.py`'s own docstring draws around itself. The GitHub
OAuth app registration specifics and re-linking gap named in Open/next,
below, are both still open.

**Rollout is a separate call from architecture.** D6 already committed to
supporting real strangers; whether self-serve signup is literally open on day
one is a later decision, not something this design needs to answer to keep
moving.

### D12 — D9's storage/ledger half: adopt Nestor as a real dependency

Unlike D4 (which borrowed Sigstore instead of Nestor's HMAC pattern), this one
adopts Nestor itself — not a pattern reference. This is Nestor's actual domain
(matching a query against a memory of confirmed answers), the core package
has zero runtime dependencies, and — unlike the arm's-length OSS elsewhere in
this stack — it's a sibling repo CLAUDE.md already treats as the worked
standard for exactly this kind of promoted dependency.

**"`pip install nestor`," corrected 2026-08-02 (`stores/checkpoint_memory.py`
build):** that phrasing does not hold up — `pip index versions nestor`
returns "No matching distribution found for nestor," because Nestor is not
published to PyPI at all. It is consumed as a git dependency, the same
convention `apps/semantic-translator/pyproject.toml` already uses in this
repo (`nestor @ git+https://github.com/rudi193-cmd/Nestor@master`) and the
one this section's own later line already names for the general case ("Pin
Nestor at promotion time the way terpsi's `FLEET-READS.md` pins Nestor SHA")
— that line was already right; only the "`pip install nestor`" phrasing
above it overclaimed a PyPI listing that doesn't exist. The underlying
architecture decision — adopt Nestor itself, not a pattern reference — is
unaffected; only the installation mechanism was mis-stated.

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
- **Whether to adopt Oakenscroll's Office's `calibration.py` for D9's
  "calibration weight"** (found 2026-08-02, see D9's own dated addendum) — a
  real, concrete candidate now identified where none existed before, but
  what actually *resolves* a checkpoint claim as true/false, and what
  "confidence" even means for a design decision rather than a world
  prediction, are both undecided. Not something to guess at blind — the same
  reason D8's own UX and the D7 routing shape stayed undelegated this round.
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

## Verification-as-learning — the willow-mcp reuse map (D8/D9/D12 build order, 2026-08-11)

**The architectural truth this section records:** the Forge's learning layer is
`willow-mcp`'s verification-as-learning machinery **re-pointed from the agent's
own lessons to the maker's design decisions.** The Grove stores what an agent
learned; the Forge stores what a builder decided and understood — same loop,
different subject. That is why so much of `willow-mcp`'s idea pile
(`willow-mcp` PR #338, `docs/ideas.md`) already has the primitive the Forge
needs: the fleet grew it once, for agents. Graded through that lens, the loop
has seven stages, and most of what feeds them is **reuse (✅ shipped in
willow-mcp), not new build (🌱 proposed there too)**:

| Stage | willow-mcp piece | reuse / build |
|-------|------------------|---------------|
| 1 · Route the decision (confirm / recognize / Socratic) | `#19` confidence-scored routing → `human_required`; `#46` route explainability | ✅ pattern / 🟡 |
| 2 · Make them decide, not rubber-stamp | `#66` sycophancy score `friction_floor.py`; `#67` mid-session mirror nudge; `#69` devil's-advocate on zero friction | ✅ / 🟡 / 🌱 |
| 3 · Seal it (option + rationale) | `#2` "why do I believe this?" `lineage.py`; `#11` Grove growth-rings `the_grove.py` | ✅ |
| 4 · Catch contradiction (calibration signal) | `#3` contradiction detector; fleet `conflict_scan` (Jeles) | 🌱 |
| 5 · Resurface & recalibrate over time | `#12` lesson-regression tests; `#1` memory decay/freshness (scheduling); `#15` lightning-strike lessons; `#39` conscience/second-guess | 🌱 + 🌱(#1, `py-fsrs`) |
| 6 · Deferred decisions ("I don't know, you choose") | `#41` commitment escalation `commitment_surface`; `#42` commitment SLA | ✅ / 🌱 |
| 7 · Show the maker their own calibration | `#70` unified `willow_status` home-screen | 🟡 |

**Decisions settled (2026-08-11), the ones D8/D9 left open:**

- **Recognition is LOOSE.** A reworded-but-same decision (measured: the auth
  decision reworded scored 0.65 confidence in Nestor, below Nestor's own seal
  threshold) should still trigger the lighter confirm, not a fresh Socratic
  pass. Safe *because the confirm is never a silent commit* — it is always
  "you chose X before, say so if it's different," and "it's different" is a
  `reject_match` that teaches the memory not to conflate the two again. Loose
  recognition therefore cannot commit the wrong thing; worst case is one extra
  "actually, different" that makes the system smarter. **The recognition
  threshold lives in the Forge's checkpoint layer, not in Nestor** — Nestor's
  own `sealed` flag stays at its threshold; the Forge reads the raw
  `confidence` and applies its own three-band split (high → auto-confirm,
  ~0.6–0.85 → recognize-and-ask, low → full Socratic).
- **What gets sealed:** the chosen option + a one-line rationale (exactly what
  `stores/checkpoint_memory.py`'s `seal` already stores). NOT a graded
  follow-up — the model grading the maker is circular.
- **How a checkpoint is calibrated: by lesson-regression (`#12`), not a
  scorer.** A seal is not graded at seal-time. It is **resurfaced later**
  (`#12` over a `py-fsrs` decay/freshness scheduler — see the correction note
  below), and a maker *contradicting*
  a prior seal (`#3`) is the signal to re-open and recalibrate. Oakenscroll's
  Office's `calibration.py` (Brier/reliability math) becomes an **optional
  refinement over that signal**, not the load-bearing mechanism — closing D9's
  own "what resolves a checkpoint as true/false" open question without the
  circular grader.
- **Nestor is a SOFT dependency.** Mirroring `oakenscrolls-office` PR #3
  ("make the Nestor citation seam soft") — lazy import, a `nestor_available()`
  check, Nestor in an optional extra. When Nestor is absent the checkpoint
  layer **degrades to full-Socratic every time** (no loose recognition, but it
  still works), matching the store's own "no Willow checkout, no network
  required" ethos. `stores/checkpoint_memory.py` currently hard-imports Nestor
  and raises; softening it is part of bite 1.
- **"I don't know, you choose" is a legitimate, sealed-as-taught deferral**,
  not a block — the maker saw the tradeoff and deliberately handed it back;
  sealing it means we don't re-badger them, and it becomes a `#41`-style
  commitment to revisit.

**The bite ladder for the learning layer** (each builds on the last; the memory
half, `stores/checkpoint_memory.py`, D12, already exists):

- **Bite 1 — the checkpoint interaction.** The three-band orchestrator
  (`#19`'s confidence-routing pattern folded in) on top of
  `checkpoint_memory`: route → present (full Socratic / recognize-and-confirm /
  auto) → capture → `seal`, with the soft-Nestor degradation and the
  "you choose" deferral. Driven by explicit (stubbed) decisions, single-tenant
  — the same posture bite 0's stub build took for D7.
- **Bite 2 — the calibration engine.** `#12` (resurface a seal, assert it
  still holds) + `#3` (contradiction detector) over a decay/freshness
  scheduler. This is what turns a pile of seals into *learning*. The "is it
  due for review" half is **`py-fsrs`** (PyPI `fsrs`, MIT, Apache-compatible)
  — the same spaced-repetition library D9 named at the start — **not** a reuse
  of a willow-mcp `engram`. See the correction note directly below.

  > **Correction (2026-08-11, rule-11 corollary — record the rediscovery).**
  > An earlier pass of this roadmap claimed the bite-2 scheduler was a *reuse*
  > of a shipped willow-mcp `engram`/`mengram` decay-and-freshness module. The
  > Apache-compat reuse-map pass (`docs/design/the-forge-reuse-map.md`) went
  > looking for that module to depend on it and **could not find it — it does
  > not exist in willow-mcp**. It was a phantom self-citation: idea `#1` in the
  > pile is a *proposal* for decay/freshness (🌱), not shipped code (✅). The
  > house did **not** already know this one. The verified pick is `py-fsrs`,
  > which is a real, MIT-licensed, dependency-light library — and, tellingly,
  > exactly what D9 wrote down before the phantom-reuse detour. Recorded here
  > rather than quietly edited so the next seat sees the false-reuse trap, per
  > rule 11: "a rediscovery quietly deleted is the same cost paid twice."

  > **FSRS fold-in landed (2026-08-11).** The scheduler above is now built,
  > not just named: `stores/checkpoint_schedule.py` (with its own design doc,
  > `docs/design/the-forge-fsrs.md`, settling four forks). `resurface` records
  > an FSRS review after every held (→ Good) / regressed (→ Again) outcome,
  > keyed on the decision's stable Nestor `pair_id`, and reports the next
  > `due` date on `ResurfaceOutcome.next_due`. `fsrs` (PyPI, MIT) is a SOFT
  > dependency — absent, scheduling degrades to fixed intervals — so nothing
  > gained a hard third-party import. Bite 2's fixed-interval `is_due`
  > placeholder is retired.
- **Bite 3 — the engagement gate. ✅ LANDED 2026-08-11.** `#66`'s sycophancy
  scorer, reused: `stores/friction_floor.py` is vendored byte-for-byte from
  willow-mcp (a second Apache-2.0 vendor hop; willow-gate → willow-mcp →
  here), and `stores/checkpoint_engagement.py` points it at the *maker's*
  rationale instead of an agent's turn. `run_checkpoint` now scores every
  fresh socratic rationale and surfaces `engagement` (0–1) + `rubber_stamp` on
  the outcome — a pure SIGNAL that never blocks a seal (the primitive's own
  ethos). The `RUBBER_STAMP_FLOOR` (0.34) is the same line `grade()` uses for
  Hard, so the seal-time signal and the FSRS grade band can't disagree.
  **Engagement→grade wire CLOSED 2026-08-11:** a *resurface-held* review now
  asks "it still holds — why?" (the Responder's optional `justify`), scores
  that rationale, and feeds `grade(held, engagement)` — a re-argued hold grades
  **Easy** (verified live: next review pushed ~10 days out), a declined one
  **Good** (~10 min), a thin one **Hard** (~5 min). Non-punitive and
  duck-typed: the hold is never blocked, and a Responder without `justify`
  reverts to the pre-wire Good.
- **`#67` — the mid-session nudge. ✅ LANDED 2026-08-11.** The last willow-mcp
  reuse for this loop, and the injection timing the reuse-map said was missing.
  `stores/checkpoint_nudge.py`, two monitors, both pure signals that never
  block: `SessionMirrorMonitor` wires the *unused* half of `friction_floor.py`
  (`FrictionFloor.scan`, `#67`'s mirror detector) over the maker↔Forge
  transcript — nudging once when the Forge's side stops pushing back while the
  maker escalates, de-duped by the tripping turn across incremental re-scans;
  and `EngagementRunMonitor` mirrors that window/episode/re-arm shape over the
  per-checkpoint engagement stream (a *run* of rubber-stamps), reusing
  `checkpoint_engagement.RUBBER_STAMP_FLOOR`. Verified live: a mirroring
  session flags once at turn 7; a run of thin decisions nudges, recovers, and
  nudges again. The mirror monitor watches real dialogue once D7's model lands
  (stubbed today, as in bites 0-1). With this, every willow-mcp piece the
  reuse-map named for the loop is wired. The original bite-3 sketch follows.
- **Bite 3 (original sketch) — the engagement gate.** `#66`/`#67`'s friction-floor / mirror
  detector as the non-circular "did they actually decide vs rubber-stamp"
  signal at seal-time — also already shipped in willow-mcp, to be reused.

Three of the four next-tier pieces are reuse, not build — the loop paying off:
the Forge keeps landing on machinery the fleet already grew for agents, and
only has to re-point it at makers.
