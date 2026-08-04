# `homestead-law` — build plan

*A fresh build in a new repo. Not a port, not a refactor. Every failure this
session documented is written correctly the first time, and the tests that say
so are written before the code that satisfies them.*

**Drafted 2026-08-04.** Target: `homestead-affairs/homestead-law`, with
`homestead-affairs/homestead` (the seat, holding `homestead.keep`) built first.

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

---

## Build order

Each phase ends with its invariant tests green. **The tests come first and start
red** — that is the whole method.

### Phase 0 — the seat

`homestead-affairs/homestead`. `homestead.keep` skeleton, the `/.homestead`
resolver (I-19, I-20), the two logs (I-22), and **the invariant test suite,
written and failing**. Nothing else.

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

### Phase 4 — surfaces

TUI, then MCP, both behind the single chokepoint. Cover screen. Rung enforcement
per surface.

*Exit:* I-16, I-17, I-21 green. `GAZELLE_GATE`'s successor is **on by default**
and its tests do not skip.

### Phase 5 — the other two packs

Bankruptcy and workers' comp. If either requires a change outside its own pack,
Phase 3 was wrong and the registry gets fixed before the pack lands.

### Phase 6 — search, seams, attestation

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

- **D-6 — the verifier.** Still unanswered; no engineering resolves it.
- **The `L4`-on-S1 question** — does the operator see the derived form on their
  own screen? The one rung decision that changes daily use.
- **`rebuilt` as a fourth tombstone shape** — needs ratifying into
  [`conventions/tombstones.md`](conventions/tombstones.md).
- **Nestor's pin**, and whether it is in v1 at all.
- **Retention** — `"permanent local"` is a placeholder, not a decision.

---

## Related

- [`homestead-affairs-face.md`](homestead-affairs-face.md) · [`homestead-rungs.md`](homestead-rungs.md) · [`die-rules.md`](die-rules.md)
- [`conventions/pinned-dependency-seams.md`](conventions/pinned-dependency-seams.md) · [`conventions/tombstones.md`](conventions/tombstones.md)
- [`apps/law-gazelle/docs/bug_list.md`](../apps/law-gazelle/docs/bug_list.md) · [`household_safety.md`](../apps/law-gazelle/docs/household_safety.md) · [`sourcing_report.md`](../apps/law-gazelle/docs/sourcing_report.md)
- [`apps/law-gazelle/docs/legal_obligations_us.md`](../apps/law-gazelle/docs/legal_obligations_us.md) · [`_intl.md`](../apps/law-gazelle/docs/legal_obligations_intl.md)

ΔΣ=42
