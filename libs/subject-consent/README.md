# subject-consent

The stdlib-only, egress-free **guardian-consent primitive**: *did this person — or
a guardian on their behalf — agree to their data being used this way?*

It answers a question no ordinary authorization surface can. Capability gates ask
*may this app do X?* Owner-consent switches ask *does the operator permit the
system to do X?* Both are about the **owner** and the **app**. Neither can
represent a third party — **the person the data is *about*, when that person is
not the operator** (a co-parent, a child, an ex-partner, a student).

This package is that missing axis, extracted as a shared dependency so three
consumers depend on one primitive instead of each carrying a copy:

- **willow-mcp** — a thin binding wires it into the manifest gate + ReceiptLog.
- **UTETY** — the reference implementation; runs on a child's device (COPPA:
  verifiable *guardian* consent for an under-13 subject).
- **corpus-lens** — its quarantined `person_inference` capability.

It was named "the biggest unshipped gap" by corpus-lens and refused shipment
there; it is the same gap willow-mcp's guardian-consent seam mapped and UTETY
built privately. Built once, here.

## The discipline

Everything is **fail-closed**, exactly like a well-behaved consent reader:
absence, unparseability, a broken hash chain, `pending`, or `revoked` all resolve
to **denied**. *Absence is not consent.*

Three mechanisms:

1. **The consent gate** — `permitted(store, subject_id, scope) -> bool`, read-only.
   True only when the latest transition for `(subject_id, scope)` is a *verified*
   `granted`. Scopes are **independent permissions, not a ladder**
   (`local_only`, `process_analysis`, `kb_promotion`, `person_inference`).
   Mutation (`grant` / `revoke`) is a library primitive an operator CLI calls — an
   app can never grant consent on a subject's behalf.
2. **De-identify-or-refuse** — `deidentify(text, identifiers)` removes each
   identifier and then *proves* the scrub, raising if any survives — and the error
   **never carries the surviving value**. *Identified is person; de-identified is
   process.*
3. **The disclosure chain** — a per-subject, hash-chained, append-only record of
   what was done with a subject's data (the record a guardian can read), detecting
   both mid-chain edits and tail truncation. Revocation is a logged transition,
   never an erasure.

## Zero dependencies, by charter

The core imports **nothing but the standard library** — no network stack, no FFI,
no third-party. `tests/test_boundaries.py` enforces it with an AST walk over the
whole package (mirroring UTETY's own boundary test), so a child-device consumer
and a stdlib-only-charter consumer can both depend on it without dragging a
runtime in behind them.

```python
from subject_consent import grant, permitted, deidentify, record_disclosure

grant(store, subject_id="s1", scope="kb_promotion", granted_by="guardian")
permitted(store, "s1", "kb_promotion")            # -> True (verified grant)
deidentify("Alex went home", ["Alex"])            # -> "████ went home" (or raises)
```

`store` is a directory holding two append-only, hash-chained JSONL files
(`consent.jsonl` + `disclosures/<hash>.jsonl`). The package does **not** decide
who the owner is, judge capacity/self-consent, or expose an MCP surface — those
belong to the binding that consumes it.

## What lives in the binding, not here (on purpose)

- **owner == subject** is not special-cased — the core doesn't know who the owner
  is; a binding that does may exempt that case.
- **capacity / self-consent policy** (age, capability to consent) is deferred.
- **the mutation seat** — enforcing that only an operator (never an app) may
  `grant`/`revoke` is the binding's job; the core only records grants.

## Tests

```
pip install -e .
pytest            # core semantics + the stdlib-only boundary
```

MIT licensed.
