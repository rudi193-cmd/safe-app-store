# ai-game-master

**The blueprint for an AI Game Master's campaign vault — schemas and bootstrap
only. Never a campaign.**

This repo is how you *build* the box an AI Game Master keeps its world in. It is
not, and must never become, a world. The running campaign — its ledger, its
sealed canon, its guests, a family's seven-month game — lives in a private box
and is **never committed here.**

> Repo = *how to build a campaign vault.* &nbsp; Box = *the actual played campaign that stays home.*

This is the [`willow-data-vault`](https://github.com/rudi193-cmd/willow-data-vault)
pattern applied to game-mastering: a blueprint repo that refuses data, and a box
that holds it. The Vander valley campaign that proved this out lives in a private
box ([`sean-data-vault`](https://github.com/rudi193-cmd/sean-data-vault)), not in
this repo.

## The thesis

An AI Game Master is **not a rules referee.** It is a **yes-and bookkeeper.**

A campaign the kids actually loved took seven months — once a week, an hour a
session, a room of eight-to-ten-year-olds. The *plot* is the part a machine
renders in seconds. The seven months were the **value**: the room, the weekly
ritual, the arguing about whether to press the button. A machine's job is not to
compress that to seconds — it is to carry the **toil** (the stat-tracking, "what
did we decide three sessions ago", the tamper-proof record of what's true) so
the human at the head of the table has more room for the part that was worth
seven months.

That table loosened the dice, let role-play count for more than the mechanics
allowed, and welcomed **Beetlejuice, the Sandworm, and Bill Cipher** into a D&D
valley. That is exactly what LLMs are *good* at (improv, narrative, incomplete
information) and *bad* at (rigid rule adjudication). So the engine leans into it:

- **The machine proposes, rolls, and remembers.** It never confirms.
- **A named human at the head of the table seals canon.** A player proposes
  "Bill Cipher enters the valley"; the DM seals it; the ledger records
  *"Bill Cipher — guest, sealed by \<DM\>, session N."* Joyful, non-standard,
  human-authored canon — auditable and un-retconnable.
- **The book is tamper-evident.** Edit any past turn and the hash chain refuses.

"The human seals canon" is not a feature. It is the thesis. See
[`docs/DECISION.md`](docs/DECISION.md) for build-vs-reuse, the CC-BY licence
wall, and the differentiator in full.

## What's in the blueprint

```
schema/
  01_ledger.sql            # hash-chained turn log — the book of record   (Nestor ledger)
  02_canon.sql             # PENDING/DRAFT/SEALED/REJECTED — human seals   (terpsi sealing)
  03_entities.sql          # PCs / NPCs / places / items / GUESTS          (Nestor entity)
  04_rulings.sql           # signed decision graph — house rules, rule-of-cool (Nestor decision+signing)
  05_corpus.reference.sql  # injectable knowledge (SRD/persona) — REFERENCE ONLY, the engine ADAPTS (Jeles corpus)
bootstrap/
  provision.sh             # stand up an empty campaign box from the schemas
  verify_ledger.py         # walk the ledger hash chain; --canon refuses a machine seal; a break REFUSES
```

Four schemas are **owned** — pattern-ported from the fleet's already-built
organs (attributed in each file's header, no code copied verbatim). The fifth is
**reference only**: the corpus is whatever a table grows, so the engine resolves
its shape at runtime and never assumes this DDL against an existing corpus — the
same way willow-data-vault leaves the knowledge base to the code.

### The hash chain (tamper-evidence)

`01_ledger.sql`'s `prev_hash`/`hash` columns are a hash chain over the turn
stream, pattern-ported from Nestor's hash-chained ledger (`nestor/ledger.py`,
Apache-2.0, `github.com/rudi193-cmd/Nestor`, pinned `v0.2.0`). Editing a past
turn breaks the next turn's `prev_hash` on re-hash —
`bootstrap/verify_ledger.py` is the verifier, and `provision.sh` runs it after
applying the schema, so a broken chain **refuses to provision** (nonzero exit)
instead of silently standing up alongside a book someone rewrote. Run
`bootstrap/verify_ledger.py --self-test` to watch the guard build a clean chain,
verify it, tamper a turn, and confirm that IS refused.

Covenant: this chain adds tamper-*evidence*. It seals nothing and grants no
authority — a clean chain says the turns were not altered after being written,
not that anything in them was approved. Approval is a **seal**, and only a named
human writes one (`02_canon.sql`; enforced by `verify_ledger.py --canon`).

## Provision an empty box

```bash
bootstrap/provision.sh /path/to/box      # creates dirs, applies schemas, verifies the chain
# point your GM engine at /path/to/box/campaign.db
# grow a corpus under /path/to/box/corpus/  (ship the SRD reader; the corpus stays home)
```

## The box layout (never in git)

```
<box>/                    # 0700
  campaign.db             # ledger + canon + entities + rulings (the played game)
  corpus/                 # the injectable knowledge the GM reads (SRD reader + house notes)
  keys/                   # Ed25519/HMAC signing keys for rulings & seals (0600)
```

`campaign.db`, the corpus, and the keys are **data**. They live in the box and
stay home — see `.gitignore`, whose first rule is that none of them may ever be
committed to this blueprint.

## Provenance

Built from organs the fleet already grew — the value is in *not* rebuilding
them:

| Blueprint piece | Ported from | What it gives |
|---|---|---|
| `01_ledger.sql` + verifier | Nestor `ledger.py` (v0.2.0) | tamper-evident book of record |
| `02_canon.sql` | terpsi-music `records/sealing.py` | the human-seals-canon state machine |
| `03_entities.sql` | Nestor `entity.py` | one referent per name; the guest lane |
| `04_rulings.sql` | Nestor `decision.py` + `signing.py` | signed, superseding house rules |
| `05_corpus.reference.sql` | Jeles corpus/`conflict_scan` | a search seam over injectable knowledge |

Reuse tier (the open shelf): the **SRD 5.1 / 5.2** rules text (CC-BY 4.0) and
MIT dice plumbing. Inject tier (the moat): memory, continuity, and sealed-canon
authority — the parts the fleet already holds and points outward.

Licensed Apache-2.0, matching Nestor.
