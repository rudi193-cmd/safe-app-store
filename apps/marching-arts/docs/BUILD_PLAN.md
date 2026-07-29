# Build plan

**Every guarantee is a mechanism or it is a wish.**

A constraint that is stated will be violated. A constraint that is structural
cannot be. Not "we don't share health data" but *there is no code path that
transmits it*. Not "the model is calibrated" but *a test integrates radiated
power over a sphere and fails if it drifts*. Not "students can't see peer
rankings" but *ranked peer data is not in the product*.

Every phase below ships with the mechanism that makes its promise checkable. A
phase without a gate is not done.

Companion to [`PRODUCT_PLAN.md`](../../field-acoustics/docs/PRODUCT_PLAN.md) in
the sibling [`field-acoustics`][fa] build, which covers the acoustic capability
specifically. This covers the platform underneath it — the storage,
authorization, consent and transport every capability sits on, acoustics
included.

[fa]: ../../field-acoustics

---

## Why the plan looks like this

Three times during the work that produced it, correct process produced a wrong
answer. The fix was identical each time.

| What happened | Why process didn't catch it | The mechanical fix |
| --- | --- | --- |
| Directivity normalised to the axis, not the sphere | Beam shape looked right. Two independent reimplementations agreed to 1e-14 dB — with each other, on the same wrong input. The spectrum tilted 13 dB at 8 kHz. | A sphere-integration test that recovers declared sound power, or fails. |
| Residualising captions on their own total | The arithmetic was correct. The transformation manufactured negative correlations and produced a startling, entirely false finding about judge independence. | Rank within year. No aggregate the components compose. |
| An agent named an unadjudicated individual | The brief excluded it in prose. Nobody read the artifact before it was treated as done. | Exclusions as a self-audit checklist; a second pass reviewing for compliance, not coverage. |

The pattern is worth naming because it will recur: **the failure is never in the
step you are watching.** It is in the input you assumed, the transform you
thought was neutral, or the instruction you believed was followed.

---

## Three stores already in hand, and the mechanic they share

The plan does not need to invent its integrity model. It is already implemented
three times, in three places, by three different hands — and all three agree.

| Store | What it holds | How it records not-knowing |
| --- | --- | --- |
| `dci_scores.db` | 42 corps · 6 seasons · 12 events · 184 results · 280 caption rows · 530 repertoire entries · 103 shows | `seasons.scored = 0` for 2021 — a row that exists to say *no scored competition happened*. `events.complete = 0` on two events. `shows.confidence` ∈ confirmed/partial/unknown. Every `results`, `captions` and `repertoire` row carries a `source` string. |
| SOIL `gate_app_ideas` | 56 records — every decision, correction and refusal, parked rather than asserted | Each record carries `status` and `confidence` as first-class fields. Four records are corrections of earlier records, kept alongside rather than overwriting them. |
| Nestor | The cascade: sealed / draft / pending, over a hash-chained ledger | **pending** — "nothing to offer, said plainly rather than improvised." A machine answer is permanently **draft**. Only a human seals, and a human can reject just as durably. |

**Absence is a value, not a gap.** The database records that 2021 had no scored
competition. SOIL records that the core job was asked and never answered. Nestor
refuses to improvise when it has nothing. Three systems, built for unrelated
purposes, all reached the same conclusion: *a missing row and a row that says
"missing" are different facts, and conflating them is how a tool starts lying.*

This is the same trichotomy [`field-acoustics`][fa] carries as `MEASURED /
FITTED / ASSUMED`, propagated by `min()` so a result is worth its weakest input.
It is the same shape as the privacy model, where a refused consent grant must
render as *no slot* rather than an empty one. **Build it once, in P1, and the other three
become configurations of it.**

What this buys, concretely:

- **Nestor's cascade is the seal layer for every machine-produced number** — an
  acoustic prediction, a schedule conflict, a position diagnosis. Apache-2.0,
  zero runtime dependencies, 123 tests, and its `Storage` is an injectable
  `Protocol`. **Resolved by spike: fork the mechanic, do not adopt the package.**
  Two findings decided it. The browser half of P1 is TypeScript over
  sqlite-wasm, so depending on a Python package still requires the mechanic
  written twice; and this app authorizes through a SQL correlated subquery on
  `g.state = 'sealed'`, which cannot call Nestor's Python-side `is_verified_seal`
  — adopting its storage would import the vocabulary without the safety. Two
  things the spike found by running the code: there is no principal parameter
  anywhere in the 19-method `Storage` Protocol, so `memory_candidates` must
  return every row and score in Python, which is the exact leak shape `store.py`
  is built to refuse; and its fuzzy matcher scores two adjacent member ids at
  0.9524 against a 0.92 seal threshold. Worth taking from it regardless: its
  `ConflictingSealError` refuses a second verifier escalating a grant's band,
  which this app does not yet guard against.
