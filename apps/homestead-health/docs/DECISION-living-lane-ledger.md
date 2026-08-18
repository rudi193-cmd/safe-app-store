# Decision — the living lane's ledger: keep's `IntegrityLog` suffices

**Proposed 2026-08-18, `verified_by ≠ author`** — drafted while building bite 7,
awaiting a person's seal, the same posture as the extension plan it answers.

## The question this closes

`PLAN-homestead-health.md`'s extension left one thing open **as a check, not a
design decision** (§ "Open — added by this extension"):

> **Does `keep`'s `IntegrityLog` suffice for the living lane?** … whether
> `IntegrityLog` covers the living lane's needs as it stands, or wants something
> Nestor's ledger carries and it does not — the supersede model, or the
> encryption `logs.py` defers to Phase 4. **Bring in `rudi193-cmd/Nestor` and read
> its ledger when the bite lands; do not presume the answer here.**

This is the read, and the answer.

## What Nestor's ledger actually is

`nestor/ledger.py` and `nestor/cascade.py::ledger_append`, read directly:

- **The same hash chain.** Each line's `prev` is the SHA-256 of the whole
  previous line, rooted at `"genesis"`; `head()` returns the tip; `verify()`
  walks the chain and takes an `expected_head` to close the last-line gap "for a
  caller who kept it somewhere the ledger's writer cannot reach." That is
  `keep/logs.py::IntegrityLog`, line for line — including the off-tree-anchor
  reasoning (Nestor calls the external form `nestor.frank`; keep calls it
  `anchors_dir()`), and including the concurrency lock whose docstring keep's own
  cites by name.
- **A supersede model — that is a `kind`-tagged append.** Nestor carries a
  closed `LEDGER_KINDS` set (`supersede`, `seal_replaced`, `baseline_replaced`,
  `unseal`, …) and `entries(kind=…)` filters on it; when a seal is replaced "the
  previous target and verifier survive *only* here." There is **no supersede
  primitive** beyond that — a replacement is an ordinary appended line whose
  `kind` says what boundary was crossed, and the prior is gone from the live
  store but recoverable-as-a-hash from the chain. `keep`'s
  `IntegrityLog.append(dict)` takes an arbitrary entry, so it carries exactly
  this shape: a `{"kind": "living_replaced", …}` line is a supersede record.
- **No encryption.** Nestor's ledger is plaintext JSON hashed over plaintext,
  same as keep's. Nestor's *seals* are asymmetrically signed; the *ledger* is
  not encrypted. So "the encryption `logs.py` defers to Phase 4" is not something
  Nestor's ledger carries and keep's does not — neither encrypts.

## The answer

**`keep`'s `IntegrityLog` suffices for the living lane, as it stands.** The two
things the Open note wondered Nestor might carry, it does not:

- **The supersede model** is a kind-tagged append, and `IntegrityLog.append`
  already does that. The living lane records each replacement as a
  `living_replaced` line carrying the **thing's** ref and the **SHA-256 of the
  replaced value** — a hash commits to the prior without keeping it readable,
  which is the inverse of bite 5's *verify-catches-an-edit* and exactly what a
  forgetting cell needs. `verify(expected_head=…)` against an off-machine head
  proves the sequence un-forged.
- **Encryption is not needed.** The lane keeps *hashes* of priors in the ledger,
  never the priors, so there is nothing readable in the audit to encrypt. The
  latest value lives in the cell as `L5` with no egress path — the same posture
  keep already takes for any `L5` datum, whose encryption-at-rest is the shared
  Phase 4 item, not a living-lane-specific one.

So the living lane is what the plan said: **one small new primitive (the
forgetting cell) plus keep's ledger reused as it stands.** No engine change to
`IntegrityLog`.

## The one gap the check *did* find — `VisibleLog`, not `IntegrityLog`

The plan's *done when* names "a `VisibleLog` event" for the operator-visible
motion. `keep`'s `VisibleLog.record` takes an `Event` **enum member**, and the
enum is **closed** (R-7: so argument one cannot become the free-text field a note
leaked through). It has no living-replaced member, and widening it is a change to
the pinned engine this app must not make.

The resolution keeps the app on the right side of the engine wall: **the living
lane's audit uses the `IntegrityLog` alone.** That log is already content-free by
construction for this lane (refs and hashes, never a value), so it serves both
roles — the provable record *and* the operator-visible "this cell was replaced N
times, in order, un-forged," read back by filtering the chain on the thing. Using
a *fitting* existing `Event` would be right; there is none, and bending
`RECORD_SYNCED` ("a record was stored") to mean "a value was forgotten" would be
the mislabelling the closed enum exists to prevent — worse than one log.

An engine issue is filed proposing a `LIVING_REPLACED` `Event` member, so a
future engine version can also surface the motion in the operator's ordinary
activity feed. Until then the `IntegrityLog` carries it, and nothing is lost:
the audit is provable, content-free, and readable.

## What this decision does not do

- **Does not touch `homestead.keep`.** The finding is that it needs no change for
  this lane; the one proposed change (`LIVING_REPLACED`) is filed upstream, not
  made here.
- **Does not build the reference lane (bite 6).** That is the reader-over-a-corpus
  half of the extension, with its own open provenance question; out of scope.
- **Does not ratify itself.** Proposed; a verifier who is not the author seals it.
