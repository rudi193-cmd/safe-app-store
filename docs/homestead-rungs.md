# The homestead rung model — `L1`–`L5`

*How much of a household's own record may be rendered, on which surface, and
what it takes to see the datum instead of the instruction.*

**Drafted 2026-08-04.** Destination: `homestead.keep`. This is what
`workflow._fact_blocked` becomes.

---

## Provenance, and a loop worth naming

Adapted from **`terpsi-music/docs/SENSITIVITY.md`**, which is the mature
worked version of this idea — five rungs, `max` composition, fail-closed
absence, and the principle that carries the whole thing.

That document says of its own crossing table:

> *"It is written in the shape of `law-gazelle`'s permission table (§7.2), which
> is the fleet's worked example of the same crossing."*

So the influence already runs both ways. Law Gazelle supplied the shape of the
trust crossing; Terpsi built the sensitivity half on top of it. **This is
collecting on a loan, not borrowing from a stranger.**

**What does not transfer.** Terpsi serves six populations across an untrusted
relay, so most of its apparatus is about *entitlement edges between people* —
`guardian_of`, `judge_at`, `staff_of`. A household has one operator, no relay,
and no untrusted server. Those edges mostly collapse, and `L2` nearly empties.

**What replaces them: surfaces.** For a household the question is almost never
*which person may see this* — the operator holds everything. It is **what
crosses a boundary**. So this ladder is scored against surfaces, not principals.

---

## The four surfaces

Every render happens on exactly one of these, and the rung is scored against it.

| # | Surface | What it is |
|---|---|---|
| **S1** | **The operator's own screen** | The TUI, on their machine, in front of them |
| **S2** | **A model prompt** | Anything placed in a local LLM's context window |
| **S3** | **Agent retrieval** | The MCP surface — `gazelle_detail`, `gazelle_briefing`, and friends |
| **S4** | **Egress** | Drafts, exports, filings, commit manifests — anything that leaves |

**S2 is a rendering.** This is the point most easily missed and the one with the
most consequence. A prompt is not "internal processing"; it is a surface with a
reader, and the reader summarizes, retains in a cache, and produces text a human
will act on. Under this model `intelligence.py` is a rendering path and is
governed like one.

---

## The five rungs

Higher is **more restricted**. This runs opposite to WillowGate's
`Rookie → Steady → Veteran` trust, where higher is more privileged. That
opposition is deliberate and is not to be reconciled — see *Never a bare
integer*.

### `L1` — Public

Already public, or publishable, in this matter's own forum. Survives being read
aloud in a hallway.

> *Worked example.* `Hearing · Aug 15 · 8:30 am · Dept 3 · County Courthouse.`

> **The rung is a property of the field in its jurisdiction, not of the data
> type.** A bankruptcy docket is a public record; a family-court file is
> commonly sealed. The *same* field — a case number — is `L1` in one matter and
> `L3` in another. Anything that classifies by column name alone is wrong.

### `L2` — Household

Renderable on any household surface without a purpose. Carries no person's
identity and no protected category. Counts, schedules, operational state.

> *Worked example.* `4 items due this week · 1 overdue · 2 drafts unsent.`

> **The re-identification check is the whole of it, and it bites harder here
> than at Terpsi's scale.** "One matter has an overdue medical response," over a
> household with three matters, names the workers' comp matter immediately. An
> aggregate is `L2` only after a check that it cannot be resolved; until it
> passes it inherits the `max` of its inputs.

### `L3` — Attributed

Names or resolves to a person — the operator, a child, the other party, a
creditor, an employer, a witness.

Rendered in full on **S1**. On **S2/S3/S4** it is `NULL` and a derived form is
served in its place, unless an explicit act says otherwise.

> *Worked example.* `Parenting time · Tue/Thu · minor child A.R.` The operator
> sees it. The model prompt gets *"a recurring parenting-time obligation on
> Tue/Thu."*

### `L4` — Protected