- **SOIL is the decision ledger the project already needs.** Fifty-six records
  is the answer to "why is it built this way," queryable by anyone who joins
  later. Every settled decision below has a record id behind it.
- **The database is the P4 fixture.** Not sample data: real, sourced, and small
  enough (176 KB) to ship with the app for a demo that works offline on first
  load with no network at all.

---

## Settled

Each row is a SOIL record, not a recollection. The id is the audit trail.

| Decision | Basis | SOIL |
| --- | --- | --- |
| Apache-2.0, local-first, no accounts | Trust argument before cost argument. Only credible because the source is open and checkable. | `shell-is-shared` |
| Three zones: corps-private · adjudication · public | Adding spectators broke the single-LAN model cleanly. The publication boundary *is* the airlock — data becomes public when the announcer reads it. | `scope-whole-stadium` |
| Corps LAN, no WAN uplink | Makes no-egress a property of hardware. Corrected same day: a corps LAN is *not* a trusted network. | `sync-lan-hub`, `sync-lan-is-not-trusted` |
| Sync scope = permission scope | A device receives only what its holder may see. Blast radius of a stolen phone is one person. The authorization resolver does double duty as the sync filter — build it once. | `sync-scope-equals-permission` |
| TypeScript kernel. No Rust, no WASM, no SIMD. | Measured: literal Rust→wasm was *slower* than JS in-browser; SIMD produced binaries differing by one byte. The win was algebra, not language. 25.8 ms/set, 5.9× honest. | — |
| Measurement is not evaluation | The tool never produces a number that competes with a caption score. Machine output is permanently draft; only a human seals. | `decision-no-ai-judging`, `caption-dimensionality` |
| Ranked peer data is out of the product | No leaderboards on pedagogical grounds, and position-accuracy data ranks a squad whether you meant it to or not. | `decision-realized-positions` |
| L4 is named persons only | Not caption heads, not program coordinators, not roles. FLAG was redundant against L3 and leaked by existing. | `access-map-open-questions` |
| Safeguarding: route, never receive | In every leadership-implicating case on the public record, surfacing was external. Digitising a broken path digitises the breakage. | `safeguarding-design-answer`, `incidents-surfacing` |

### The number that settles "no AI judging" on evidence, not taste

The decision was made on values. The database independently makes it the
*correct* engineering call, which is a much better place to be. Spearman rank
correlation within each year and round, across four seasons — reproduce with
`tools/caption_dimensionality.py`:

| Sub-caption pair | Mean ρ | Worst single sheet | What it means |
| --- | ---: | ---: | --- |
| GE1 ~ GE2 | 0.988 | 0.978 | Two judges, two boxes, one judgement. Not two independent readings of effect. |
| Brass ~ Music Analysis | 0.977 | 0.937 | The music captions do not separate. |
| Visual Prof ~ Visual Analysis | 0.972 | 0.944 | Nor do the visual ones. |
| GE ~ Visual | 0.980 | 0.958 | Nor do the top-level captions from each other. |

n = 101 semifinals sheets, 2022–25. Spread on the same rows: GE sd 2.92 against
2.24 visual and 2.19 music — GE is where the separation lives, and it is also
the pair that agrees with itself most.

A model trained on this sheet would learn *placement* and dress it as eight
opinions. The honest product measures things the sheet does not contain — SPL at
a box seat, a schedule conflict, a coordinate — and hands the judgement to the
human. That is not a concession. It is the only defensible position.

> **Method note.** Rank within year and round. An earlier pass residualised each
> caption on the composed total, which forces negative correlation by
> construction and produced a false finding of GE1/GE2 *disagreement* at −0.24.
> The correct value is the +0.988 above. SOIL `methodology-residualising-error`.

---

## The build

Sequenced by dependency, not by visibility. The first two phases ship nothing a
user sees, and skipping them is how the leak gets built in.

### P1 — Storage and the authorization resolver · unblocked

The resolver is first because everything depends on it — including the sync
spine, which is the same component wearing a different hat.

- `@sqlite.org/sqlite-wasm` on the `opfs-sahpool` VFS, with a **SharedWorker
  owner** for multi-tab. One owner by construction rather than by protocol;
  `pauseVfs()`/`unpauseVfs()` supply the handoff, Web Locks supply the election.
