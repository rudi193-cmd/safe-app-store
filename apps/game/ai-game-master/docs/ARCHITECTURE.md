# Architecture — the reuse / inject / build map

*One picture of where every part comes from. The rule: build only the seam;
reuse the plumbing; inject the moat. Full reasoning in [`DECISION.md`](DECISION.md).*

```
                         THE TABLE (humans)
                    DM  ·  players  ·  a room of kids
                              │
                    proposes / rolls / drafts        ← the machine
                              │
   ┌──────────────────────────┴───────────────────────────┐
   │                    THE GM SEAM  (BUILD)               │
   │   propose a beat · roll dice · draft a fact           │
   │   route every "is this true now?" to a HUMAN SEAL     │
   └───┬───────────────┬───────────────┬──────────────┬────┘
       │               │               │              │
   ┌───▼───┐      ┌────▼────┐     ┌────▼────┐    ┌────▼─────┐
   │ ledger│      │  canon  │     │entities │    │ rulings  │     ← INJECT
   │ (chain│      │ (seal   │     │ (who/   │    │ (signed, │       (fleet organs,
   │  book)│      │  state  │     │  what,  │    │  super-  │        already built)
   │       │      │  machine)     │  guests)│    │  seding) │
   └───┬───┘      └────┬────┘     └────┬────┘    └────┬─────┘
    Nestor          terpsi          Nestor        Nestor
    ledger.py      sealing.py      entity.py    decision.py
    (v0.2.0)                                    + signing.py
       │
   ┌───▼──────────────────────────────────────────────────┐
   │            corpus (REFERENCE — the engine ADAPTS)     │     ← REUSE + INJECT
   │   reuse: SRD 5.1/5.2 rules text (CC-BY, attributed)   │       (Jeles corpus shape,
   │   inject: this table's canon / house rules / guests   │        conflict_scan)
   └──────────────────────────────────────────────────────┘
       │
   ┌───▼───┐
   │ dice  │  MIT roller (or 30 lines of stdlib random) — plumbing, never knowledge   ← REUSE
   └───────┘
```

## The three tiers

- **BUILD — the GM seam.** The only new code: the loop that proposes/rolls/drafts
  into `PENDING`/`DRAFT`, surfaces to the human, writes the human's
  `SEALED`/`REJECTED` row, snapshots the turn to the chained ledger, and answers
  "what's true" from canon + rulings. Scoped in `DECISION.md §7`.

- **INJECT — the moat.** `01`–`04` are pattern-ports of Nestor / terpsi organs
  that already exist and are tested. We do not rebuild them; we point them here.
  This is the fleet's largest untapped asset and its largest tax (rediscovery).

- **REUSE — the shelf.** SRD rules text (CC-BY, attribution enforced) and a dice
  roller. Commodity plumbing; the model is bad at it and a library does it for
  free.

## The two walls

1. **Blueprint / box.** This repo holds `schema/` + `bootstrap/`. A played
   campaign — `campaign.db`, the grown `corpus/`, the `keys/` — is data and lives
   in a private box (`sean-data-vault` holds the Vander game). `.gitignore`
   enforces it.

2. **Propose / seal.** The machine writes `PENDING`/`DRAFT`; a named human writes
   `SEALED`/`REJECTED`. `schema/02_canon.sql` CHECKs it at write; `verify_ledger.py
   --canon` refuses a machine seal on read. The seam may cross the first wall
   (it reads the box) but never the second.

## Proof it carries a real game

`docs/poc_vander_room.py` replays the Vander boss room through this exact schema:
proposes the *button-is-bait* ruling, drafts the guest *Bill Cipher*, seals both
under a **named DM**, snapshots each beat to the ledger, and verifies the chain —
the same run the Vander dogfood did over a JSONL file, now over `campaign.db`.
Run it: `python3 docs/poc_vander_room.py`.
