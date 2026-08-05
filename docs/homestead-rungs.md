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
| **S1** | **The operator's own screen** | The app window, on their machine, in front of them. Two panes with different powers: the **list** (ambient, cannot render an `L4` payload — I-35) and the **detail** (opened deliberately, expires back to derived — I-32). |
| **S2** | **A model prompt** | Anything placed in a local LLM's context window |
| **S3** | **Agent retrieval** | The MCP stdio entry point, invoked as a subprocess. Never a listening port. |
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

Rendered in full on **S1**. On **S3/S4** it is `NULL` and a derived form is
served in its place, unless an explicit act says otherwise. On **S2 there is no
such act** — a name never reaches a model prompt as a payload.

> **Corrected 2026-08-05.** This sentence used to read "S2/S3/S4 … unless an
> explicit act says otherwise", which contradicted the crossing table's flat
> `derived` for `L3 · S2`. Two statements about one cell, in different
> registers — the same defect that put a non-monotone `S3` column in the table,
> and it was found the same way. The table was ruled correct; this sentence is
> the one that has been changed.

> *Worked example.* `Parenting time · Tue/Thu · minor child A.R.` The operator
> sees it. The model prompt gets *"a recurring parenting-time obligation on
> Tue/Thu."*

### `L4` — Protected

Identifies a person **and** carries a category the law follows. Health, money,
discipline, likeness are the familiar four; here they also include **minors'
data**, **substance-use records** (42 CFR Part 2), **immigration status**, and
**privileged communications**. The four are examples of the clause, not the
whole of it.

**The derived instruction is the normal serving mode, and the payload is the
exception.** On S1 that resolves by pane rather than by ceremony: the **list
cannot render a payload at all**, and the **detail pane** serves it when the
user opens it — the act of opening *is* the declaration. On S2 the payload never
appears. On S3 and S4 it requires an explicit purpose.

> *Worked example.* The workers' comp file holds: *"IME 2026-06-14: L4–L5 disc
> herniation, 12% whole-person impairment, permanent lifting restriction 20 lb."*
>
> What Today renders is *"Medical records response due Aug 15 — 11 days."* The
> operator can act. The diagnosis is not on the Today list, not in the local
> model's prompt, and not in the MCP briefing. Opening the record shows it —
> and I-32 puts it away again, because the threat is someone walking past
> thirty seconds later.

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

**A regime does not classify; a datum in a matter does.** Noted here because this
document says `L4` and `L5` about the same material in two places, and the
disagreement has already been read the wrong way once.

**42 CFR Part 2 is named as an `L4` category** in the `L4` clause above —
alongside minors' data, immigration status and privileged communications — and it
is **not** in the `Includes:` list here. That is deliberate. Part 2 is a
disclosure-**consent** regime: it governs who may pass a record on and with whose
permission. It is not a sealing order, and the four clauses `L5` turns on
(reveals a refusal, exposes privileged strategy, discloses key material, breaches
a sealing order) are not what a Part 2 record engages by existing.

The two `L5` rows for substance-use material in the table below are **correct and
should stay.** They are worked instances — a treatment record inside a live
custody or workers' comp matter, where step 4 does apply — and over-classifying
fails closed, which is this model's direction of error. What does **not** follow
is the generalisation: *Part 2 material is `L5`*, therefore an act naming Part 2
re-disclosure can never be performed. Run the procedure instead. Step 3 puts a
substance-use record at `L4` by category; step 4 asks whether serving it breaches
a sealing order, which for a Part 2 record *simpliciter* it does not; step 5 is
the standing refutation of classifying by regime at all — *the same field is `L1`
in a bankruptcy and `L3` in a family matter.*

Recorded because the generalisation was made, against `homestead`'s
`Purpose.REDISCLOSURE`, on the reasoning that its canonical datum is `L5` and
`L5` has no override, so the member was dead. It is not: it is live at `L3` and
`L4` on egress, and four of that enum's members have a canonical `L5` datum they
cannot reach — which is `L5` working rather than a defect in a member.
See `homestead/docs/DECISION-redisclosure.md`.

---

## Class → rung, for the three matter types

