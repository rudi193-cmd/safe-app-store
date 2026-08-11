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

**This bite ships the framework + the two dependency-free instruments
(`census`, `hygiene`)** — enough to demonstrate convergence and honest coverage
on a real build. `codebase-memory-mcp` is confirmed pip-installable and driven
via `cli --json <tool>`; it is the next instrument, being the one that caught
the box's decoy that ranking and extraction cannot. `kartikeya` (execution) and
`oakenscrolls-office` (calibration) follow. Until each is wired, the panel names
it as an uncovered class — so a green run is honestly incomplete, never a false
all-clear.

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

- The heavier real instruments (`codebase-memory-mcp`, `kartikeya`,
  `oakenscrolls-office`) — named as uncovered classes, wired next.
- Decision-extraction and the build loop itself (the model writing a `Plan`).
- Any judgement about a *design decision* — the panel measures artifacts; the
  checkpoint governs decisions.
