# Archived — the Forge engine's tests, extracted to rudi193-cmd/Forge

Companion archive to `stores/_forge_extracted/README.md` — read that first.

These test files exercised the store-side copies of the Forge engine's
modules before the 2026-08-11 extraction to `rudi193-cmd/Forge`. The real,
live versions of every one of these test files now live in that repo's
`tests/` directory on `master`, and that is where the engine's behavior is
actually covered going forward.

Archived here on 2026-08-18 (moved, not deleted — CLAUDE.md rule 4), alongside
the store-side module copies they tested:

- `test_calibration.py`, `test_calibration_ledger.py`
- `test_checkpoint.py`, `test_checkpoint_calibration.py`,
  `test_checkpoint_engagement.py`, `test_checkpoint_governance.py`,
  `test_checkpoint_memory.py`, `test_checkpoint_nudge.py`,
  `test_checkpoint_schedule.py`
- `test_instrument_callgraph.py`, `test_instrument_execution.py`
- `test_measure_panel.py`
- `test_model_route.py`
- `test_soil_store.py`

`test_calibration.py` also carried a byte-identity check specific to this
store's vendoring relationship — it compared `stores/calibration.py` against
`apps/oakenscrolls-office/calibration.py` line for line. That relationship no
longer exists on this side of the extraction (the vendored math now lives in
`rudi193-cmd/Forge`'s `forge/calibration.py`, not here), so the test could not
be updated in place; it is archived along with everything else in this
directory rather than deleted.

None of these files were part of `.github/workflows/store-ci.yml`'s curated
`gates` pytest list, the `app-tests` matrix, or the `forge-tests` job (which
covers the unrelated `apps/the-forge` sandbox-build app) — so archiving them
changes no CI command. They only ever ran via a bare `pytest tests/`.

Two store-side tests were **not** archived because they are not duplicates:
`tests/test_forge_build.py` (tests `stores/forge_build.py`, which stays — see
the module-side README) and `tests/test_readiness_corpus.py`/
`tests/test_readiness_drift.py` (the store's own readiness seam, which
consumes the Forge package's `measure_panel` module but is not itself part of
the Forge engine).
