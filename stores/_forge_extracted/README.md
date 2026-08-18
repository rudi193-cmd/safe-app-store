# Archived — extracted to rudi193-cmd/Forge

The 17 modules in this directory are **archived duplicates**, not live code.
CLAUDE.md rule 4 governs: *"Archive, don't delete."*

## What happened

The Forge engine (the checkpoint loop, the measuring panel, and their
supporting modules — the "model side," per `docs/design/the-forge-promotion.md`)
was **extracted** out of this store's `stores/` monorepo into its own standing
repo, **`rudi193-cmd/Forge`**, on **2026-08-11**. The extraction was performed
with `tools/extract_forge_pkg.py` (still in this repo, still re-runnable —
it reproduces the pushed `forge/` tree byte-identically) and landed on the
Forge repo's default branch (`master`) via commits `ada98e7` (enroll),
`a3a8682` (verified_by=rudi193 recorded), and `c2c44d4` (§0.2 witnessed
mechanism), plus a `claude/forge-sonnet-agents-analysis-i2npad` branch
carrying further doc work on top of `master`.

At extraction time, `promote_check` passed every gate against the pushed
Forge tree except one: `host_repointed`, held because the store-side copies
of these modules were never removed and this store's own `stores/`
directory still shadowed the promoted package. `stores/python/stored/the-forge.json`
also still read `state: building` long after the engine had actually landed
and been witnessed elsewhere.

**On 2026-08-18**, the store-side duplicates below were archived here (moved,
not deleted) to close that gap: the host is now a consumer of
`rudi193-cmd/Forge`, not a second copy of it. This directory is that
archival — see each promoted module's real, current source at
[`rudi193-cmd/Forge`](https://github.com/rudi193-cmd/Forge), `forge/<name>.py`
on `master`.

## What is canonical now

`rudi193-cmd/Forge` (branch `master`) is the canonical source for:

- `calibration.py`, `calibration_ledger.py`
- `checkpoint.py`, `checkpoint_calibration.py`, `checkpoint_engagement.py`,
  `checkpoint_governance.py`, `checkpoint_memory.py`, `checkpoint_nudge.py`,
  `checkpoint_schedule.py`
- `friction_floor.py`, `human_loop.py`
- `instrument_callgraph.py`, `instrument_execution.py`
- `measure_panel.py`
- `model_egress.py`, `model_route.py`
- `soil_store.py`

Anything in this store that still needs one of these (for example,
`stores/readiness_corpus.py`'s `assess` CLI, which measures the panel's
coverage) imports the real `forge` package rather than loading a file out of
this archive. See `stores/requirements.txt` for the install line.

## What is *not* archived here, on purpose

`stores/forge_build.py` looks related by name but is **not** a duplicate and
was **not** moved. It is store-side glue — bite 0's spine — that wires
together `apps/the-forge` (a separate, still-in-playground sandbox/build app;
`the_forge` Python package under `apps/the-forge/src/`), `stores/sap_gate.py`
(D4 signing), and `stores/seam.py` (the D3/D4/D5 crossing pipeline). None of
those three things live in `rudi193-cmd/Forge` — it has no counterpart there
— so `forge_build.py` stays exactly where it is.

## Reopen condition

If a future edit needs to change the *behavior* of any module in this
directory, that edit belongs in `rudi193-cmd/Forge`, not here. A change made
only to the archived copy here has no effect on anything that runs.
