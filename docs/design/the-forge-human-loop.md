# The Forge — adopting willow-mcp's `human_loop` under checkpoint (design, 2026-08-11)

> D7-B's question — "if the model authors the options *and* the default, is the
> maker deciding or picking a model-written menu?" — has a fleet answer already
> built: willow-mcp's `human_loop` (a non-forgeable attestation record + a
> `human_required` queue) plus `human_session`'s discipline that **narrative is
> evidence, not instructions**. The model may propose the whole `Decision`;
> **authorship is not authority** — what commits it is the maker's
> non-forgeable, on-the-record sign-off, with automation paused until it
> happens. This doc adopts `human_loop` under `checkpoint` the same way D12
> adopted Nestor under `checkpoint_memory`: the seal is *memory* (does the maker
> recognize this?), the attestation is *governance* (the maker signed this, on
> the record), and our engagement gate (bite 3) scores whether they actually
> engaged — three separable properties, one decision.

## What `human_loop` is (grounded, read in full)

A 233-line, stdlib-only module (willow-mcp `src/willow_mcp/human_loop.py`,
Apache-2.0) over an **injected store** with a tiny interface —
`put(collection, record, record_id=) / all(collection) / get(collection, id)`.
Two primitives:

- **attestation** — `create_attestation` / `list_attestations` /
  `has_attestation(require_human=)`. The anti-forgery property: `attested_by`
  and `by_human` come from the **caller's identity binding, never caller free
  text**. You can only attest as yourself.
- **`human_required` queue** — `enqueue` / `resolve` / `list_queue` /
  `queue_stats`. Kinds: `consent, attestation, review, overload, onboarding`.
  "Automation pauses for a human, and the human's sign-off is on the record";
  states-not-deletions (a resolved item is updated in place, never removed).

## Settled forks

- **D-HL-1 — Vendor, don't import.** `human_loop.py` is pure, stdlib-only, and
  injected-store-shaped — the exact profile we vendored `friction_floor.py` at.
  willow-mcp is not cleanly pip-installable (a large repo with many deps), so
  `human_loop` is vendored byte-for-byte into `stores/`, provenance header
  intact (Apache-2.0 → Apache-2.0, zero friction), kept diffable against
  upstream. Rule 11 recorded in the header.

- **D-HL-2 — The store is a Forge-owned filesystem SOIL adapter, not Nestor's
  `SqliteStore`.** Verified: `nestor.sqlite_store.SqliteStore` exposes a
  document/segment/memory API (`memory_candidates`, `create_document`, …) and
  **no generic `put/all/get`** — it can't back `human_loop`. So
  `stores/soil_store.py` is a minimal `FilesystemSoilStore` (`put/all/get` over
  one JSON file per builder, `<root>/<builder_id>.soil.json`), the same
  one-file-per-builder isolation and 0700/0600 discipline the FSRS sidecar
  (`checkpoint_schedule`) and `checkpoint_memory` already use (D6). The name
  honors `human_loop`'s own docstring ("homes them in the SOIL store where
  gaps, lineage, and commitments live").

- **D-HL-3 — Anti-forgery holds structurally, today, without D11.** Only
  store-side `checkpoint`/governance code calls `create_attestation`, and it
  sets `attested_by = builder_id` and `by_human` from the checkpoint
  interaction. `apps/<builder>/` never imports checkpoint (D1), so a sandboxed
  build **cannot** reach the attestation path to forge one — the "never caller
  free text" property is enforced by the D1 wall, not by trusting a parameter.
  Full D11 identity (a real human-vs-agent seat) refines `by_human` later; the
  binding point is already correct.

