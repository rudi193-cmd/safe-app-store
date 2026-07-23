# fleet-presence

The stdlib-only, egress-free **one-memory seam**: *let an app announce itself
into the shared willow store, and see the rest of the fleet — without importing
any of them.*

## Why this exists

A code-graph audit of the store (July 2026) found the apps aren't
interconnected — they're **silently duplicated**: `personas.py` had drifted
into 10 distinct versions across 11 copies, `safe_integration.py` into 17 of
17. Each app carries a private copy of the others and sits in its own SQLite
silo. The catalog's "ecosystem" pipelines were narrative-only (vision-doc E3).

This is the missing shared axis, extracted once (the `libs/subject-consent`
pattern — *built once, here*). It is the code behind the north-star thesis:

> **one desk, one memory, many tools** — apps never wire to each other, they
> read and write shared atoms.

An app calls `announce()` to publish a compact **presence atom** (its id, a
one-line summary, small counts) into the shared store's `fleet` collection, and
`roster()` to see everyone else present. That's the whole surface.

## Discipline

- **Standalone-safe (store decision #3).** Stdlib only, no `willow_mcp` import,
  no network. With no shared store reachable, every call is a **silent no-op** —
  an app that ships this still runs with zero backend.
- **Receipts, not recording.** A presence atom carries only facts an app
  chooses to publish — never record bodies (a content leak is refused).
- **States, not deletions.** `withdraw()` soft-deletes; the row is kept.
- **Willow-native.** Atoms are written in willow's own `records` schema into
  the `fleet` collection, so the live willow store tools
  (`store_search`/`store_get`) read the very same atoms an app published.

## Use

```python
import fleet_presence as fp

# on startup — guarded, silent if there's no shared memory
fp.announce("the-nightstand", "3 down, 1 heavy", {"down": 3, "heavy": 1})

# any app can see the fleet without importing another app
for app in fp.roster():
    print(app["app_id"], "—", app["summary"])
```

The shared store is `WILLOW_STORE_ROOT` (what every store app already uses),
falling back to `~/.willow/store` only if it already exists.

## Tests

    python3 -m pytest tests/ -q
