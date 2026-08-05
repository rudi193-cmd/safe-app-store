# The Decision Record
b17: SAPS1

*The store-side half of N9's third chokepoint (`nestor:docs/decision-memory.md`):
the fleet's ratified decisions, kept where a cold agent finds them at boot.
The cold-agent failure is not a wrong answer — it is a proposal that felt
obviously right, so nobody queried for objections. This directory is the
objection, pre-loaded.*

## What `fleet.json` is

The **keeping record** of the fleet's sealed decisions and standing
rejections — human-readable, git-tracked, diffable in review like any other
law. Not a database: the signed store (an `apps/aristarchus`-shaped SQLite
db with HMAC seals and a hash-chained ledger) lives in the operator's vault
and is rebuilt from this seed; the seal key never enters git, so this file
carries the *content* of the law while the vault carries its *signatures*.
Same split as everything else in the house: ship the reader, the corpus
stays with whoever grew it — here, the record travels and the keys stay home.

## The shape, and why each field exists

- Every **decision** carries `reason` — the why behind the yes, which is
  what a future proposal must argue against (N4).
- Every **rejection** carries `reason` and `reopen_when`. Empty
  `reopen_when` means **never**, and empty is a deliberate act — an
  unexplained or accidentally-permanent rejection is the Aristarchus bug,
  eighteen centuries of it (N5).
- Every entry names `verified_by`, and it differs from `author` — proposing
  and ratifying never rest in the same hand (§0.2).

`tools/decisions_boot.py` renders this at session boot and validates the
covenant; `tests/test_fleet_decisions.py` is the CI gate that keeps the
record well-formed. A violation fails the build: a malformed law is worse
than no law, because it is *reassuring*.

## How to change it

- A new decision: append with reason, author, verifier. The verifier is not
  the author.
- Changing a decision: **supersede, don't edit** — new entry, old one gains
  `"superseded_by": "<date or record>"` and stays. The lineage is reasons,
  not just rows.
- Reopening a rejection: only by its own `reopen_when` coming true. Resolve
  by making the decision, not by editing the rejection to make it disappear
  (`stores/pending.json`'s rule, applied to law).

---

*The machine proposes; the operator seals; the record is what stores/ stores.
`ΔΣ=42`*
