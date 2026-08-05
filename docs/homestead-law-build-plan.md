# `homestead-law` — build plan

*A fresh build in a new repo. Not a port, not a refactor. Every failure this
session documented is written correctly the first time, and the tests that say
so are written before the code that satisfies them.*

**Drafted 2026-08-04.** Target: `homestead-affairs/homestead-law`, with
`homestead-affairs/homestead` (the seat, holding `homestead.keep`) built first.

> **Phase 0 was audited on 2026-08-04 and does not meet its exit criteria.**
> Two independent passes found the enforcement weaker than this document
> claims. **I-19's wording below states a guarantee its test does not
> deliver** — a `Path(os.environ["HOME"]) / "Desktop" / "Nest"` injection
> passes the suite — and **I-22 claims tamper-evidence the code does not
> provide**. Both are corrected as part of the remediation, not before it, so
> the overclaim stays visible rather than being quietly edited away. See
> `rudi193-cmd/homestead` → `docs/PHASE0-REMEDIATION.md` and `docs/audits/`.
> **Do not read the invariant tables below as enforced.**

**Where they actually live, 2026-08-04.** All three are on **`rudi193-cmd`**,
public, awaiting transfer to the org — the same tier-E workshop pattern the
placement draft already uses for `nestor` ("until transferred to
`Die-Namic-Systems`"). Live now: **`rudi193-cmd/homestead`** (the seat —
**Phase 0 pushed**, 19 passing / 13 xfailed), `rudi193-cmd/homestead-law`,
`rudi193-cmd/homestead-ledger`. Transfer is a placement act, not a build
dependency; nothing in the phases below waits on it.

---

## Why fresh, and what that costs

`apps/law-gazelle` is 9,333 lines carrying 12 known bugs and 8 verified safety
exposures. Two of those defects are **unrepresentable** under the models drafted
this session ([rungs](homestead-rungs.md) kill BUG-5; the matter registry kills
BUG-6), and several others are shape problems rather than logic problems — a
date truncated before parsing, a gate wired to one entry point, a note copied
into a log that feeds a prompt. Those are not patches. They are consequences of
decisions that would have to be unmade.

**What travels: nothing but knowledge.** No copy-paste. Copied code carries
copied defects, and the defects here are in the joins.

**What that costs, honestly.** The 9,333 lines encode real domain work — what a
matter contains, which item types exist, what a chronology needs, how a queue
should rank. That is expensive to re-derive and it should not be thrown away.
Use law-gazelle as a **specification source, read like a document**, not as a
source tree to lift from. `docs/law_gazelle_spec.md` and the detail-type
enumeration in `case_store.py` are the two highest-value reads.

**law-gazelle's ending.** This is the [tombstone
convention](conventions/tombstones.md)'s first real case, and it needs a shape
the convention does not have: not `merged`, not `promoted`, not `retired`.
Propose **`rebuilt`** — *the code does not travel; the knowledge does, and the
successor is named.* Its `carried` list is the bug list, the safety findings,
and the two legal references. The convention predicted the first tombstone would
tell us whether three shapes were enough. It was not.

---

## The shape — self-contained, no listening socket

**Decided 2026-08-04.** Not a TUI, and not HTTP. A **self-contained desktop
application**, plus a separate agent entry point. Neither binds a port.

```
homestead.keep                  the core — record, deadlines, rungs, gate, logs
  ├── homestead-law (the app)   S1 · a window the user double-clicks
  └── homestead-law-mcp         S3 · stdio, invoked as a subprocess by an agent
```

**Why, and it is not a departure.** [`die-rules.md`](die-rules.md) Rule 2 says a
product gets its own root when *someone who does not run the fleet installs it*.
The same test decides the surface: **a self-represented parent does not open a
terminal.** Being the only non-TUI on a die of TUIs is what that rule predicts
for the one face that ships to strangers.

