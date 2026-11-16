#!/usr/bin/env bash
# provision.sh — stand up an EMPTY campaign box from this blueprint.
#
# The blueprint (this repo) is schema + structure. This script provisions a
# populated-but-empty BOX at a path you choose. The box holds a real campaign —
# its ledger, its canon, its guests, the family's game — and it is NEVER
# committed back to this repo (see the repo .gitignore). Repo = how to build a
# campaign vault. Box = the actual played campaign that stays home.
#
# Usage:
#   bootstrap/provision.sh /path/to/box
#
# What it does (idempotent):
#   1. create the box directory layout
#   2. apply the owned SQLite schemas into a single campaign.db at the box root:
#        01_ledger.sql    the hash-chained turn log (the book of record)
#        02_canon.sql     sealed facts — the human-seals-canon state machine
#        03_entities.sql  PCs / NPCs / places / items / guests
#        04_rulings.sql   the signed decision graph (house rules, rule-of-cool)
#      05_corpus.reference.sql is NOT applied — it is REFERENCE ONLY (the engine
#      adapts to whatever corpus it is pointed at), the same way
#      willow-data-vault leaves 05_knowledge.reference.sql to the code.
#   3. verify the (empty) ledger chain as a gate — a no-op pass on a fresh box,
#      a REFUSAL on a re-run against a box whose chain is broken
#   4. print next steps
#
# It does NOT populate any campaign data or install a corpus. Blueprint stands
# up the box; the table fills it.

set -euo pipefail

BOX="${1:?usage: provision.sh /path/to/box}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SCHEMA="$HERE/schema"
DB="$BOX/campaign.db"

echo "==> provisioning campaign box at: $BOX"
mkdir -p "$BOX"/{corpus,keys}
chmod 700 "$BOX"

# Apply a schema to a SQLite DB. Prefer the sqlite3 CLI; fall back to Python's
# stdlib sqlite3 so the blueprint works without the CLI installed.
if command -v sqlite3 >/dev/null 2>&1; then
  _apply() { sqlite3 "$1" < "$2"; }
elif command -v python3 >/dev/null 2>&1; then
  _apply() { python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.executescript(open(sys.argv[2]).read()); c.close()' "$1" "$2"; }
else
  echo "    !! no sqlite3 CLI and no python3 — apply schema/*.sql yourself"; exit 1
fi

for ddl in 01_ledger.sql 02_canon.sql 03_entities.sql 04_rulings.sql; do
  echo "    schema: $ddl -> campaign.db"
  _apply "$DB" "$SCHEMA/$ddl"
done
chmod 600 "$DB"

# Tamper-evidence gate: verify the ledger hash chain (schema/01_ledger.sql's
# prev_hash/hash columns; a pattern port of nestor/ledger.py). On a fresh box
# the table is empty and this is a no-op pass. On a re-run against an existing,
# already-played box, a broken chain here REFUSES to continue (set -e
# propagates the nonzero exit) rather than standing up alongside a book that
# has been quietly rewritten.
echo "    verifying ledger hash chain (tamper-evidence)..."
python3 "$HERE/bootstrap/verify_ledger.py" "$DB" --canon

cat <<EOF

==> campaign box provisioned (empty). Next:
    * point your GM engine at:   $DB
    * grow a corpus under:       $BOX/corpus/   (the SRD reader + your notes)
      — reuse-tier rows (SRD, CC-BY) may be shared; inject-tier rows (this
        table's canon, house rules, guests) are DATA and stay in this box.
    * a signing key for rulings/seals lives under: $BOX/keys/  (0600, never git)

    This box holds a campaign and its keys. It must NEVER be committed to the
    ai-game-master blueprint repo — only to a private box/vault of your own
    (the way sean-data-vault holds the Vander campaign).
EOF