- **CASL for per-record authorization**, plus a rules→SQL `WHERE` compiler,
  because no CASL→SQLite adapter exists. `cannot` rules must become `AND NOT`
  applied *after* the union of `can` rules — that precedence is the single most
  likely way to rebuild the leak.
- Data-classification band as a column on every row, present from the first
  migration.
- Aggregate suppression compiled into the predicate, so counts are safe by
  construction rather than by discipline.
- **A `source` or `confidence` column on every fact table, from the first
  migration** — copied straight from `dci_scores.db`. Retrofitting provenance is
  the same class of mistake as retrofitting the classification band: it can be
  added to the schema later but not to the data.
- The seal ledger and the domain data on the same connection, so they are one
  file backed up and audited as a unit. UTETY's `SqliteBackend` is the worked
  example: append-row and write-anchor in *one* transaction, because the
  filesystem backend's two non-atomic writes wedge the chain on a crash.
  (Correction: this lesson does **not** transfer to Nestor itself. Its ledger is
  a JSONL file with no head anchor and cannot join a SQLite transaction at all.
  The lesson is sound and migration 002 already applies it — it was cited two
  bullets after a package it does not describe.)

**Gate.** A test that seeds hidden rows and proves they cannot appear in a
`COUNT`, a filter, a sort order or an empty state. If the count is computed in
JavaScript over fetched rows, the phase is not done. Second gate: a row with no
`source` fails insertion.

### P2 — Identity, roles, consent · unblocked

- Adopt `subject-consent` from **safe-app-store/libs** — the canonical copy, not
  UTETY's vendored one. Grant/revoke/permitted, hash-chained disclosure log with
  a truncation anchor, de-identify-or-refuse.
- Roles as scoped grants — squad, caption, ensemble, season — resolving **per
  record, not per user**, because every leader is also a member.
- Guardian consent for minors. Silent revocation. Guardian access converts to
  member-granted at 18 rather than persisting.
- Wrap the roster core in `safe-app-common-package`'s **no_egress AST scanner** —
  23 KB that proves the core cannot import `socket`.
- **Nestor's cascade over the consent chain, not just over answers.** A grant is
  *sealed* only when a named human signed it; anything the system inferred is
  *draft* and never acted on; a member with no grant on file is *pending* —
  which renders as nothing, not as an empty slot. The third state is what makes
  silent refusal implementable rather than aspirational.

**Gate.** Refusal is invisible: a consented and a non-consented member render
identically to a section leader. Not greyed, not omitted from a list that shows
its length — *no slot exists*. Plus the no-egress scan in CI.

### P3 — Transport: rebuild, don't adopt · needs a cipher

u2u is a reference, not a dependency. Keep the authenticate-then-authorise
ordering, opt-in consent defaults, and REPLY thread correlation. Discard the
rest.

- **Add confidentiality.** u2u is signed plaintext, and `X25519|ChaCha20|AESGCM`
  returns nothing across the entire account. There is no cipher layer to
  borrow — this is genuinely new code and the riskiest thing in the plan.
- Fix the three verified holes: **destination binding** (a NOTE for a third
  party currently dispatches), **replay defence** (the same packet six times
  dispatched six times), **header allowlist** (forged `_denied`/`admin` markers
  reach the handler).
- Identity must not be the network endpoint — DHCP churn on a travel router
  would re-identify every phone and reset consent.
- Yjs for reconciliation. State deltas, not replay; 61 KB against Automerge's
  1,089 KB.
- The sync filter *is* the P1 resolver. Not a second implementation.

**Gate.** The stolen-device test: dump a member's device and prove it contains
one person's data. Then a hostile-peer test — a paired device that has the wifi
password cannot read another device's traffic, replay a packet, or forge a
control header.

### P4 — Shell and the first capability · blocked on the core job

The chassis is settled and partly written: PWA, offline, OPFS, capability seam —
the pattern `quiet-corner` already proves with several themed fronts over one
data layer. **What goes inside it is the one open question** (SOIL
`capability-order`, `open-questions`).

- Schedule and amendments is the strongest default: nothing exists for it
  anywhere in the account, iCal is the wrong internal shape, and schedule
  *changes* are the hard case on tour.
- Score intelligence is sharpened rather than blocked by bandScores — the public
  aggregation is taken, so the pitch is the corps-private half joined to roster
  and rehearsal data (SOIL `bandscores-prior-art`).
