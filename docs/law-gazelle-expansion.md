# Law Gazelle — Expansion

*Where this app can go, what each direction actually requires, and the tension
nobody has written down yet. Companion to
[`apps/law-gazelle/docs/finish_list.md`](../apps/law-gazelle/docs/finish_list.md),
which tracks the work; this tracks the **direction**.*

**Written:** 2026-08-04

---

## Where expansion is currently discussed

It is discussed in five places that do not cite each other. That is the first
problem — not that the thinking is missing, but that it is scattered, and the
pieces disagree.

| Source | What it says about this app |
|---|---|
| [`apps/law-gazelle/MISSION.md`](../apps/law-gazelle/MISSION.md) | An **access-to-justice product**. Wedge: self-represented parents in custody matters. Channel: legal aid orgs, court self-help centers, law school clinics. Path: pilot partner → docassemble intake → fiscal sponsorship and grants. Nonprofit posture, MIT, built in public. |
| [`VISION.md`](../VISION.md) §Pattern 2 | A **verification surface** in the constellation: "verify a case citation" → teaches "legal accuracy; reviewer trust," feeding SRS review and calibration weight. |
| [`docs/app_store_vision_and_gaps.md`](app_store_vision_and_gaps.md) §1, §6 | A **"personal command center," ~85%, `coming_soon`** — and in the per-app decision, **"Support/keep."** Explicitly *not* a flagship; the flagships are story-timeline, ask-jeles, the-binder, private-ledger. |
| [`docs/willow-compatible-projects.md`](willow-compatible-projects.md) | A **consumer of companion tools** — visidata and sqlit are named as natural pairings for the SQLite data it produces. |
| [`docs/the-self-portrait.md`](the-self-portrait.md) | Nothing. The constellation essay — "every app is an organ; there is one bloodstream" — does not mention it. See [The organ with no outflow](#the-organ-with-no-outflow); that omission turns out to be structural, not an oversight. |

---

## The tension we should name

`app_store_vision_and_gaps.md` §4 named the repo's central tension — two
products in one repo — and resolved it by choosing **A3, sovereign-first**.
This app has its own version of that tension, one layer down, and it has not
been named or resolved.

|  | **A — Personal instrument** | **B — Access-to-justice product** |
|---|---|---|
| Source | `app_store_vision_and_gaps.md`, `VISION.md` | `MISSION.md` |
| Who it serves | **you**, on your machine | **strangers**, through institutions |
| Success metric | your three matters stay on top of you | a pilot org adopts it; litigants don't miss deadlines |
| Resourcing verdict | **"Support/keep"** — not a flagship | pilot, then *"the biggest build"* (intake), then grants |
| Data | your own | **other people's PII**, at clinic scale |
| Funding | none needed | fiscal sponsorship, state bar foundations, ATJ commissions, LSC TIG |

**These are not the same product, and the repo currently asserts both.**

Three specific collisions:

**1. The thesis tie-breaker excludes B.** The store's one-sentence thesis is *"a
sovereign personal operating system — own your data, trust your sources"*, and
its stated tie-breaker for any gap is: *does it help **a person** own and trust
**their own** data on **their own** machine?* MISSION's expansion is about
serving people who are not you, through organizations, on machines that are not
yours. It is a good goal. It is not the goal the tie-breaker selects for, so it
will lose every resourcing argument it enters while that tie-breaker stands.

**2. "Support/keep" and "the biggest build" cannot both be true.** §6 files this
app under support/keep — maintain, don't grow. MISSION step 3 calls the
docassemble intake front end "the biggest build, and the most defensible." One
of those is wrong. Nothing in the repo reconciles them, so today the answer
depends on which document someone happens to open.

**3. Verification-as-learning may not be available to this app at all.** See
below — this is the interesting one.

### The organ with no outflow

`VISION.md` Pattern 2 says every verification event should do three things:
improve the corpus, fire an SRS review for the verifier, and adjust the
verifier's calibration weight. The table assigns law-gazelle a row: verify a
case citation → learn legal accuracy and reviewer trust.

**The first of those three cannot happen here.** The corpus that would learn is
a *shared* one, and case facts are privileged, PII-bearing, and — per this app's
own Principle 1 and MISSION's "what it will never do" — must never leave the
device. `the-self-portrait.md` describes a constellation where every organ
deposits into one bloodstream and human decisions in any organ improve the
whole. Law Gazelle is the organ that **cannot** deposit. That is presumably why
the self-portrait doesn't mention it.

So one of these must give:

- **Calibration-only participation** — the verifier's SRS event and calibration
  weight are local artifacts and can fire without emitting anything. The corpus
  contribution is simply skipped for this app. Pattern 2 becomes two-thirds of
  itself here, deliberately.
- **Pattern 2 doesn't apply**, and `VISION.md`'s table should say so rather than
  implying a data flow that the app's own principles forbid.

Calibration-only is the right answer, and it is worth writing into `VISION.md`
explicitly — because a table row that implies case data feeds a shared corpus is
the kind of thing a legal aid partner reads once and stops the conversation
over.

### The repo already contains the resolution

Worth noticing: the promotion bar in [`stores/README.md`](../stores/README.md)
requires *"a semantic-search seam over its own **injectable** knowledge — ship
the reader; the corpus stays with whoever grew it."*

That is precisely the architecture this app needs, arrived at independently for
different reasons. The capability travels; the case data never does. **The
store's own promotion bar is the answer to the constellation question**, which
means finish-list item **D-1** (build the semantic-search seam) is not just gate
paperwork — it's the structural move that lets this app participate in the
constellation without violating its own first principle.

---

## Directions

Ordered by distance from what exists today. Each is a real option; **none is
chosen here.**

### E1 — Deepen for user #1

Honor the "support/keep" verdict. Finish Track B of the finish list (PDF sync,
remaining tables), keep it excellent for three matters, expand no further.

- **Requires:** nothing new. This is the current trajectory.
- **Cost:** MISSION becomes aspirational rather than operative, and should be
  relabeled so it doesn't read as a commitment.

### E2 — Generalize the matter types

Today `MATTER_NAV` hardcodes exactly three matters — coparent, bankruptcy,
workers_comp — and `case_store` carries matching per-matter functions
(`load_coparent_meta()`, `bankruptcy_overview()`, `workers_comp_overview()`,
`schedule_response_packet()`). There is no matter-type seam; the three are
compiled in.

**This is the technical prerequisite for any second user**, whatever the
destination. A matter type should be a registered descriptor — tables, item
types, deadline rules, detail renderers — not a branch in the navigation table.

- **Requires:** a matter-type registry, and a migration of the three existing
  types onto it. Sizeable, but purely internal and testable on synthetic data.
- **Unlocks:** E3 and E4 both. Neither is reachable without it.

### E3 — Guided intake

MISSION step 3: a docassemble-integrated interview that turns a shoebox of
documents into a structured, human-confirmed case file. Called "the biggest
build, and the most defensible," and that judgment looks right — intake is where
self-represented litigants actually fail, and it is the part hardest to copy.

- **Requires:** E2 first. Plus a real integration decision — docassemble is a
  server-side Python stack, which sits awkwardly against "no server, no
  account." Embedding an interview engine locally is a different project from
  integrating a hosted one.
- **Watch:** this is the point where "local-first" gets tested for real.

### E4 — Advocate-assisted deployment

MISSION's stated channel: a legal aid org or clinic runs it on behalf of
clients.

This is the largest change and it is **not primarily a code change.** It moves
the app from *your data on your machine* to *other people's data on an
advocate's machine*, which changes:

- **The data model** — multi-client, multi-matter, per-client isolation. The
  sidecar keys on `(source_db, item_type, item_id)` with no client dimension.
- **The consent posture** — the subject of the data is no longer the operator.
  The manifest's `privacy_tier: client_only` describes the wrong relationship
  once the client isn't the user.
- **The liability posture** — breach obligations for someone else's PII, and
  the unauthorized-practice-of-law question. MISSION already guards UPL well
  ("information, not advice"; "does not apply law to facts"), and the
  `_fact_blocked` gate in `workflow.py` implements it rather than merely
  asserting it. At clinic scale that guard stops being a principle and becomes
  a compliance surface someone will ask to see documented.
- **The gate stops being optional** — `GAZELLE_GATE` is off by default today,
  and its 9 tests skip because willow-gate isn't installed. In a multi-client
  deployment the authorization layer is load-bearing and currently unexercised.

- **Requires:** E2, a client dimension throughout the sidecar, the gate on by
  default and actually tested, and a named partner (finish-list **C-5**).

### E5 — Extraction as a reusable library

The promotion path (finish-list Track D): lift it into its own repo with an
import-pure core and an injectable corpus seam.

Two things make this cleaner than it looks. The app already carries **its own
MIT license** inside the Apache-2.0 monorepo, so the license story for
extraction and for a nonprofit/grant posture is already correct. And D-1's
injectable seam is exactly the "ship the reader, not the corpus" shape that both
promotion and access-to-justice distribution need.

- **Requires:** D-1, D-2, D-3, and a verifier who is not the author (§0.2).
- **Note:** E5 is orthogonal to E1–E4 — it improves the architecture regardless
  of which destination is chosen.

### E6 — Constellation participation, calibration-only

Wire Pattern 2's verifier-side halves — SRS review events and calibration
weight — while emitting nothing. `gazelle_state.set_fact_verification()`
already records exactly the human decisions that would fire these, so the event
source exists.

- **Requires:** a local-only calibration sink, and the `VISION.md` correction
  described above.
- **Cost:** small. This is the cheapest way to make the app a real member of the
  constellation without touching its privacy guarantee.

---

## Open questions

1. **Is this app A or B?** Personal instrument, or access-to-justice product?
   Everything else sorts from this. `app_store_vision_and_gaps.md` §4 resolved
   the repo-level version of this question by choosing; this one is still open.
2. **Does "support/keep" survive MISSION?** If B is chosen, §6's per-app
   verdict needs revisiting — support/keep and "the biggest build" are not
   compatible.
3. **Does the thesis tie-breaker need widening?** "Helps a person own and trust
   their own data on their own machine" excludes B by construction. If B is
   chosen, the thesis sentence has to grow a clause, or this app becomes a
   permanent exception to it.
4. **Calibration-only, or Pattern 2 not applicable?** Either is defensible;
   leaving `VISION.md`'s table implying corpus contribution is not.
5. **Who is the pilot partner?** (finish-list **C-5**) — B cannot start without
   one, and E3/E4 sequencing depends on what they actually need.

---

## Related

- [`apps/law-gazelle/docs/finish_list.md`](../apps/law-gazelle/docs/finish_list.md) — the work, across four tracks
- [`apps/law-gazelle/MISSION.md`](../apps/law-gazelle/MISSION.md) — the B story, stated
- [`apps/law-gazelle/docs/law_gazelle_spec.md`](../apps/law-gazelle/docs/law_gazelle_spec.md) — architecture and phase roadmap
- [`docs/app_store_vision_and_gaps.md`](app_store_vision_and_gaps.md) — §4 the repo's central tension, §6 the per-app verdict
- [`VISION.md`](../VISION.md) — Pattern 2, verification as learning
- [`stores/README.md`](../stores/README.md) — the promotion bar, and the injectable-corpus seam

ΔΣ=42