Identifies a person **and** carries a category the law follows. Health, money,
discipline, likeness are the familiar four; here they also include **minors'
data**, **substance-use records** (42 CFR Part 2), **immigration status**, and
**privileged communications**. The four are examples of the clause, not the
whole of it.

**The derived instruction is the normal serving mode — on every surface,
including S1 — and the payload is the exception**, requiring a declared purpose.

> *Worked example.* The workers' comp file holds: *"IME 2026-06-14: L4–L5 disc
> herniation, 12% whole-person impairment, permanent lifting restriction 20 lb."*
>
> What Today renders is *"Medical records response due Aug 15 — 11 days."* The
> operator can act. The diagnosis is not on the Today screen, not in the Ollama
> prompt, and not in the MCP briefing. Opening the record under a declared
> medical purpose serves the payload; the same operator, ten minutes earlier
> under a deadline purpose, gets the instruction.

> **This is the rung that makes the ladder worth having.** `L4` is not "`L3` but
> more so." It is the claim that most of what a household needs to *do* about a
> sensitive category is satisfied by an instruction rather than the datum, and
> that serving the datum is a decision requiring its own reason. *A design that
> renders the diagnosis to every surface that might need to act on it has not
> classified anything; it has added a label to a leak.*

### `L5` — Sealed

Rendering it would reveal a refusal, expose privileged strategy, disclose key
material, or breach a sealing order. **Never served on any surface**, including
to the operator's own agents.

Includes: any fact the operator marked **`do_not_use`**, and why; the content of
a sealed record; export-ledger key material; anything under a protective order.

---

## Class → rung, for the three matter types

Illustrative, not exhaustive; the procedure below governs.

| Matter | Field | Rung | Why |
|---|---|---|---|
| **Custody** | Hearing date, courthouse, department | `L1` | Calendar, publicly posted |
| | Case number | `L3` | Family records commonly sealed — **not** `L1` |
| | Parenting schedule | `L3` | Resolves to the child |
| | Child's name, DOB, school | `L4` | Identifies a minor |
| | Guardian ad litem report, counseling records | `L4` | Health / discipline |
| | Substance-use treatment records | `L5` | 42 CFR Part 2 re-disclosure rules |
| | Allegations under a protective order | `L5` | Sealing order |
| **Bankruptcy** | Chapter, filing date, 341 date, case number | `L1` | Bankruptcy dockets are public |
| | Creditor names and amounts | `L4` | Money category, identifies |
| | Means-test income, schedules I/J | `L4` | Money category |
| | SSN, account numbers | `L5` | Key material |
| **Workers' comp** | Claim number, carrier, employer | `L3` | Identifies |
| | Injury description, IME, treatment, impairment rating | `L4` | Health |
| | Prescription and substance-use treatment | `L5` | 42 CFR Part 2 |

---

## Classifying a new field

1. **Is it public in this matter's forum?** → `L1`.
2. **Does it name, or resolve to, a person?** No → `L2`. Yes → continue.
   **2a. Is it derived?** `L2` applies only *after* the re-identification check;
   until it passes, it inherits the `max` of its inputs.
3. **Does it carry a category the law follows?** No → `L3`. Yes → `L4`.
4. **Would rendering it reveal a refusal, expose privileged strategy, disclose
   key material, or breach a sealing order?** → `L5`.
5. **Record the matter type and jurisdiction alongside the rung.** Step 1
   depends on both, and neither is derivable from the field name.

**Step 4 runs last and overrides.** A field can be `L3` by step 2 and still land
at `L5` because rendering it would identify who refused.

---

## Rules that travel

**Composition is `max`, everywhere.** A record is the `max` of its fields. A
chronology is the `max` of its events. A draft is the `max` of every fact it
cites. **A model prompt is the `max` of everything in its context window** — and
that includes the retrieved neighbours a semantic search pulled in. A projection
never lowers a rung. Only an explicit, dated, sealed declassification does.

