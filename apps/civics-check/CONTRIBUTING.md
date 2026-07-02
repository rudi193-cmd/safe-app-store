# Contributing to Civics Check

Thanks for helping improve the fair. This app lives entirely in `apps/civics-check/`.

## Scope

- One concern per PR when possible (scoring fix, new pavilion data, TUI polish).
- Do not commit `civics_check.db`, `__pycache__/`, or generated SVG previews under `art/` unless they are intentional assets.
- Changes outside `apps/civics-check/` belong in separate PRs unless required for store registration (`catalog.json` at repo root).

## Development setup

```bash
cd apps/civics-check
pip install -r requirements.txt   # or ./dev.sh creates its own venv
make catalog                      # rebuild data/catalog.json
make run                          # fair TUI
make cli                          # stdlib menu only
python3 -m unittest discover -s tests -v
```

The CLI runs with zero pip dependencies. The TUI needs Textual 0.50+.

## Data rules

1. **Edit `data/sources/*.json`** — not `data/catalog.json`.
2. Run `python3 scripts/build_catalog.py` after source changes.
3. Update `data/sources/current_officials.json` when federal leadership changes (President, VP, Speaker, party).
4. Keep USCIS question text faithful to the official bank; add context in `body` / `context` fields, not by altering the graded answer unless the official answer changed.

## Pull requests

- Run the full test suite before opening.
- Update README if run commands, keys, or data workflow change.
- Note in the PR if you rebuilt `data/catalog.json` (expected for any source edit).

## Code style

Match surrounding code: small functions, explicit names, minimal scope. Prefer tests for grading, session logic, and hero rendering — behavior that must not regress.

## Privacy

All progress stays in local SQLite (`civics_check.db`). Do not add telemetry, remote APIs, or cloud sync without an explicit SAFE manifest update and user consent.
