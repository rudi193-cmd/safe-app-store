#!/usr/bin/env bash
# sandbox.sh — a disposable, repo-local playground for stupid tests.
#
# Everything lives in ./.sandbox/ (gitignored): its own ledger, its own fake
# almanac-data clone, seeded predictions with a deliberately overconfident
# track record. Your real ledger in ~/.willow is never touched.
#
# Usage:
#   ./sandbox.sh              seed (idempotent) + launch the TUI
#   ./sandbox.sh --web        seed + launch the web mirror instead
#   ./sandbox.sh --seed-only  seed and exit (CI / smoke tests)
#   rm -rf .sandbox           burn it down; next run reseeds fresh
#
# Override venv location:  OAKENSCROLL_VENV=~/some/venv ./sandbox.sh

set -euo pipefail
cd "$(dirname "$0")"

SANDBOX="$PWD/.sandbox"
export OAKENSCROLL_DB="$SANDBOX/office.db"
export ALMANAC_DATA_ROOT="$SANDBOX/almanac-data"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/oakenscrolls-office}"
VENV_DIR="${OAKENSCROLL_VENV:-$APP_DATA/.venv}"
if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  echo "Creating venv at $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python3"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

"$PY" - <<'SEED'
import json, os, time
from pathlib import Path

sandbox = Path(os.environ["OAKENSCROLL_DB"]).parent
if (sandbox / "office.db").exists():
    print(f"sandbox already seeded at {sandbox} — rm -rf .sandbox to reset")
    raise SystemExit(0)

# --- a fake local climate-almanac clone (catalog, don't host — or data) ---
repo = Path(os.environ["ALMANAC_DATA_ROOT"]) / "climate-almanac"
(repo / ".git" / "refs" / "heads").mkdir(parents=True)
(repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
(repo / ".git" / "refs" / "heads" / "main").write_text("5andb0x" + "0" * 33 + "\n")
(repo / "catalog.json").write_text(json.dumps({"name": "climate-almanac", "entries": [
    {"id": "berkeley-earth-temperature", "title": "Berkeley Earth Surface Temperature",
     "description": "Independent global land and ocean surface temperature analysis",
     "publisher": "Berkeley Earth", "topics": ["temperature", "global"],
     "source": {"canonical_url": "https://berkeleyearth.org/data/"},
     "status": "live", "license": "CC-BY-NC-SA-4.0"},
    {"id": "noaa-billion-dollar-disasters", "title": "Billion-Dollar Disasters",
     "description": "US weather and climate disasters exceeding one billion dollars",
     "publisher": "NOAA", "topics": ["disasters", "weather"],
     "source": {"canonical_url": "https://example.gov/disasters"},
     "status": "frozen", "license": "public-domain"},
]}, indent=2))

import office_db as db
import almanac_seam

now = int(time.time())
H, D = 3600, 86400

# --- a track record that tells a story: says ~80%, hits ~55% ---
graded = [
    ("the fleet demo works first try", 0.9, False),
    ("PR #77 merges within a day", 0.85, True),
    ("Gerald stays headless through July", 0.97, True),
    ("the binder rewrite starts this month", 0.8, False),
    ("no new bugs in the vault this week", 0.75, False),
    ("the store hits 25 apps by August", 0.7, True),
    ("Loki files a handoff without being asked", 0.6, False),
    ("it rains on the weekend", 0.65, True),
    ("the willow migration needs a rollback", 0.55, False),
    ("Copenhagen remains an orange", 0.99, True),
]
for claim, conf, outcome in graded:
    db.resolve(db.state_claim(claim, conf), outcome)

# one graded WITH a citation from the fake almanac (shows the dagger)
pid = db.state_claim("2026 sets a global surface temperature record", 0.8)
hit = almanac_seam.search("temperature")[0]
db.resolve(pid, True, evidence=almanac_seam.citation(hit, note="sandbox seed"))

# one voided, one revised-then-open, and live dew: two due now
db.void(db.state_claim("the meaning of the test is discovered", 0.5), "unfalsifiable")
wobble = db.state_claim("next quarter's plan survives contact with reality", 0.75, due=now + 30 * D)
db.revise(wobble, 0.55)
db.state_claim("the sandbox survives the stupid test", 0.5, due=now - 2 * H)
db.state_claim("coffee runs out before the experiment does", 0.8, due=now - 1 * H)
db.state_claim("this claim is graded within three days", 0.7, due=now + 3 * D)

n = len(db.ledger())
print(f"seeded {n} predictions into {sandbox}")
print("the record says ~80% and delivers ~55% — Oakenscroll has notes")
SEED

echo "" >&2
echo "SANDBOX (disposable — rm -rf .sandbox to reset):" >&2
echo "  ledger:   $OAKENSCROLL_DB" >&2
echo "  almanacs: $ALMANAC_DATA_ROOT (fake climate-almanac, 2 sources)" >&2
echo "" >&2

case "${1:-}" in
  --seed-only) exit 0 ;;
  --web)       exec "$PY" web.py ;;
  *)           exec "$PY" app.py ;;
esac
