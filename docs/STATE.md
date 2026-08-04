# State — 2026-08-04

*Where everything is, and what survived the rebuild decision. One page, so the
answer to "where do we stand" is not a reading list.*

---

## The map

| What | Where | State |
|---|---|---|
| **The essay** | [`docs/on-this-side-of-the-law.md`](on-this-side-of-the-law.md) | done |
| **The face** | [`docs/homestead-affairs-face.md`](homestead-affairs-face.md) | decided |
| **Die-level rules** | [`docs/die-rules.md`](die-rules.md) | decided — seats, roots |
| **The rung model** | [`docs/homestead-rungs.md`](homestead-rungs.md) | decided; partly built |
| **The build plan** | [`docs/homestead-law-build-plan.md`](homestead-law-build-plan.md) | 36 invariants · **two of its claims are overclaims, flagged at the top** |
| **Conventions** | [`docs/conventions/`](conventions/) | seams, tombstones — both with enforcement deferred |
| **Nestor seam** | [`docs/drafts/nestor_seam.py`](drafts/nestor_seam.py) | contract written; Nestor is an optional extra |
| **Org profile** | [`docs/homestead-affairs-profile-README.md`](homestead-affairs-profile-README.md) | drafted, unpublished |
| **Legal — US / intl** | [`apps/law-gazelle/docs/legal_obligations_*.md`](../apps/law-gazelle/docs/) | reference; gates deployment, not code |
| **Sourcing** | [`apps/law-gazelle/docs/sourcing_report.md`](../apps/law-gazelle/docs/sourcing_report.md) | two dependencies total; the rest is write-it-ourselves |
| **Store-wide safety** | [`docs/store_minors_safety.md`](store_minors_safety.md) | **no tracking home — deliberately, see below** |
| **The code** | `rudi193-cmd/homestead` | Phase 0 built, **audited, not clean** |
| **Remediation** | `rudi193-cmd/homestead` → `docs/PHASE0-REMEDIATION.md` | 7 fixes + 1 decision, none made |

**Repos live:** `rudi193-cmd/homestead` (Phase 0 pushed), `homestead-law`,
`homestead-ledger` — all public, all on the personal account awaiting transfer.

---

## Reconciliation

The finish list holds **45 items** written when the plan was to *repair*
law-gazelle. We then decided to **rebuild**. Most of Track A is now describing
work that will never happen, and a list that large describing dead work is worse
than no list.

Verdicts below. **Do not work an item marked dead.**

### Dead — the code they describe is being replaced

`A-1` declare host deps · `A-2` archived shadow · `A-3` stale spec boxes ·
`A-4` `safe_integration` self-shadow · `A-5` README refresh · `A-7` orphan
modules · `B-3` verify `nest_watcher`

Six of Track A and one of B. Their **lessons** survive as invariants — A-1 became
`I-27`, A-2 became `I-28` — but the work does not.

### Resolved by a design decision

| Item | Resolved by |
|---|---|
| `B-4` draft evidence guard | the rung model — `L5` is never served on any surface |
| `B-5` CourtListener | **F-3** identified it as the exfiltration vector; the build plan excludes it from v1 |
| `C-1` cold checkout works | `I-27` / `I-28`, built and verified in Phase 0 |
| `E-6` private-ledger's name | `homestead-ledger` is live |
| `D-6` verifier | split: `verified_by` covers engineering gates only; legal posture is separate and outstanding. **The person is still unnamed.** |

### Done

`E-0` org handle confirmed · `E-2` `homestead.keep` and `E-3` `/.homestead`
exist — **but Phase 0 is audited and not clean**, so treat both as built rather
than finished.

### Carries — knowledge, not work

`B-1` PDF sync · `B-2` remaining matter tables · `C-2` demo end-to-end ·
`D-1` semantic seam (FTS5, Phase 6) · `D-4` `promotion.json` · `D-5` gate run

These describe things `homestead-law` will need. They are **specification input**
now, not tasks against existing code.

### Still live, unchanged by the rebuild

`C-3` PII scrub · `C-5` pilot partner · **`C-6` `personas.py`** · `E-1` teach
the vault-leak linter · `E-4` matter registry · `E-7` module names ·
`E-8` `justice-almanac` edge · `E-9` + `C-4` reconcile MISSION ·
`E-10` publish the org profile · `E-11` Nestor seam · `E-12` rung model ·
all of **Track F** · all **8 remediation items**

> **`C-6` deserves the emphasis.** Rebuilding `homestead-law` does *not* remove
> `personas.py` from this repo. It is still there, still dead code, and the US
> legal research independently rated it a live liability — its text is close to a
> template for the self-presentation *In re Reynoso* penalized. The rebuild moves
> the product; it does not clean the predecessor.

### Bug coverage — all 12 have an invariant successor

`BUG-1`/`BUG-2` → `I-1`,`I-2` · `BUG-3` → `I-3` · `BUG-4` → `I-5` ·
`BUG-5` → `I-13`,`I-35` · `BUG-6` → `I-23` · `BUG-7` → `I-10` ·
`BUG-8` → `I-9` · `BUG-9` → `I-25` · `BUG-10` → `I-8` · `BUG-11` → `I-7` ·
`BUG-12` → `I-16`

Nothing from the bug list falls through the rebuild.

---

## Two gaps the reconciliation found

A reconciliation that finds nothing missing is not doing its job. Two items have
**no successor and no home**:

1. **`A-6` — the seeder that writes wherever `argv[1]` points.** Filed as a
   law-gazelle fix, so it dies with law-gazelle. But the *class* of failure —
   a script that puts case files wherever an unparsed argument says — has **no
   invariant** in the build plan. It should. Proposed **I-37: no script takes a
   destination without validating it, and no destination outside the root is
   accepted.**
2. **`F-8` — the first-run shared-machine question ending in a DV
   safety-planning referral.** It is documentation and copy rather than a
   control, so it fits no invariant, and the build plan has no section for
   *things that must be said to the user*. It currently exists nowhere in the
   plan. That is the one finding in the whole safety pass that cannot be
   enforced in code, which is exactly why it is the one most likely to be lost.

---

## Deliberately homeless

The **store-wide safety findings** have no tracking list, by decision — the
portfolio is mid-reshuffle, some apps will merge and some will promote, and a
list keyed to app names would be stale the moment two of them combine.

But four of those findings are **store-level, not app-level**, and survive any
reshuffle because they are properties of the gates rather than of any app:

- **No manifest schema.** `privacy_tier`, `data_streams` and `local_processing`
  are read by no lint, test or CI step — so install-time consent rests on
  declarations nothing checks.
- **The vault-leak linter is defeated by a spelling** (`E-1` fixes half of this).
- **The store models no data subject but the operator** — no minors or audience
  field anywhere.
- **`CLAUDE.md` §7's sandbox claim** is not implemented by `Makefile:24`.

Those four are durable now and will still be true whatever the portfolio
becomes.

---

## What is actually next

1. **Phase 0 remediation** — 7 fixes, 1 decision. Nothing should build on Phase 0
   until this lands; the audits found the enforcement weaker than the plan claims
   in four places.
2. **`E-1`** — teach the vault-leak linter, which is a *store* fix and unblocks
   nothing else but is small and real.
3. **`C-6`** — archive `personas.py` with a note saying why.
4. **Phase 1** — dates. Three pending tests already written and waiting.

Everything else waits on a person: a verifier, counsel, a pilot partner, and the
org transfer.