**What it deletes rather than solves.** Terpsi's whole three-zone architecture
exists because guardians *force* a reachable endpoint. A household has no such
constraint, so a self-contained app does not solve the server problem — it
removes it. No port, no bind, no relay. `I-26` stops being a rule to police,
because nothing in the app wants `http.server`.

**MCP survives without HTTP.** MCP is stdio — a subprocess pipe, not a server.
The agent surface is a separate entry point, so `I-16`'s single chokepoint sits
in the core where *both* surfaces cross it. **F-2 happened because law-gazelle
wired its gate to one entry point;** this shape makes that mistake structurally
hard rather than merely forbidden.

**Toolkit: `tkinter`.** Stdlib, zero dependencies, cross-platform, native
widgets via `ttk`, accessibility inherited from the host toolkit. It is the only
option that costs nothing against the dependency posture, and this UI is a list,
a detail pane and a cover — not a complex layout. Rejected: **PyQt** (GPL or
commercial, same exclusion as PyMuPDF); **Electron/Tauri** (heavy, and an extra
security surface on an app holding privileged records). Held in reserve:
**PySide6** — LGPL, so dependency-only and never vendored, a contained swap
*if the surface stayed thin* and a pilot partner says the look is a blocker.

**Accessibility becomes tractable.** EN 301 549 and the European Accessibility
Act against a terminal application are genuinely unresolved (see
[`legal_obligations_intl.md`](../apps/law-gazelle/docs/legal_obligations_intl.md)).
Native widgets bring screen-reader, contrast and font-scaling support from the
host, converting an open legal question into a shipping property.

**The honest cost: packaging.** PyInstaller or Briefcase, **code signing**,
**macOS notarization**, Windows SmartScreen. Real, ongoing, per-platform work.
It also makes packaging a **Phase 0** concern — "self-contained" is a
build-system property, and discovering that at Phase 6 is how a project ends up
shipping a zip file with instructions.

---

## The invariants

Every row is traceable to a documented failure. These are written as tests
**first**, in the same style as the store's existing `test_no_raw_soil_reads` /
`test_no_inline_vault_root` AST-and-grep invariants — so "written correctly the
first time" is enforced rather than intended.

### Dates and deadlines

| # | Invariant | From |
|---|---|---|
| **I-1** | **One `Deadline` type.** A date never crosses a module boundary as a string. Parsing happens once, at the edge. | BUG-1, BUG-3 |
| **I-2** | **Parse strictly or refuse.** A strict `strptime` set (~26 lines, verified in the [sourcing report](../apps/law-gazelle/docs/sourcing_report.md) against 11 real fixtures and 10 garbage inputs). **Never truncate before parsing.** Never `dateutil.parser.parse` — it invents from today (`'2026'` → 2026-08-04). | BUG-1 |
| **I-3** | **Never compare dates as strings.** `overdue` is derived from the parsed value, never from lexicographic order. Two fields describing one fact cannot disagree. | BUG-3 |
| **I-4** | **Counting rules are explicit and tested.** FRCP 6(a)(1)+(6) roll-forward over `holidays` (MIT). No open-source Python court-deadline engine exists; this is ~80 lines we own and audit. | new |
| **I-5** | **No free-text dates anywhere.** Snooze, filters, and every input take a validated date. `"next week"` is rejected at the edge, not stored and string-compared. | BUG-4 |

### The record

| # | Invariant | From |
|---|---|---|
| **I-6** | **Canonical store is read-only, enforced by type.** Writes go to the sidecar. Not a convention — the canonical handle has no write methods. | law-gazelle's best idea, kept |
| **I-7** | **One key derivation.** Read and write compute `(matter, item_type, item_id)` from the same function. No literal matter name in any call site. | BUG-11 |
| **I-8** | **Never silently drop input.** Unparseable data becomes a recorded **gap**, never an empty list. `chronology_builder`'s `gaps` pattern generalized. | BUG-10 |
| **I-9** | **Writes never silently overwrite.** Every write reports what it replaced, or refuses. | BUG-8 |
| **I-10** | **Cache keys hash their inputs.** A fingerprint is derived from content or it does not exist. | BUG-7 |

