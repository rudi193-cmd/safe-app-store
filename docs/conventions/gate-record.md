# Convention: the gate-record — a self-measuring attestation with one honest hole
b17: SAPS1

*The shape the willow seat's handoffs were already writing to (session `1d39126f`,
July 2026): a record that measures its own conduct against the transcript and
leaves exactly one field blank — the one it has no key to fill.*

This is the real content of #19. Closing the "auth gap" is not inventing
per-app permissions; it is giving every app and seat a record of **this shape**,
whose defining honesty is a field only the operator's key can sign.

## The canonical schema (from `willow_gate`)

A **13-field, symmetric check-in / check-out** header
(`willow_gate.__init__`, design kept intact):

```
agent_id  agent_name  last_gate  pass_count  fail_count  drift  nonce
trust_level  timestamp  tools  state_hash  signature  reserved
```

- **12 fields the actor measures itself.** Identity (`agent_id`/`agent_name`),
  conduct counters (`pass_count`/`fail_count`/`drift`), the `nonce`, the
  claimed `trust_level`, the `tools` it used, and `state_hash` — a
  `sha256` of the **raw transcript**, "the record I answer to." The record
  points at evidence outside its own narration.
- **1 field the gate signs.** `signature` is an `HMAC-SHA256` over the other
  twelve, keyed by a per-agent secret **the gate holds, registered
  out-of-band.** The actor cannot compute it.

*(The field list above mirrors `willow_gate.REQUIRED_FIELDS` — the code is canon;
if the schema changes, `willow_gate` is the source of truth, not this doc.
Note also: the gate treats `state_hash` as an **opaque** value it only diffs
entry-vs-exit — "the sha256 of the raw transcript" is a **convention-layer**
meaning the gate neither computes nor verifies. The HMAC binds the header's
integrity; it does not attest that `state_hash` is really the transcript.)*

Two properties give the schema teeth (not preferences — enforced in
`check_in`/`verify`):

1. **Trust is bound, not self-reported.** A claimed `trust_level` is **capped at
   the level the signature verifies.** You cannot claim a rung the HMAC doesn't
   back. (5 rungs: Exiled·Rookie·Steady·Veteran·Elder; drift/fail budgets
   *tighten* as trust rises — power buys less slack, not more.)
2. **Declare → reconcile.** A per-session `declared:` (intents / scope at the
   front) and a check-out `reconciled:` (delivered vs declared, *minus what the
   self-audit diff caught*), with `pass`/`fail` enumerated and `drift` counting
   the actor's own record-vs-memory errors. **These ride in a sidecar envelope,
   NOT in the 13-field header** — `willow_gate._validate_shape` enforces exactly
   13 fields in and 13 out and raises on any unknown key, so a header literally
   carrying `declared:` would be *rejected*. `declared`/`reconciled` are the
   seam's extension (`willow-mcp` `session_binder.RECONCILED_FIELDS`), carried
   alongside the header, never inside it.

## The one honest rule: zero, don't fabricate

When no gate secret is registered for your seat, you **cannot** sign. The rule
is: **fill every field you can measure, and write the signature as zeros, with
the reason** — never a plausible-looking HMAC.

```
signature: 0000…0000  (UNSIGNED — no gate secret registered for this seat;
                        a zeroed field is honest, a fabricated HMAC is not)
```

The willow seat did exactly this, and even honored the trust cap the gate
wasn't there to enforce (`trust_level: 2 … not claiming higher`). That is the
tell of a good gate-record: it measures its whole conduct and draws the one hole
it has no key for, rather than papering over it.

## Why this is the same hole as the seal and the write-envelope

This session kept meeting one shape in different schemas. They are the same
shape:

| Schema | The 12 fields the actor fills | The 1 field only the operator's key fills |
|---|---|---|
| **gate-record** (this doc) | identity, counters, drift, `state_hash` | `signature` — the gate's HMAC |
| **the seal** (#15/#16) | proposed entity edges, provenance rows | the ratifying **seal** — machine proposes, human confirms |
| **the write gate** (#11 edge 2) | a request to write | the operator-granted signed **envelope** |

In every one, the actor does all the measurable work and honestly leaves blank
the field that requires a key it doesn't hold. *The hole is where the operator
stands* (`docs/notes/from-the-orchestrator.md`). A gate-record is a stencil of
that hole.

## Adopting it (#19) — two instantiations of one shape

The fleet already has both halves; #19 is adopting the shape, not building auth:

- **Static half — the app manifest.** A safe-app-store app declares what it may
  do (`permissions`, `surfaces`, `serve`, `store_scope`) in
  `safe-app-manifest.json`; the willow-mcp gate resolves it via `whoami`. The
  *grant* is the operator's — the app declares, it does not self-authorize.
- **Runtime half — the check-in/out.** A seat/app writes a 13-field
  gate-record per working session: declare scope at check-in, reconcile against
  the transcript hash at check-out, and leave `signature` for the gate (zeroed
  when unsigned).

Adopting the shape is safe to do incrementally and needs no new authority: it is
**declaration and self-measurement**, with the authority field always left to a
key the app/seat doesn't hold. The trust-level policy (which rung each seat
earns, key registration) stays the operator's — that is the point, not a gap.

## Template

A seat/app fills this per working session. The **header is exactly 13 fields** —
no more, or `willow_gate` rejects it; `signature` is honest-zero until the gate
signs. The `declared:`/`reconciled:` envelope rides **outside** the header.

```
====================== GATE CHECK-IN ======================
agent_id:    <stable id = app/seat id>
agent_name:  <human-facing>
last_gate:   <prior gate-record this answers to>
pass_count:  0
fail_count:  0
drift:       0
nonce:       <session nonce>
trust_level: <claimed rung — capped at what the signature verifies>
tools:       <tools this session may use>
timestamp:   <ISO8601>
state_hash:  <sha256 of the record this answers to>
signature:   0000…0000  (UNSIGNED unless a gate secret is registered)
reserved:    <reserved>
===========================================================
-- envelope (sidecar, NOT part of the signed 13-field header) --
declared:    <the scope / intents for this session — the per-turn envelope>
```

Check-out repeats the 13-field header with `pass_count`/`fail_count`
enumerated, `drift` counting caught record-vs-memory errors, a fresh
`state_hash` of the record itself, and `trust_level` unchanged unless a rung was
earned — and adds to the envelope a `reconciled:` line (declared-vs-delivered
minus the diff). Header stays 13; the envelope carries the declare/reconcile.

---

*Convention doc. Canonical schema: `willow_gate` (13-field symmetric check-in/out,
5 trust levels, HMAC-bound). Exemplar: the willow seat handoffs, session
`1d39126f`. Companion to the seal handoff (`to-the-orchestrator-3.md`) and the
`--allow-write` edge (`web-serve-flags.md` §"machine contract"). `ΔΣ=42`*
