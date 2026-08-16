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
- every path must resolve **inside** the corpus root, so a symlink planted in
  `docs/checklists/` cannot smuggle a control in from outside (the containment
  check bite 0's `../../escape.py` crown jewel established, applied to an
  injected corpus for the same reason: the path came from outside)
  *(grounded: tested)*. The read is taken from that *same* resolved path
  (`_resolved_within`), closing a check-then-use mismatch an adversarial audit
  found — the old bool check resolved once and `read_text` resolved again, so a
  swap between the two could be checked inside and read outside. This is **not**
  atomic against a genuine race-swap during the read; the honest bound is that
  such a race needs write access inside the corpus root, and anyone with that
  can plant a control directly — the race buys nothing the threat model does
  not already grant;
- every control string passes through `_as_data()` — NFKC-normalized, Unicode
  control characters dropped, whitespace collapsed, capped at 300 characters —
  so no control text can forge a line in a queue item or a log *(grounded: an
  audit tried RTL-override, zero-width, Zalgo, homoglyph, and tag-char
  injection; all stripped)*.

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
**on the type**: `Verdict.__post_init__` refuses `Status.PASS`, so no path —
`assess()`, `assess_gates()`, or a hand-built `ReadinessAssessment` — can carry
a Pass into a report, because the Pass `Verdict` cannot be constructed. The
first design guarded only inside `assess()`; an audit built a Verdict outside it
and watched a Pass flow through `note()` (which printed "NO control is Pass"
over a live one). "A convention is what a later edit forgets" — so the refusal
moved from the call site to the constructor, where a later edit cannot route
around it, and the call-site guard was removed as dead.

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

## D-R7 — `promote_check`'s gates get their own bearings, and it inverts the asymmetry

The panel's four instruments *scan* a build for incidental evidence; the ten
`promote_check.py` gates are pass/fail checks each already aimed at one
specific question. That difference flips D-R4's asymmetry rather than
repeating it: `assess_gates()` treats a **failed** gate as first-party
evidence (`Status.FAIL`, citing the gate's own `detail` and the control's
`file:line`) and a **passed** gate as the weaker signal (`Status.BLOCKED`,
naming the gate) — a mechanical check clearing is not a human's evidence the
control is met, so rule 6 draws the line at Blocked exactly where it draws it
for a clean instrument. `GATE_BEARINGS` is keyed by the gate's BASE name; a
one-line helper (`_gate_base_name`) strips promote_check's trailing `" [A]"`/
`" [M]"` tag once, in one place, rather than re-deriving the strip at every
call site. Both `assess()` and `assess_gates()` still route through
`_refuse_to_mint_pass()` — one guard, one invariant, whichever seam calls it.

Nine of the ten gates were read against the corpus and rejected; one survived:

- **`witnessed` ↔ USEQ-E075330B** — *"Apply independent review proportionate
  to impact and prevent authors from self-approving material controls."* The
  gate's floor (`verified_by` set and `!= author`) IS that sentence, not a
  paraphrase reached for it: both are, word for word, "prevent the author from
  approving their own material control." The candidate found first by keyword
  search — the corpus's *"Reviewer: someone other than the implementer for
  material controls"* — turned out to be **operating instructions** (§1, "how
  to operate this checklist"), not a control with a stable ID; it cannot be
  cited as evidence for anything, so it was set aside in favor of the control
  that actually says the same thing.

Rejected, each after reading the gate's mechanism and the control's text side
by side, not just their names:

- **`tests_green`** — the only close control, USEQ-007A0FED ("verify …
  formatting, compilation, static analysis, unit tests, contracts, secrets,
  dependencies, policy, and packaging"), is already `execution`'s bearing
  (D-R5's four-instrument table). Assigning it a second time from a
  differently-scoped mechanism — one pytest/unittest run, vs. a sandboxed
  parse of every file — is the "plausible, unearned mapping" rule 6 forbids in
  a new shape: two bearings quietly competing to explain one ID. No other
  control asks "did the test suite exit clean" on its own, apart from that
  nine-clause bundle.
- **`vault_leak`** — checks storage **location** (does a path derive from the
  injected vault root, or a fixed home path) — a SAFE-specific convention. The
  corpus's nearest neighbors, PRC-10-037 ("no secrets in source") and the
  tenant-isolation / data-residency families, ask about literal secret strings
  or multi-tenant SaaS boundaries. Neither is the question `vault_leak_lint`
  answers; nothing else in 10,042 controls is either.
- **`own_repo`, `host_repointed`** — the plausible target, PRC-02-014 ("the
  production artifact cannot be traced to reviewed source, dependencies, build
  process, tests, and approval"), is a compound five-clause release gate.
  `own_repo` verifies one string (a repo URL outside this monorepo);
  `host_repointed` verifies one attested boolean. Neither establishes
  traceability through dependencies, build process, or tests — attributing a
  FAIL on either to PRC-02-014 would claim more was checked than was.
- **`import_pure_core`, `inversion`, `semantic_seam`** — architectural
  properties of this store's own promotion shape (no network import at import
  time; the core doesn't import its host; a declared `module:symbol`
  resolves). No generic production-readiness control asks any of these —
  confirmed, not assumed, as the bite that named them expected.
- **`manifest`, `attestation`** — not investigated (not named as candidates);
  left out rather than guessed at.

**Grounded**: `assess-gates` was run against the real corpus with a synthetic
nine-gate result set (the shape `promote_check.check()` actually returns).
`witnessed [M]` failing cited `USEQ-E075330B` at
`docs/engineering/01-governance-and-foundations.md:458` with `Status.FAIL`;
`witnessed [M]` passing produced the same control at `Status.BLOCKED`, never
`Status.PASS`; the other eight gates reported `bear on no control in this
corpus`, matching the rejections above exactly.

## Open / next

- **The `witnessed → Pass` tension.** `witnessed` is the one gate in
  `GATE_BEARINGS` whose PASSING outcome encodes something a human actually
  did: `verified_by` names a specific person, distinct from the author, and
  when the attestation carries a `trust` block that name is backed by a
  cryptographic seal — a provisional custody entry covered by a checkpoint
  signed with the verifier's own key (`promote_check._witnessed`). That is
  closer to a real ratification than anything else in either bearing table:
  an owner, a recordable identity, evidence a specific verifying act
  occurred. It is also the sole candidate anywhere in this module for a
  legitimate MECHANICAL Pass — and `assess_gates()` still reports it Blocked,
  on purpose. `Status.PASS` exists in the corpus's vocabulary because a human
  records one, with evidence, an owner, a release, and a date (D-R4); whether
  a verified cryptographic seal clears that bar, or is still one step short of
  it (an identity check, not a review), is a genuine design call this bite
  held open rather than made. Not implemented here.
- **The corpus's `PRC-02-*` immediate no-go conditions are still unwired for
  the panel's four instruments** (as distinct from the gate table above,
  which now covers `witnessed`). Twenty controls that stop a release outright,
  none borne on by an instrument.
- **Nothing consumes `note()` yet in a stored artifact.** The reader has a CLI
  and returns an assessment; wiring it into a promotion record, or into the
  panel's routed queue items, is a separate call about where the sentence
  belongs.
- **Upstream drift now has a proactive guard, not yet a schedule.**
  `tools/readiness_drift.py` closes the first half of the gap above: it reads
  every `control_id` referenced anywhere in `BEARINGS` and `GATE_BEARINGS`,
  checks each against the injected corpus via `ReadinessCorpus.get()`, and
  exits 0 (clean, naming the corpus and the count verified), 1 (drift — every
  drifted ID printed with which table/key referenced it), or 2
  (`CorpusUnavailable` — a guard that cannot reach its corpus must not report
  a false all-clear, same fail-closed rule the seam itself follows). It is
  stdlib-only, spec-loads `stores/readiness_corpus.py` the same
  `_REPO`-relative way `_cmd_assess` and the test suite do, and runs clean
  against the real corpus today: `7 referenced control ID(s) verified
  present`. Covered by `tests/test_readiness_drift.py`, which builds its
  fixture corpus from the live tables rather than a hardcoded ID list, so the
  test does not go stale the day a bearing changes.

  What is still open: **it is not wired into scheduled CI.** The corpus is a
  separate repository, not checked out in this repo's CI, so the guard has
  nowhere to run automatically yet. A ready-to-paste job, once someone
  decides to add it to `.github/workflows/store-ci.yml`:

  ```yaml
  readiness-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          path: safe-app-store
      - uses: actions/checkout@v4
        with:
          repository: rudi193-cmd/production-readiness-checklist
          path: production-readiness-checklist
      - run: |
          cd safe-app-store
          python3 tools/readiness_drift.py \
            --corpus ../production-readiness-checklist --strict
        # or, equivalently: export FORGE_READINESS_CORPUS instead of --corpus
  ```

  Actually adding this job to `.github/workflows/store-ci.yml` is the
  remaining human call — out of scope for the bite that built the guard.

---

*Rule 11, the other way round: this time the house had the shape (the Almanac's
injected corpus) and the outside had the content. `ΔΣ=42`*