### Rungs and surfaces — see [`homestead-rungs.md`](homestead-rungs.md)

| # | Invariant | From |
|---|---|---|
| **I-11** | **Every field carries a rung, set at schema-definition time.** Unclassified is a **build failure**. At runtime an unclassified field reads `L5` and is not served. A classifier that errors denies; it never returns `L1`. | rung model |
| **I-12** | **Composition is `max`.** Records, joins, chronologies, drafts — and **a prompt is the `max` of its whole context window**, including retrieved neighbours. | rung model |
| **I-13** | **`L4` reaches no surface as a payload without a declared purpose, and reaches a model prompt never.** `L5` has no override anywhere. | rung model, BUG-5 |
| **I-14** | **Rungs are strings.** `L3`, never `3` — trust runs the other direction and `>=` reads fine either way. | rung model |
| **I-15** | **Note bodies never enter a log or a prompt.** Logs carry references, not content. | **F-4** |

### Surfaces and egress

| # | Invariant | From |
|---|---|---|
| **I-16** | **One authorization chokepoint, covering every surface.** TUI, MCP, model calls, egress. A gate wired to one entry point is not a gate. | **F-2** |
| **I-17** | **No network egress by default, ever.** Any outbound call is opt-in per call and **shows the user exactly what will be sent** before sending. | **F-3** |
| **I-18** | **Any pattern that could match PII is anchored and tested against PII negatives.** The citation regex matched `1420 Maple 87501` and missed `347 F.3d 1120`. Every extraction pattern ships with a negative-case test. | **F-3** |
| **I-19** | **All paths derive from one resolver rooted at `/.homestead`.** No launcher, script, or env may redirect user data to a fixed or shared location. The Desktop is never a default. | **F-1**, E-3 |
| **I-20** | **One canonical path spelling.** `expanduser("~")` vs `Path.home()` defeated the store's own linter and law-gazelle sits in that blind spot (`safe_integration.py:23`). One helper, and a test that no other spelling appears. | store sweep |
| **I-21** | **No auto-render on start.** Cover screen first; the record is not drawn before a human asks. | **F-5** |
| **I-22** | **Two logs.** A redacted operator-visible log, and a sealed hash-chained one the app appends to and never renders. | **F-6** |

### Domain and structure

| # | Invariant | From |
|---|---|---|
| **I-23** | **The registry is the only enumeration.** Anything touching "all matters" iterates it. No hardcoded matter list in navigation, queue, or briefing. | BUG-6 |
| **I-24** | **Third-party observations require a source and an issue.** No classifier separates an evidence chronology from a surveillance log; provenance and scope do. | **F-7** |
| **I-25** | **The app never authors a fact**, and never applies law to facts. Disclosure is structural — attached to the artifact, not appended by a string check. | BUG-9, legal |
| **I-26** | **Import-pure core.** No network module imported at import time. Adapters live outside the core. | promotion bar |
| **I-27** | **Declared dependencies are true.** `pip install` from a cold checkout, then the suite passes. No out-of-band CI install. | A-1 |
| **I-28** | **Bare `pytest` works.** Nothing shadows the live suite. The promotion gate runs bare `pytest -q`. | A-2 |

### The surfaces

