# Convention — seams for pinned cross-org dependencies

*How an app consumes a pinned dependency from another face without the
dependency becoming the subject of the work.*

**Applies to:** `nestor`, `willow-gate`, `vault-paths`, `terpsi-core`, and
anything else pinned across an org boundary under the Möbius rule *depend on
contracts, not apps*.

---

## The failure this prevents

When a large, coherent dependency is imported, work drifts onto **it** instead
of onto **how the app uses it**. This is observed, not hypothetical, and it is
worth understanding rather than just forbidding.

- **The dependency is more interesting than the integration.** Nestor is the
  brain — seal, passage, entity resolution, verification, a whole theory. The
  actual task ("call `resolve()` here, store the result there, translate the
  error") is dull beside it. Attention flows uphill toward the interesting
  system, and the central ones are *designed* to be interesting.
- **Imported code reads as territory.** Once it is in the import graph, a reader
  exploring the tree treats it as in scope: reads it, forms opinions, finds
  improvements, proposes changes. Nothing in the code says "this lives in
  someone else's repo and changes belong upstream."
- **The general abstraction pulls.** The dependency is fleet-wide; this app is
  one consumer. Reasoning "correctly" tends toward *this really belongs in
  Nestor* — and app logic starts migrating across a repo boundary.
- **Vocabulary colonizes.** *Seal. Passage. Resolve.* Evocative words arrive
  carrying a worldview, and soon the app describes itself in the dependency's
  terms instead of its own domain's.

That last one is the same mechanism that took *Homestead · Sovereign* from
"you work it yourself" to "settler order without a county" in four individually
plausible steps (see [`docs/homestead-affairs-face.md`](../homestead-affairs-face.md)).
A word arrives carrying more than it says. The cure is the same: make the
boundary explicit **before** the drift, not after.

---

## The rules

### 1. One seam file, and only one

A single module is the **only** place the dependency is imported. Everything
else imports from the seam.

```
homestead/keep/nestor_seam.py     ← the only `import nestor` in the tree
homestead/keep/*.py               ← import from .nestor_seam
homestead_law/**                  ← never sees nestor at all
```

`grep -rn "import nestor" .` should return exactly one file. That is a
one-command check anybody can run, and it means a reader working on any other
file never encounters the dependency at all.

**Precedent in this repo:** `apps/law-gazelle/gazelle_paths.py` is already this
shape for `vault_paths` — one module owns the import and re-exports what the app
needs.

### 2. The contract is a list of calls, written down

Not *"we depend on Nestor."* Instead, at the top of the seam file:

```python
"""nestor_seam.py — the only place this app touches Nestor.

Taken from nestor (pinned: v1.4.2):
  seal(record) -> Seal          attest a verified fact, locally
  verify(seal) -> bool          check a seal we hold
  resolve(entities, store=...)  entity resolution over an INJECTED store

Not taken: passage, promote gates, the matcher.
Nestor is a pinned dependency. Do not modify it, do not propose changes to
it, and do not move app logic into it. If Nestor needs a change, that is an
issue on Nestor's own repo.
"""
```

Three lines of surface is a boundary that cannot be drifted past without
noticing. This is the Möbius *depend on contracts, not apps* rule made concrete
at file level instead of org level — and the **Not taken** line matters as much
as the taken ones, because it says the omissions are deliberate.

### 3. Pin a tag; never vendor

Every cross-org dependency is a tag or sha, never `@master` on anything that
ships. And the source does not enter the tree.

The supply-chain reason is already stated in the fleet rules. The stronger
reason is this: **vendored source gets read and edited; a pinned wheel in
`site-packages` does not.** Physical distance is the cheapest discipline
available.

### 4. Don't let the vocabulary leak

The app speaks its own domain — matters, deadlines, evidence, verification. The
dependency's words stop at the seam, and the seam translates.

Keep the dependency's term where the concept genuinely belongs to it. Rename
where the app already has a word. The test is whether the app's **domain model**
is being renamed to match a dependency; if so, the seam is failing.

### 5. Say it in the boot documentation

One line where an agent will read it before touching anything:

> *`nestor` is a pinned dependency consumed only through
> `homestead/keep/nestor_seam.py`. Do not modify it, propose changes to it, or
> generalize app logic into it. Upstream changes are issues on its own repo.*

Costs nothing. Addresses the behaviour directly, at the moment it would occur.

---

## The enforcing test — deferred, and why it is the real answer

The four rules above are things a person has to remember, which means they are
enforced against whoever is tired and in a hurry — exactly when they fail. The
durable version is a test:

```
tests/test_<dep>_seam.py
  - only the declared seam file imports the dependency (AST, not grep)
  - only the declared symbols are used
  - the pin is a tag or sha, never a branch
```

That is the same move as `verified_by != author` in
[`stores/promote_check.py`](../../stores/promote_check.py): it turns a norm a
person remembers into a mechanism. The repo already runs this class of
invariant in CI — `tests/test_no_raw_soil_reads.py`,
`tests/test_no_inline_vault_root.py`, `tests/test_no_unauthenticated_bind.py`
are all AST-or-grep rules enforced by `store-ci.yml`, and
`promote_check.py` already carries the AST machinery to walk top-level imports.

**Deferred by decision (2026-08-04):** written when there is an actual seam to
guard, not before. A test asserting facts about a file that does not exist is
scaffolding, not enforcement.

---

## Order of work

When a pinned dependency is brought in, **the seam and its contract come
first** — before any call site exists. Build the boundary before there is
anything to drift across.

1. Create the seam file with its contract docstring, importing nothing yet.
2. Add the line to the boot documentation.
3. Add the first call, through the seam.
4. Add the enforcing test once the seam is real.

---

## Related

- [`docs/die-rules.md`](../die-rules.md) — seats and roots at die altitude
- [`docs/homestead-affairs-face.md`](../homestead-affairs-face.md) — the naming slide this generalizes
- [`stores/promote_check.py`](../../stores/promote_check.py) — `inversion [M]`, and the AST machinery a seam test would reuse

ΔΣ=42