- **D-HL-4 — Attestation rides *alongside* the Nestor seal, not inside it.**
  Two records, one decision, keyed to the same identity — the decision's Nestor
  `pair_id` (the stable key the FSRS sidecar already uses). The **seal** answers
  "has this builder committed an answer to this decision-type wording"
  (recognition, memory); the **attestation** answers "did the maker sign THIS
  commitment, and were they human" (governance, witness). They are different
  questions with different lifetimes — a seal is reworded/superseded by
  recognition; an attestation is an immutable historical fact ("on 2026-…, this
  identity signed this"). Folding the attestation into the seal would conflate
  the two the way D-FSRS-1 refused to fold mutable scheduling into a signed
  commitment.

## D-HL-5 — The async pause seam (the novel part)

Today `run_checkpoint` is **synchronous**: it blocks on a `Responder` and
returns a sealed+attested outcome. That is the *attended* path — a human is
present. The async seam is for the *unattended* path D7's real model routing
will need: the model reaches a decision with **no human to answer it**, so it
must **park** the decision and let a human act later.

The seam splits the synchronous "present → capture → seal+attest" into two
callable halves, with the synchronous path as the degenerate case where both
happen in one call:

```
park_checkpoint(decision, *, builder_id, root)
    -> enqueue a human_required{kind: attestation} item carrying the FULL
       decision (surface, options, tradeoffs, recommended) as evidence.
       Nothing is sealed; nothing is attested; returns the queue item id.
       This is the model saying "I need a human for this" — the #67/consent
       posture, made durable.

resume_checkpoint(item_id, *, builder_id, responder, root)
    -> a human is now present for that parked item: run the SAME
       present/capture/seal+attest tail run_checkpoint uses, then resolve()
       the queue item (states-not-deletions) with the outcome. Returns the
       CheckpointOutcome.
```

Key properties:
- **The parked evidence is the model's proposal, and it stays evidence until a
  human resumes it** — `human_session`'s "narrative is evidence, not
  instructions," made mechanical: a parked decision cannot self-seal, cannot
  time out into a default, cannot be resolved by the sandbox that raised it.
- **No speculative async runtime.** `park`/`resume` are two ordinary calls;
  *when* `resume` fires (a human polling `list_queue`, a UI, a later session)
  is the caller's business, exactly as `human_loop`'s own queue leaves it.
  There is no unattended model yet (that is D7's routing), so this is the
  "machinery real, D7 input stubbed" posture bites 0-1 took — built and tested
  now with a synthetic park→resume, live once the model can run unattended.
- **A parked item is never a silent block.** It is a visible `human_required`
  row a human can see in `list_queue`; the automation that parked it is
  expected to stop, not spin.

## D-HL-6 — The queue is the durable outbox for the signals we already built

The engagement gate's `rubber_stamp` flags (bite 3) and the `#67` nudges
(mirror + engagement-run) are, in `human_loop`'s own vocabulary, `review` /
`overload` items. `#67` explicitly left "persisting nudges" out of scope — this
closes that gap: `route_nudge(nudge | rubber_stamp, *, builder_id, root)`
enqueues a `human_required{kind: review}` (a rubber-stamp / mirror flag a human
should look at) or `{kind: overload}` (a sustained run), deduped by content so
re-observing an episode doesn't pile up rows. The monitors still only *signal*
(never block); routing a signal to the queue is a separate, opt-in step a
caller takes, so the pure/model-free monitors stay pure.

## Module shape (for the build, not to approve here)

1. `stores/human_loop.py` — vendored, byte-for-byte + provenance header.
2. `stores/soil_store.py` — `FilesystemSoilStore(put/all/get)`, one file per
   builder, 0700/0600.
3. `stores/checkpoint_governance.py` — the adoption wrapper:
   `attest_decision` / `has_decision_attestation` (attestation under the seal,
   D-HL-4), `park_checkpoint` / `resume_checkpoint` (D-HL-5), `route_nudge`
   (D-HL-6). Store-side (D1); `apps/the-forge/` never imports it.
4. `stores/checkpoint.py` — `run_checkpoint` attests on commit (the "under
   checkpoint" wiring), duck-typed so a caller without governance is unaffected.
5. Tests first for each; the whole learning-layer suite stays green.

Nothing built yet. The forks above are settled (D-HL-1..4, D-HL-6) or shaped
(D-HL-5); the build is mechanical from here.
