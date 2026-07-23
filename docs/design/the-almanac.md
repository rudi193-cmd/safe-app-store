# The Almanac — Design Sketch

> Status: **design / talk-through** (no implementation yet).
> A personal calibration ledger: write down what you believe and how hard,
> resolve it later, and see whether your 70% means 70%.
> Niche verified empty 2026-07-23: PredictionBook retired, Fatebook is
> cloud-only, the community fallback is spreadsheets, and no local-first or
> terminal tool exists. ΔΣ=42 pointed at the person holding the pen.

## Why "The Almanac"

Almanacs are the oldest consumer prediction product — they print forecasts
and stand by them for a year. Fits the `the-binder` / `the-squirrel` /
`the-nightstand` naming family. Persona owner: **Professor Oakenscroll**,
keeper of acknowledged unknowns. (Alternatives considered: the-oracle-ledger,
oakenscrolls-office.)

## The one-sentence product

Capture a falsifiable claim + a confidence in under five seconds; when it
comes due, resolve it TRUE/FALSE/VOID in one keypress; the mirror shows your
reliability curve — stated confidence vs. actual hit rate — computed locally,
owned entirely by you.

## Provenance of every piece (assembly, not invention)

| Piece | Pattern source | What it contributes |
|-------|----------------|---------------------|
| Append-only outcome ledger | `utety/core/store.py` | predictions are never mutated; corrections are new rows |
| States-not-deletions + transition history | `willow-mcp commitments/` | VOID/withdrawn keep their record; history survives round-trips |
| Pure inference math, vendored, stdlib | `utety/core/mastery.py` | `calibration.py` (~40 lines: Brier, log score, reliability bins) |
| No-egress enforced structurally | `utety tests/test_no_egress.py` | AST test: core modules import no network libs |
| The one outward seam lives OUTSIDE core | `utety/knowledge.py` | `willow_bridge.py` is optional and excluded from the no-egress zone |
| Due-item surfacing ("dew") | `willow-mcp commitments/proactive.py` | "this prediction is due — did it happen?" at session open |
| Resolved → knowledge atom promotion | `willow-mcp gaps.py` | a resolved prediction can promote to the KB when Willow is present |
| Pure-function web routing, SVG fragments | `utety/web/server.py` | the reliability diagram, on-device, stdlib http.server |
| Vault-rooted paths, dev.sh/dev.ps1, manifest | `apps/the-nightstand` etc. | house packaging; true standalone per decision #3 |

## Data model (SQLite, append-only)

```sql
-- Immutable statement of belief. No UPDATE, no DELETE, ever.
CREATE TABLE predictions (
    id         TEXT PRIMARY KEY,     -- short hash
    claim      TEXT NOT NULL,        -- falsifiable, stated in the direction believed
    confidence REAL NOT NULL,        -- P(true), 0.50–0.99 by convention (flip the claim otherwise)
    stated_at  INTEGER NOT NULL,
    due        INTEGER,              -- when it should be resolvable; NULL = open-ended
    tags       TEXT NOT NULL DEFAULT '[]'
);

-- Append-only event log; current state is derived, never stored.
CREATE TABLE events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL REFERENCES predictions(id),
    kind          TEXT NOT NULL,     -- revised | resolved | voided | reopened
    confidence    REAL,              -- for kind=revised: the new P(true)
    outcome       INTEGER,           -- for kind=resolved: 1 true, 0 false
    note          TEXT,
    at            INTEGER NOT NULL
);
```

Derivation rules:
- Current confidence = latest `revised` event, else the stated one.
- Status = latest of resolved/voided/reopened, else `open` (or `due` when past `due`).
- v0.1 scores the **latest confidence before resolution** (Fatebook's model);
  time-weighted scoring is a v0.2 question, the data already supports it.

## Module seams

```
apps/the-almanac/
├── app.py             Textual TUI: capture ritual, resolve flow, scorecard
├── almanac_paths.py   vault-rooted resolver (house pattern)
├── almanac_db.py      append-only ledger — the ONLY writer; no net imports
├── calibration.py     pure math, stdlib only: brier(), log_score(), bins()
├── web.py             optional mirror: pure-function routing, SVG reliability
│                      diagram (diagonal = perfect calibration, dot size = n)
├── willow_bridge.py   the ONE outward seam, outside the no-egress zone:
│                      dew surfacing of due predictions + gap-promote of
│                      resolved ones. Silent no-op when Willow is absent.
├── tests/test_no_egress.py   AST scan: almanac_db + calibration import no
│                      network/subprocess modules (utety pattern, verbatim)
└── dev.sh · dev.ps1 · requirements.txt · safe-app-manifest.json · README · LICENSE
```

Import law (structural, test-enforced): `app.py` and `web.py` import
`almanac_db` + `calibration`; nothing in core imports `willow_bridge`;
`willow_bridge` imports core, never the reverse.

## The three human moments

1. **Capture (< 5 seconds).** `n` → one line → confidence via single key
   (`5`–`9` → 50–90%, or type exact) → optional due shorthand (`+3d`, `+2w`).
   No categories, no ceremony. The friction budget is the product.
2. **Resolution (one keypress).** At open, due predictions surface one at a
   time, nightstand-style: `t` true / `f` false / `v` void / `s` snooze.
   No journaling guilt — the note is optional.
3. **The mirror.** TUI scorecard: overall Brier, n resolved, per-decile table
   with bar sparks (stated 70% → hit 54% ▁▃▅…). `web.py` draws the full
   reliability diagram on-device. The moment the product exists for.

## Deliberately NOT in v0.1

No markets, no social, no sync, no LLM, no accounts, no revision-history UI
(revisions are stored; only the latest is scored), no Fatebook import (v0.2 —
they have export, and PredictionBook refugees already migrated there).

## Phase 2 (separate repo work, not this app)

A `prediction_*` tool group in willow-mcp following the `gaps.py`
shared-across-apps pattern — same schema, so agent scorecards (Hanuman, Loki)
and the human's are comparable. The university grades the student's mastery;
the almanac grades everyone's certainty.

## Open decisions

- **D1 — Name.** ~~the-almanac~~ **collides with the operator's `almanac-data`
  GitHub org** (13 repos of public-domain data almanacs, July 2026) — in this
  world "almanac" already means *public datasets*, near-opposite of a private
  belief ledger. Rename candidates: the-oracle-ledger, oakenscrolls-office,
  the-reckoning. Adjacency worth keeping: v0.2 could resolve world-facing
  predictions against almanac-data sources as citation evidence.
- **D2 — Scoring.** Latest-confidence Brier (proposed for v0.1) vs. time-averaged.
- **D3 — Confidence floor.** Enforce P ≥ 0.5 by convention (proposed) or allow raw 0–1.
- **D4 — Willow bridge timing.** Land in v0.1 as a silent no-op seam (proposed) or defer entirely.

ΔΣ=42