- **Ship `dci_scores.db` as the demo fixture.** 176 KB, four complete seasons of
  caption data with no nulls across all twelve sub-caption columns, and a 2026
  season in progress. It makes the app demonstrable on a plane with no network,
  and every screenshot uses real sourced numbers — which matters when the
  audience knows these scores by heart.
- The first screen that earns the meeting is the one the data already supports:
  **what does the cut actually cost.** The 12th-place semifinals cutoff was
  87.425 · 87.088 · 88.075 · 88.275 across 2022–25 — a director reads their own
  margin off that in five seconds, and it needs no member data, no consent
  framework and no board approval.
- GROVE tokens from `safe-design` throughout, aliases wired as `var()`
  references so they cannot drift.

**Gate.** Works fully offline after first load, on a Chromebook, from a static
host. Not `file://` — that is dead: null origin kills fetch, WASM, modules and
OPFS alike.

### P5 — Acoustics: measured, then validated · headline is ASSUMED

The engine is done and lives in [`field-acoustics`][fa]: 25.8 ms/set, a 100-set
show in 2.6 s single-threaded, agreeing with the Python reference to 5.0e-13 dB
in literal mode. The physics is the weak part, and it says so itself.

- **Load BYU directivity** (CC BY 4.0 — trumpet, tuba, euphonium, flute).
  Replaces the rear front-to-back array, which is currently asserted and is the
  single most load-bearing input in the model. The flute also pulls woodwinds
  forward from P4.
- Facing is an *independent variable you set*, not a datum you recover — the
  counterfactual needs coordinates only, and those import reliably.
  Travel-direction inference stays rejected: its errors are
  ensemble-correlated and do not average away.
- Reimplement the Pyware coordinate grammar. Never vendor the AGPL source it was
  read from.

**Gate.** Field measurement against two or three real programs, published
including where the model missed, before any number goes to a caption head.
Until then the provenance report says ASSUMED and the product says so too.

---

## Not building — and why that is a feature

- **Safeguarding intake.** Route and explain rights; never receive. There are
  already up to four front doors and a fifth leading nowhere authoritative makes
  things worse. What software could genuinely add is a tamper-evident record of
  *when notice was received*.
- **Anything that scores.** Effect is 40 of 100 points and nothing instruments
  it. The circuit decides whether this tool exists at their shows; a tool read as
  coming for judges' jobs gets banned, and then nothing else matters.
- **Realized-position capture leaving the corps.** Kept, inward-only, with no
  export path rather than a disabled one — and framed as rehearsal language,
  never as a tick count that maps onto a sheet.
- **Ranked peer data, anywhere.** Not hidden from students. Absent from the
  product.

---

## Still open, and what each one blocks

- **The core job.** Blocks P4 and nothing else — which is why P1 through P3 are
  the right place to start regardless.
- **Nestor: adopt or lift.** Re-vocabularise the store behind the same `Storage`
  protocol, or fork the mechanic and let Nestor stay Nestor. Cheap either way;
  worth deciding before P1 opens the connection, because that choice is what P1
  hands it. SOIL `nestor-adopt-or-lift`.
- **Guardians are never on the corps LAN.** They're at home, several hundred
  miles away, and guardian access is a requirement. This is the one place a
  server may be unavoidable, and it should be scoped deliberately rather than
  discovered.
- **High school programs go home at six.** The LAN model fits a corps that lives
  together for seventy days far better than a band that rehearses for three
  hours. The stated market is all marching programs. Worth colliding with before
  P3 hardens.
- **Whether the retaliation norm is live.** A written rule against derogatory
  speech about member organisations, enforced in about 24 hours. If that is
  still operative, any reporting affordance is decorative.
- **Counsel before anything touches L5**, and before L4 leaves the device.

---

## Process changes

- **Fail CI on UNKNOWN licences, not only known-bad ones.** Neither
  `@triplit/db` nor `merkletreejs` trips a conventional deny-list — the first
  declares nothing, the second declares MIT in a format scanners cannot parse.
  Five things believed permissive were not.
- **Overlapping passes on anything sensitive.** The naming violation was caught
  by a second agent working the same file — not by the agent that made it. The
  redundancy that looked wasteful was the control.
- **Corrections land beside the record, never on top of it.** Four SOIL records
  exist only to correct an earlier one — `findings-facing-not-a-gate` against
  `facing-capture-risk`, `sync-lan-is-not-trusted` against `sync-lan-hub`. Both
  halves stay live. A decision log that quietly overwrites its own mistakes
  cannot be used to check whether the reasoning was sound, only to confirm that
  the current answer is the current answer.
