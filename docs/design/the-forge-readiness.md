# The Forge — the readiness seam (design, 2026-08-16)

> A ruler the fleet did not cut. `stores/readiness_corpus.py` measures the
> measuring panel's coverage against an **external, versioned, dated control
> corpus** instead of against the five classes the panel wrote for itself.
> Facts marked *(grounded)* were measured on this branch, not assumed.

## The problem this closes

`stores/measure_panel.py` already carries the sigmap lesson: every run states
which instruments ran, which could not, and what that blinds it to, so "green"
is never read as "sound." But the denominator in that sentence is
`ASPIRATIONAL_CLASSES` — **five classes the panel authored itself**. Cover all
five and the panel reports full coverage. That is the same trap one level up: a
harness grading itself against a ruler it cut.

The check the panel could not perform on itself is *"measured against what,
that someone else defined?"*

## The corpus

`rudi193-cmd/production-readiness-checklist`, a fork of
[`MarinJursic/production-readiness-checklist`](https://github.com/MarinJursic/production-readiness-checklist)
(MIT), **v2.1.0, released 2026-08-15** — 10,042 controls with stable IDs
*(grounded: parsed, 1,421 `PRC-*` + 8,621 `USEQ-*` = 10,042, matching its own
`scripts/validate.py` constants exactly)*. Technology-neutral by an enforced
rule of its own validator: a control naming a language, framework, or vendor
fails its CI.

It arrives with a law that is, almost word for word, the Forge's thesis:

> *"An agent must label these controls **Blocked** or **Unknown**, not infer a
> pass from missing information."* — `docs/guides/ai-assisted-review.md`

and an anti-pattern list that names, precisely, the failure this seam is built
to make impossible: *"Allowing the agent to mark organizational or
production-only controls as passed from source code."*

## D-R1 — The corpus is injected, never vendored

`stores/almanac/README.md` settled this shape already, for a public live list:
*"the store provisions the fetch, never a static copy … Ship the mold and the
reader; the wood stays with whoever grew it."* This is that seam one axis over
— applied to a public **standard** rather than a public **list**.

So: the corpus root is injected (an explicit path, or `FORGE_READINESS_CORPUS`),
there is no default path, and its absence raises `CorpusUnavailable` — a
declared gap, the way a missing instrument is. Vendoring 10,042 controls into
`safe-app-store` would freeze someone else's living document and duplicate what
rule 8 says is never duplicated. The reader travels; the corpus does not.

Rejected: copying the two `docs/` trees in at a pinned SHA. It reads as
reproducibility and is really a fork of a document the fleet has no authority
over, which goes stale silently and without a diff anyone will look at.

## D-R2 — The format's owner is upstream

The two control regexes are lifted from the corpus's own
`scripts/validate.py` (`CONTROL`, `ENGINEERING_CONTROL`) rather than
re-derived. A second, independently invented parser is a fork of the format,
and it rots without saying so. When the patterns stop matching, that is a
`CorpusUnavailable` — *"the corpus's control format changed shape"* — not
something to rescue with a looser pattern. Zero controls parsed is refused for
the same reason: a coverage gap stated against an empty denominator understates
itself.

## D-R3 — The corpus is untrusted input, read as data

A fork of a repository this fleet does not control, whose text reaches JSON
output and the `human_required` queue. Mechanically, not aspirationally:

- nothing in the corpus is imported or executed — only `*.md` text is read;
- every path is checked to resolve **inside** the corpus root, so a symlink
  planted in `docs/checklists/` cannot smuggle a control in from outside
  (the containment check bite 0's `../../escape.py` crown jewel established,
  applied to an injected corpus for the same reason: the path came from
  outside) *(grounded: tested)*;
- every control string passes through `_as_data()` — NFKC-normalized, Unicode
  control characters dropped, whitespace collapsed, capped at 300 characters —
  so no control text can forge a line in a queue item or a log.

The corpus's own rule 9 says the same thing from the other side. The two laws
agree, and this is the place they are enforced.

## D-R4 — The seam is one-directional: it can Fail a control, never Pass one

The status vocabulary is the corpus's four, exactly: Pass, Fail, Blocked, Not
Applicable. `assess()` emits only Fail and Blocked.

- an instrument that **finds something** can move a control to **Fail**, with
  the artifact, the metric, and the control's own `file:line` cited;
- an instrument that **ran clean** leaves its controls **Blocked** — absence of
  a finding is not evidence a control is met (rule 6);
- an instrument that **could not run** leaves them Blocked for a separately
  reported reason;
- everything no instrument bears on is Blocked, because most of the corpus
  needs operating evidence — production configuration, a restore, alert
  delivery, on-call authority, a contract — that no repository can supply.

`Status.PASS` exists because a *human* records one, with evidence, an owner, a
release, and a date. No mechanical reader has any of those. That is enforced
structurally by `_refuse_to_mint_pass()`, which raises rather than returning —
a convention is what a later edit forgets.

## D-R5 — Bearings are hand-authored, and declare their own strength

A `Bearing` is a claim that one instrument's measurement bears on one control,
carrying `why`, a `limit` (what it still cannot show), and `on_finding` (the
strongest status a hit can support).

Hand-authored on purpose: keyword-matching instrument descriptions against
10,042 control texts would manufacture dozens of plausible, unearned mappings —
exactly the inference rule 6 forbids. **Six mappings that survive reading both
sides beat six hundred that survive a regex.** Four instruments, six controls,
each verified present in the real corpus by a live test.

`on_finding` was **not** in the first design; the first real run put it there.
The census flagged `apps/the-binder/web/binder.png` at 95% of the build and the
seam called PRC-07-015 *("Large binaries, generated files, and vendored code
are controlled")* **Fail** — but a 95% PNG is evidence a large binary **exists**,
not that large binaries are **uncontrolled**, and rule 5's bar for Fail is
direct evidence the control is *not met*. A reviewed app icon and an
uncontrolled dump look identical to a size census. So `census` declares
`on_finding=BLOCKED` — it names the artifact and says it *raises the control
without answering it* — while `hygiene` finding a committed `error_log`
genuinely fails the same control, because no policy deliberately versions a
stray dump *(grounded: seven playground builds had been called Fail on
PRC-07-015 by the size census alone — `UTETY-Reddit-Bots`, `ask-jeles`,
`llmphysics-bot`, `ratatosk`, `source-trail`, `the-binder`, `vision-board` —
and all seven are now Blocked-with-the-artifact-named instead. After the fix,
**no current playground build fails a borne control**; the Fail path is
exercised by the tests' box-shaped fixture, not by anything in `apps/` today)*.

A bearing may not claim a finding supports a Pass; the constructor raises.

`calibration` is deliberately absent from the table: `calibration_ledger` is
longitudinal — a claim about the model *across* builds — so it cannot bear on a
control scoped to one release.

## D-R6 — Counts, never a percentage

The corpus's rule 13: *"Do not calculate a readiness percentage. One blocker
may outweigh hundreds of passing controls."* A coverage fraction is not a
readiness score, but printed beside control counts it will be read as one. So
`note()` emits raw counts and states why the ratio is absent. Tested (`"%" not
in note`).

Two instruments disagreeing on one control resolve to a single status, **Fail
winning**: a control with direct evidence it is not met is not rescued by a
second instrument that looked elsewhere and saw nothing. The per-instrument
verdicts stay as the evidence trail beneath it.

## What it actually reports

Against the real corpus, on `apps/the-forge` *(grounded)*:

> controls with evidence from this panel: **1 of 10,042** … The other 10,041
> are Blocked: no instrument here bears on them, and most require operating
> evidence … NO control is Pass: this panel cannot mint one.

One. That number is the deliverable. The panel's own coverage note reads
2-of-5 classes on the same build; measured against a ruler someone else cut,
the same run is one control in ten thousand. Both sentences are true, and the
second is the one that is hard to misread as an all-clear.

## Open / next

- **The corpus's `PRC-02-*` immediate no-go conditions are unwired.** Twenty
  controls that stop a release outright, none of them borne on by any
  instrument today. The nearest is PRC-02-014 (*the production artifact can be
  traced to reviewed source, dependencies, build process, tests, and approval*)
  — which is close to what `promote_check.py` already asserts, and is the most
  promising next bearing.
- **Bearings for `promote_check`'s ten gates, not just the panel's four
  instruments.** The gates are the store's real promotion bar; several of them
  (`tests_green`, `vault_leak`, `witnessed`) plausibly bear on controls, and a
  `witnessed` gate that already enforces `verified_by ≠ author` is directly the
  corpus's "reviewer: someone other than the implementer for material
  controls." Held back here to keep this bite one bite.
- **Nothing consumes `note()` yet in a stored artifact.** The reader has a CLI
  and returns an assessment; wiring it into a promotion record, or into the
  panel's routed queue items, is a separate call about where the sentence
  belongs.
- **Upstream drift is undetected.** The fork re-syncs; a control this seam
  names could be renumbered upstream. `assess()` skips a bearing whose control
  the corpus lacks (coverage shrinks rather than lying), and `bearings --corpus`
  exits non-zero listing them, but nothing runs that on a schedule.

---

*Rule 11, the other way round: this time the house had the shape (the Almanac's
injected corpus) and the outside had the content. `ΔΣ=42`*
