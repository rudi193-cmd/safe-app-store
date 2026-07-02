# Civics Check

America's 250th civics fair — offline quizzes, pavilion browsing, and the USCIS naturalization test bank. Pure Python; no accounts, no network required after install.

**Runs on its own.** You do not need the SAFE App Store monorepo — copy this directory anywhere, or install with pip.

## Install (standalone)

From this directory (`apps/civics-check` in the monorepo, or a copy of that folder):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
civics-check                       # console script → app.py
```

Or use the launcher (creates `~/.willow/apps/civics-check/.venv` automatically):

```bash
./dev.sh                           # fair TUI (default)
./dev.sh --cli                     # stdlib fair map only
```

## Run (standalone)

| What | Command |
|------|---------|
| **Primary entry** | `python3 app.py` — SAFE manifest `entry_point`; launches Textual fair when installed, else CLI fair map |
| **CLI fair only** | `python3 app.py --cli` |
| **TUI directly** | `python3 tui.py` |
| **After pip install** | `civics-check` (same as `python3 app.py`) |

Rebuild catalog after editing sources:

```bash
python3 scripts/build_catalog.py
```

## Monorepo (optional)

If you have the full [safe-app-store](https://github.com/rudi193-cmd/safe-app-store) checkout:

```bash
make install app=civics-check
make run app=civics-check          # runs app.py in apps/civics-check
```

## What you get

- **Fair map** — parchment lanes (Citizenship Court, Statehouse Row, Founders Hall, …) with pavilion tents
- **Naturalization quiz** — 10 questions, 6 of 10 to pass (same rule as USCIS civics)
- **Speed round** — 60 seconds against the full bank
- **State matchups** — capitals and admission order
- **Timeline sort, quote match, colonies flashcards, amendment explorer**, and more
- **Local progress** — missed-question tracking and scores in `civics_check.db` (dev tree) or `~/.willow/apps/civics-check/` (pip install)

## Keyboard (TUI)

| Key | Action |
|-----|--------|
| `↑` / `↓` or `j` / `k` | Move between lanes / pavilions |
| `Enter` | Open selected pavilion |
| Type answer + `Enter` | Submit |
| `Esc` | Back to fair map |
| `q` | Quit |
| `1776` | Liberty Bell commentary |

## Data workflow

**Never hand-edit `data/catalog.json`.** It is compiled output.

1. Edit JSON under `data/sources/` (questions, presidents, numbers, links, fair schedule, …)
2. Rebuild: `python3 scripts/build_catalog.py`
3. Test: `python3 -m unittest discover -s tests -v`

## Project layout

```
app.py              Primary entry (SAFE) — TUI when Textual present, else fair CLI
tui.py              Textual fair map + stage (optional direct launch)
tui_art.py          Hero band, curtains, ASCII ceremony
engine.py           Catalog facade shared by CLI and TUI
bell.py             Liberty Bell narrator + Joan Stark banner art
db.py               Local SQLite scores / missed questions
civics/
  catalog.py        Load compiled catalog
  paths.py          Resolve app root + data/ (dev, editable, wheel)
  scoring.py        Answer matching
  session.py        Activity state machine
scripts/
  build_catalog.py  Compile sources → catalog.json
data/
  sources/          Authoritative JSON (edit these)
  catalog.json      Generated — do not edit
tests/
dev.sh              Standalone launcher (venv + catalog + run)
pyproject.toml      pip install -e . / civics-check console script
safe-app-manifest.json
```

## SAFE manifest

Registered as `civics-check` in the SAFE App Store monorepo (`entry_point`: `app.py`). Permissions: `file_write` for local SQLite only.

## License

MIT — see [LICENSE](LICENSE).

ΔΣ=42