| # | Invariant | From |
|---|---|---|
| **I-29** | **The surface layer holds no domain logic.** It composes and renders; anything calculating lives in `homestead.keep`. With two surfaces over one core, logic in either is duplicated or divergent. law-gazelle's 1,296-line `app.py` is the symptom this prevents. | new |
| **I-30** | **Nothing binds a port.** No `http.server`, no socket listen, in any surface or the core. MCP is stdio only. | the shape |
| **I-31** | **The resting state reveals nothing.** The cover shows counts that survive the `L2` re-identification check and no more. *"1 overdue"* over a household where one matter has deadlines identifies that matter — the check is not theoretical at three matters. | **F-5**, rung model |
| **I-32** | **Reveal expires.** A deliberate act shows the payload; a timeout returns the surface to the derived form. Not a lock — a fall-back. The threat is someone walking past thirty seconds later, not someone stealing the machine. | **F-5** |
| **I-33** | **One rung indicator per surface, never per datum.** A status line — *"showing derived · L4 present"* — that changes on reveal. `L4` tagged on fifty fields is unreadable, and unreadable is unread. Never a colour alone. | rung model |
| **I-35** | **The list pane cannot render an `L4` payload.** Not a policy — the ambient render path does not accept one. Payloads exist only in a detail pane the user opened, and expire per I-32. The act of opening is the purpose declaration. | rung model, **F-5** |
| **I-36** | **The app never deletes canonical data.** It has no write path to the record (I-6), so retention is necessarily advisory. Matter packs carry **`review_after`** — an event or duration that surfaces a *review item in the queue*, never a deletion. Auto-purging a live matter is destroying evidence on a schedule. | I-6, **F-5**, GDPR Art. 17 |
| **I-34** | **Bind by consequence, not by frequency.** Single-key for acting — what is due, mark done, snooze. Deliberate friction for revealing history or payloads. `a` opening a confession timeline in one press is the defect. | **F-4** |


---

## Build order

Each phase ends with its invariant tests green. **The tests come first and start
red** — that is the whole method.

### Phase 0 — the seat

`homestead-affairs/homestead`. `homestead.keep` skeleton, the `/.homestead`
resolver (I-19, I-20), the two logs (I-22), and **the invariant test suite,
written and failing**.

**Plus packaging, from day one.** A signed, double-clickable artifact that
launches an empty window on all three platforms — before there is anything to
put in it. "Self-contained" is a build-system property; a project that defers it
ships a zip file with instructions.

*Exit:* I-19, I-20, I-27, I-28 green. `pip install -e .` from cold, `pytest -q`
bare, both clean.

### Phase 1 — dates and the record

The `Deadline` type, strict parser, counting rules over `holidays`. The
read-only canonical handle and the sidecar. Key derivation.

*Exit:* I-1 … I-10 green, with the 11 real fixtures and 10 garbage inputs as
test data.

### Phase 2 — rungs

Classification at schema-definition time, `max` composition, the surface table.
`_fact_blocked`'s successor.

*Exit:* I-11 … I-15 green. An unclassified field fails the build.

### Phase 3 — registry and one matter pack

The matter-type registry, then **custody only**. One pack proves the seam; three
prove nothing that one does not.

*Exit:* I-23 green. Adding a pack touches no navigation, queue, or briefing code.
**The custody pack is classified at import, and an unclassified field in it fails
the build** — a real schema, not the capability to refuse one.

That last clause is Phase 2's exit line made load-bearing, and it is stated again
here because Phase 2 met it in a way worth naming. `classify_schema` is
implemented and heavily tested; it has **no callers**, and the package declares no
field with a rung. So *"an unclassified field fails the build"* is currently
satisfied the way a lock on an empty room is satisfied — correctly, and without
evidence. Phase 3 is where the room gets something in it, so Phase 3 is where the
criterion earns its keep. A green suite before that point is not evidence that
any schema has ever been classified.

Note also what the instrument is and is not. `classify_schema` **raises**;
whether that is a *build* failure is a property of when a caller calls it, and
nothing enforces import time. So "fail the build" and "fail the user" are not
competing implementations to choose between — they are one function invoked from
two places, and a product may do both. That matters if a pack is ever
operator-authored rather than shipped, which is **not in v1** (all three packs
here are project-authored, and D2 is deferred under *Deliberately not in v1*).
Whether a household operator may extend a *shipped* pack is not the D2 case and
is not answered anywhere; it is small and it is open.
See `homestead/docs/DECISION-unclassified-field-instrument.md`.

