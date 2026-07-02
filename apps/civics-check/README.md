# Civics Check

America's 250th civics fair — offline quizzes, pavilion browsing, and the USCIS naturalization test bank. Pure Python; no accounts, no network required after install.

## Quick start

**Recommended** — self-contained venv, rebuilds catalog, launches the fair:

```bash
cd apps/civics-check
./dev.sh
```

From the monorepo root (uses repo `.venv-dev` after install):

```bash
make install app=civics-check
make run app=civics-check          # fair TUI when Textual is installed
```

| Surface | Command | Dependencies |
|---------|---------|--------------|
| **TUI fair** (default) | `./dev.sh` or `make run` | `textual` (`requirements.txt`) |
| **CLI fair map** | `./dev.sh --cli` or `python3 app.py --cli` | stdlib only — same lanes, pavilions, and activities as the TUI |

## What you get

- **Fair map** — parchment lanes (Citizenship Court, Statehouse Row, Founders Hall, …) with pavilion tents
- **Naturalization quiz** — 10 questions, 6 of 10 to pass (same rule as USCIS civics)
- **Speed round** — 60 seconds against the full bank
- **State matchups** — capitals and admission order
- **Timeline sort, quote match, colonies flashcards, amendment explorer**, and more
- **Local progress** — missed-question tracking and scores in `civics_check.db` (never leaves your machine)

## Keyboard (TUI)

| Key | Action |
|-----|--------|
| `↑` / `↓` or `j` / `k` | Move between lanes / pavilions |
| `Enter` | Open selected pavilion |
| Type answer + `Enter` | Submit |
| `Esc` | Back to fair map |
| `q` | Quit |
| `109` | Easter egg |
| `1776` | Liberty Bell commentary |

## Data workflow

**Never hand-edit `data/catalog.json`.** It is compiled output.

1. Edit JSON under `data/sources/` (questions, presidents, numbers, links, fair schedule, …)
2. Rebuild:

   ```bash
   python3 scripts/build_catalog.py
   ```

3. Run tests:

   ```bash
   python3 -m unittest discover -s tests -v
   ```

### Current officeholders

Questions about “the President now”, party, Speaker, and Vice President are pinned in `data/sources/current_officials.json`. Update that file when leadership changes, then rebuild the catalog. The build script fails if placeholder answers remain in the naturalization bank.

## Project layout

```
app.py              CLI menu (stdlib)
tui.py              Textual fair + stage
tui_art.py          Hero band, curtains, ASCII ceremony
engine.py           CLI helpers over catalog
civics/
  catalog.py        Load compiled catalog
  scoring.py        Answer matching
  session.py        Activity state machine
scripts/
  build_catalog.py  Compile sources → catalog.json
data/
  sources/          Authoritative JSON (edit these)
  catalog.json      Generated — do not edit
tests/
```

## SAFE manifest

Registered as `civics-check` in the SAFE App Store monorepo. See `safe-app-manifest.json` for permissions (`file_write` for local SQLite only).

## License

MIT — see [LICENSE](LICENSE).

ΔΣ=42