Illustrative, not exhaustive; the procedure below governs. **A row here is a
worked instance, not a rule about the category it names** — see the note under
`L5` for what happened when one was read as one.

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
| `L3` | render | **derived** † | **derived**, ≥ Steady; payload on explicit act | explicit act, ledgered |
| `L4` | **derived** unless purpose | **derived**, no exception | **derived**, ≥ Veteran + purpose | explicit act + purpose + ledgered |
| `L5` | **never** | **never** | **never** | **never** |

**The table is monotone, and that is a rule rather than an observation.** No
cell may be stricter than the cell **below** it in the same column: whatever
unlocks a rung on a surface also unlocks every lower rung on that surface. A
cell that omits an unlock a higher rung has is an **error in this table**, not
a denial.

> **Correction, 2026-08-05 — the `S3` column was non-monotone as written, and
> it was caught by an agent implementing from the table alone.**
>
> `L3 · S3` read *"**derived**, ≥ Steady"* with no unlock, while `L4 · S3`
> read *"≥ Veteran + purpose"* — so cell-by-cell the **higher** rung was
> servable where the lower one was not. That is **BUG-5's exact shape**, in
> the normative table, on the surface that is an automated agent with no eyes
> to be walked past.
>
> It was a reading error rather than a real inversion, but only for a reader
> who brings outside knowledge: `L3`'s prose supplies the missing unlock
> ("*unless an explicit act says otherwise*") and the cell did not. Two
> statements in different registers, and one of them **alone** produces the
> inversion — which is what a reader implementing from the table gets. The
> cell now states its own unlock, and the monotonicity rule above makes the
> next omission detectable instead of load-bearing.

† ~~**Open**~~ **Decided 2026-08-05 — the table wins. `L3` never reaches a model
prompt as a payload.** The table said a flat **derived** with no unlock; `L3`'s
prose said `S2/S3/S4` are derived *"unless an explicit act says otherwise."*
Monotonicity did not settle it — `L4 · S2` is a hard stop under either reading.

What an operator loses is narrower than it looks: **drafting is unaffected**,
because `L3 · S4` already permits an explicit ledgered act, so a filed document
can carry a real name. What is refused is *asking the model about a named
person* — and for that the derived form is nearly always enough. A model does
not need `"A.R."` to reason about a Tuesday/Thursday schedule.

**The ruling carries a build item**, and without it the refusal is enforced but
its justification is not yet true: **pseudonymise → reason → re-attach
downstream**. With that path, `L3` never needs to reach `S2` and the cost rounds
to zero. Without it, the cost is real and is being paid in silence. Phase 4/5.

The `L3` prose above is now the one that is wrong; it says `S2` unlocks on an
explicit act and it does not.

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

## A refusal is information at the rung of the thing refused

**Added 2026-08-05**, deciding whether the surface indicator may say `L5
present`. It may not, on an ambient surface — and the reason generalises past
the indicator, which is why it lives here rather than in a decision log.

I-35 says an ambient surface cannot carry an `L4` **payload**. This says it
cannot carry the **fact of an `L5`** either. On a shared machine, *"something is
sealed here"* tells the person behind the chair that a record is being kept from
them, and that is F-1's reader — the whole point of `L5` is that it is never
rendered, and the existence of a sealed thing is rendered by saying so.

On a surface the operator **deliberately opened**, the same disclosure is fine,
by exactly the by-widget logic that settled the `L4` question the day before. So
the rule is not "never say it" but *"say it only where the saying was asked
for."*

`"derived · L4 present"` stays legal on an ambient surface: that an `L4` exists
is not itself protected at `L5`.

---

## Open

- ~~**Does the operator get the derived form on their own screen at `L4`?**~~
  **Decided 2026-08-04 — by widget, not by dialog.** The **list pane cannot
  render an `L4` payload**: its render path does not accept one, so nothing
  sensitive can be ambient even by mistake. The payload exists only in a detail
  pane the user explicitly opened, and **I-32** returns it to derived on
  timeout. The deliberate act of opening **is** the purpose declaration, so
  there is no ceremony tax on a person in crisis. Terpsi caps the subject at
  `L4` because a ward may request but never authorize (W-4); a household
  operator is both subject and principal, so that argument does not carry over
  — but the *surface* distinction does all the work the cap was for.
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
