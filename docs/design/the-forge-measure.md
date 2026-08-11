# The Forge — the measuring panel (design, 2026-08-11)

> Prompted by the box (`rudi193-cmd/quick-stupids` PR #5): a fabricated legacy
> horror exhibit, and 15 of the fleet's own tools turned loose on it. Its two
> durable results are load-bearing for The Forge's model side, so they are
> recorded here as the design basis for a new component the checkpoint loop
> did not have.

## Why the checkpoint loop is not enough

Everything built this session — checkpoint, memory, calibration, FSRS,
engagement gate, the human_loop governance layer — governs the **watched
decision**: a choice the model surfaced and the maker signed. The box shows
that is structurally incomplete:

1. **The failure is never in the step you were watching.** The box's real
   disease was a committed `error_log` (93% of the repo) that **nobody
   decided**. It was named independently by four unrelated instruments —
   DontFeedTheAI (2,645/2,645 flagged IPs), HeatWatch (risk 73.7, the hottest
   artifact), smallcode (93% of tokens), homestead-ledger (−118.61, the single
   largest liability) — none asked to look. The headline jokes (four "final"
   folders, the decorative login) were the distraction. **Decision-extraction
   is blind to this class by construction: a checkpoint fires on a choice, and
   nobody chose the error_log.**

2. **Convergence is the alarm.** No one tool "found" the error_log; four blind
   instruments *converged* on it. Convergence — several instruments built for
   unrelated jobs naming the same artifact — is a far stronger signal than any
   single reading, and it is the panel's core mechanic.

3. **Health is a claim about the harness, not the code.** sigmap scored the
   worst repo imaginable **100/100 health A and coverage D in the same breath**
   — "health" meant "did my own tooling run." The Forge is *acutely* exposed to
   this: we just built a green harness (140+ tests, attestation, engagement
   scored, FSRS). A maker can be fully engaged, non-forgeably attest, every gate
   green — and the model still committed an error_log. **Our green signals are
   harness-health; they must never masquerade as artifact-truth.**

4. **Plausibility ranks the decoy.** sigmap answered "where is auth?" with
   `login.php` — exactly right, exactly wrong: it is never called (`fan_in=0`,
   caught by codebase-memory-mcp and by execution, not by ranking). A model
   emitting `Decision`s and `Plan`s *is* a plausibility engine; it will
   confidently deliver the decoy. Only grounding (run it) and measuring (call
   graph) refute it.

## The component: a measuring panel

`stores/measure_panel.py`. It runs a set of measuring **instruments** across a
build, and:

- **detects convergence** — an artifact named by ≥2 distinct instruments is a
  `ConvergentFinding`, the alarm (#2);
- **reports its own coverage honestly** — every run names which instruments
  ran, which declared themselves unavailable, and which measurement *classes*
  had no instrument at all, each with the fleet tool that would cover it (#3);
- **routes** convergent findings into the `human_required` queue via
  `checkpoint_governance.route_nudge` (the outbox the engagement gate and #67
  already feed) — a `review` item a human should see. It **never blocks a
  build**; it surfaces.

An **instrument MEASURES** (size, call graph, execution), it does not judge a
design decision — that is the checkpoint's job. The panel catches what
checkpoints can't see. Store-side (D1): `apps/the-forge/` never imports it; a
build does not measure itself and mark its own homework.

## The instruments — reuse the tools that made willow (rule 11)

Every instrument that helped in the box already exists in the fleet and is
pointed outward; the panel is the *wiring*, not a rebuild. The mature panel's
classes and their fleet tools (`ASPIRATIONAL_CLASSES` in the module):

| Class | Fleet tool | What it refuses |
|-------|------------|-----------------|
| **size** | census (dependency-free) / `smallcode` token budget | one file drowning the repo (the error_log) |
| **hygiene** | the hygiene instrument (dependency-free) | committed-by-accident smells (logs, backups, sentinels) |
| **call-graph** | `codebase-memory-mcp` (`fan_in=0` dead code) | the plausible decoy that is never called |
| **execution** | `kartikeya` (run it, don't read it — bite 0's sandbox) | a confident reading that execution refutes |
| **calibration** | `oakenscrolls-office` (grade the model's own confidence) | the model's own overconfidence |

The framework + the two dependency-free instruments (`census`, `hygiene`)
shipped first, then the three real fleet instruments — one per remaining class.

**`codebase-memory-mcp`'s call graph** (`stores/instrument_callgraph.py`, opt-in
via `--with-callgraph`): drives the tool one-shot (`cli --json`), computes dead
code as the SET DIFFERENCE `all_functions - called - entry_points - builtins`
(its OPTIONAL-count aggregate is broken — returns 1 for an unmatched match — so
fan_in can't be read from one query), and emits a per-file `fan_in=0` finding.
Verified end-to-end: it flags the box's decoy (a `check_login`-shaped function
nothing calls) that census/hygiene and any ranker cannot see.

**`kartikeya`'s per-file parse** (`stores/instrument_execution.py`, opt-in via
`--with-execution`): the box's load-bearing discipline — *run it, don't read it*
— as an instrument. Each source file is run through its language's PARSER
(`ast.parse`, `php -l`, `node --check`, `bash -n`) inside bite 0's sandbox; a
file that does not parse is ground truth a static reading misses. Parse, not
run: none of these EXECUTE the file's code. The file's CONTENT is shipped
base64'd into a sandbox temp (the build dir is never mounted or run in place —
strictly safer than mounting), and it is SAFE BY DEFAULT: `require_isolation=True`
raises `InstrumentUnavailable` rather than parse untrusted code with no real
sandbox, so a bwrap-less host honestly names `execution` uncovered instead of
running unprotected. Verified live on bwrap: flags a syntax-broken file, passes a
clean one, converges per-file with census/hygiene.

**`oakenscrolls-office`'s confidence mirror** (`stores/calibration.py` +
`stores/calibration_ledger.py`): the `calibration` class is NOT a per-build
instrument — calibration is a claim about the model ACROSS builds — so it is a
longitudinal ledger, not a directory measurement. A prediction is a
`(confidence, outcome)` pair: the model states P(true) for a claim it makes
while building, ground truth later settles it, and the vendored oakenscrolls math
(`brier`/`log_score`/`bins`) grades stated confidence against what happened. The
one signal that matters — `overconfidence` (mean stated confidence − hit rate) —
routes a deduped `review` nudge through `route_nudge` when the model
persistently promises more than it delivers. Verified live: 5 predictions stated
at 0.9 that hit 0.4 grade overconfidence +0.5 and route one standing
`human_required` review item; never blocks.