### Phase 4 — surfaces

The app (tkinter) first, then the MCP stdio entry, both thin over the core and
both crossing the single chokepoint. Cover, reveal-expires, boundary indicator,
consequence-bound keys.

*Exit:* I-16, I-17, I-21, I-29 … I-34 green. The gate is **on by default** and
its tests do not skip — law-gazelle's skipped 9 are the counter-example.

### Phase 5 — the other two packs

Bankruptcy and workers' comp. If either requires a change outside its own pack,
Phase 3 was wrong and the registry gets fixed before the pack lands.

### Phase 6 — search, seams, attestation

**Nestor is an optional extra, decided 2026-08-04.** It goes in
`[project.optional-dependencies]`, never the required path — a household that
wants entity resolution installs it; nobody else pays for it. Two consequences:
the seam must **degrade to feature-absent, never crash**, and the ledger-pinning
obligation only arises when the extra is present. `homestead.keep` builds its
own sealed log per **I-22** regardless, so there is never a second hash-chain
in the required path.

FTS5 semantic seam (the [sourcing report](../apps/law-gazelle/docs/sourcing_report.md)
establishes it clears the bar at zero dependency cost). The
[Nestor seam](drafts/nestor_seam.py) if wanted — contract already written.
Then `promotion.json` and a verifier who is not the author.

---

## Deliberately not in v1

- **No cloud model, ever.** Local inference only.
- **No panic wipe** — spoliation, discoverability under oath, and without a lock
  it is equally the adversary's destroy key (**F-5**).
- **No intake / docassemble** — the biggest build, and it needs a partner first.
- **No multi-client dimension.** D2 (clinic) reintroduces entitlement edges;
  Terpsi's model is the reference when it lands.
- **No CourtListener.** It is what produced **F-3**. Re-add only behind I-17 and
  I-18.
- **No forms-and-instructions product**, at any version. *UPL Comm. v. Parsons
  Technology.*

## Open, and blocking

- ~~**D-6 — the verifier.**~~ **Decided 2026-08-04.** `verified_by` is a named
  hand that is not the author — if the code is written by an agent, the
  operator verifies. **The attestation splits:** `verified_by` covers the
  **engineering gates only**. The **legal posture is a separate, named,
  outstanding item that promotion does not cover and must not appear to.** The
  gates check tests, imports, seams and leaks; they check nothing about UPL,
  § 110, GDPR, or whether this is safe to hand a litigant, and a record silent
  on that gap invites a green gate being trusted to say what it never said.
  Counsel precedes any D2 deployment.
- **Verification evidence is a Phase 0 deliverable**, not a Phase 6 scramble: a
  verifier must be able to clone cold and run the whole invariant suite and the
  gate in **one command**. A verifier who arrives at the end with no record has
  to take everything on trust, which is ratification in name only.
- **The `L4`-on-S1 question** — does the operator see the derived form on their
  own screen? The one rung decision that changes daily use.
- **`rebuilt` as a fourth tombstone shape** — needs ratifying into
  [`conventions/tombstones.md`](conventions/tombstones.md).

---

## Related

- [`homestead-affairs-face.md`](homestead-affairs-face.md) · [`homestead-rungs.md`](homestead-rungs.md) · [`die-rules.md`](die-rules.md)
- [`conventions/pinned-dependency-seams.md`](conventions/pinned-dependency-seams.md) · [`conventions/tombstones.md`](conventions/tombstones.md)
- [`apps/law-gazelle/docs/bug_list.md`](../apps/law-gazelle/docs/bug_list.md) · [`household_safety.md`](../apps/law-gazelle/docs/household_safety.md) · [`sourcing_report.md`](../apps/law-gazelle/docs/sourcing_report.md)
- [`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md) · [`_intl.md`](../apps/law-gazelle/docs/legal_obligations_intl.md)

ΔΣ=42