**Never a bare integer.** `L3`, not `3`. `if level >= 3` is correct against this
scale and **catastrophic** against WillowGate trust, which runs the other
direction — and it reads perfectly in review either way. The rung is a string
with its prefix, always.

**Absence fails closed, twice over.** An unclassified field is a **build
failure**, not a default. If one reaches runtime unclassified anyway it reads
`L5` and is not served. A classifier that errors returns `unknown` and denies —
never `L1`.

**Declassification is an act with a name and a date**, recorded in the ledger
`homestead.keep` already binds (see `docs/drafts/nestor_seam.py`). No rung falls
by inertia, on a schedule, or as a side effect of aggregation.

**Time does not declassify.** A closed matter's medical records stay `L4`. A
child turning eighteen changes who may hold the file, not what the data is.

---

## Crossing to trust

The mapping from a rung to what it takes to serve it lives here and nowhere
else. Trust tiers are WillowGate's existing `Rookie / Steady / Veteran`.

| Rung | S1 · operator screen | S2 · model prompt | S3 · agent (MCP) | S4 · egress |
|---|---|---|---|---|
| `L1` | render | render | render, ≥ Rookie | render |
| `L2` | render | render | render, ≥ Rookie | render |
| `L3` | render | **derived** | **derived**, ≥ Steady | explicit act, ledgered |
| `L4` | **derived** unless purpose | **derived**, no exception | **derived**, ≥ Veteran + purpose | explicit act + purpose + ledgered |
| `L5` | **never** | **never** | **never** | **never** |

Two deliberate hard stops. **`L4` never reaches a model prompt as a payload** —
if a local model needs the diagnosis to do its job, that is a signal the job is
wrong, not that the rung should bend. And **`L5` has no override anywhere**; a
rung with an escape hatch is a label, not a control.

---

## What this replaces, and two bugs it makes unrepresentable

`workflow._fact_blocked` is a single boolean over one status value. It becomes
`(rung, surface, purpose) → render | derive | deny`.

- **BUG-5 disappears structurally.** A fact marked `do_not_use` is `L5`, and
  `L5` is never served on any surface. The current defect — `_fact_blocked`
  checks only `needs_source`, so the *stronger* rejection is the one that
  doesn't work, while the UI says "Excluded from drafting" — cannot be written
  under this model.
- **BUG-6 likewise, under E-4.** A registry that iterates its matter types
  cannot silently omit workers' comp.

That is the pattern worth noticing: **the right model makes the bug
unrepresentable**, rather than making it a thing tests must catch.

---

## Open

- **Does the operator get the derived form on their own screen at `L4`?** Drafted
  as yes-unless-purpose. Terpsi caps the subject at `L4` for a reason (W-4: a
  ward may request, never authorize), but a household operator is both subject
  and principal, so the argument does not carry over unchanged. This is the one
  rung decision that most affects daily use.
- **What is a purpose declaration worth when the only principal is the
  operator?** Weaker than a guardian's, but still an intentional act that can be
  ledgered — which is most of its value.
- **Where does classification live?** Schema-definition time, with a manifest
  and a test that fails the build on an unclassified field. Not written.
- **D2 re-introduces entitlement edges.** A clinic operating for clients brings
  back `guardian_of`-shaped questions and a client dimension the sidecar does
  not have. Deferred; Terpsi's model is the reference when it lands.

---

## Related

- `terpsi-music/docs/SENSITIVITY.md` — the mature version, and where this came from
- [`docs/homestead-affairs-face.md`](homestead-affairs-face.md) — the face this serves
- [`docs/drafts/nestor_seam.py`](drafts/nestor_seam.py) — the ledger a declassification is recorded in
- [`apps/law-gazelle/docs/bug_list.md`](../apps/law-gazelle/docs/bug_list.md) — BUG-5, BUG-6
- [`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md) · [`_intl.md`](../apps/law-gazelle/docs/legal_obligations_intl.md) — 42 CFR Part 2, GDPR Art. 9, ABA Formal Op. 512

ΔΣ=42