Each of the three degrades to `InstrumentUnavailable` when its fleet tool or
sandbox is absent — so the panel names a class covered ONLY when it truly ran.
One subtlety the wiring had to get right: an instrument that spec-loads its own
second copy of `measure_panel` gets a DISTINCT `InstrumentUnavailable` class,
which `run_panel`'s `except InstrumentUnavailable` would miss — mislabeling a
real coverage gap as "errored". The instruments now reuse the one already-loaded
`measure_panel` (and the CLI registers its `__main__` module under that name), so
"could not run" and "errored" stay honestly distinct — the sigmap lesson applied
to the panel's own plumbing.

## Where this sits in the model side

The model side is not "a model that emits `Decision`s." It is a
**refuse-a-confident-wrong-answer harness** in two layers: the **checkpoint
loop** refuses a confident wrong *decision* (built), and the **measuring panel**
refuses a confident wrong *artifact* (this). The panel is the more valuable
first model-side bite precisely because it catches the class extraction can't,
and it needs **no live model** — it runs on any build directory, exactly as the
box's tools ran on a static, fictional repo. Decision-extraction (the model
recognizing and surfacing a decision) is the next piece; when it lands, the two
layers together are the model side.

## Not in scope (this bite)

- Decision-extraction and the build loop itself (the model writing a `Plan`).
- Any judgement about a *design decision* — the panel measures artifacts; the
  checkpoint governs decisions.
- Wiring the calibration ledger's `record_prediction` into a live model's own
  stated confidences (it needs the model side's decision-extraction to have
  something to record); the ledger + math + signal stand ready, driven by CLI
  and tests until then.
