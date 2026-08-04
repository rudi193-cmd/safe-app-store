# terpsi-chat

A schema and its gates for messaging between under-18s in a youth-arts
organisation. **This is a design exploration with working enforcement, not the
implementation of anything.** It exists here so that its live parts are
importable when `rudi193-cmd/terpsi-music` builds a messaging capability — it
was built in the `quick-stupids` playground, which by that repo's first rule can
never be a dependency of anything.

```sh
python3 -m pytest tests/ -q     # 36 tests: 32 gates, plus the mutation harness
```

Stdlib only. SQLite. No runtime dependencies, no network, nothing persisted
outside a test's in-memory database.

## Read this before importing any of it

**Most of this is superseded**, and by something better in the repo that would
consume it. `terpsi-music`'s records core — the W-1/W-3 lane model, the
crossing envelope, the bitemporal edges — solves the same problems more
strictly. This was written before that code had been read, which is recorded
here rather than quietly fixed because the divergence is the useful part: two
independent attempts, and the table below is which one won each round.

| Mechanism here | Status | Where the better version is |
| --- | --- | --- |
| `staff_channels.witness_adult_id` `NOT NULL` + `CHECK (witness <> adult)` — no private adult↔minor channel is representable | **LIVE — the reason this is here** | Nothing equivalent exists in `terpsi-music`. See its issue #20 for the native expression: the second adult belongs on the crossing envelope, not on a channel table |
| `peer_channels` as the accepted state, with `peer_messages` FK'd to it | **Superseded** | W-3's crossing envelope, which also names purpose, expiry and a signature — none of which this has |
| Three channel tables (peer / staff / adult) | **Superseded** | W-1: one lane per person; *a shared event is two lane entries with one referent* |
| `guardian_links` | **Defective — do not port** | It conflates *standing* with *reachability*, so a contact restriction that does not end guardianship is inexpressible. `records/sending.py` separates `guardian_of` from `ContactRestriction`, and names this as the most common protective order |
| `guardian_approval_evidence` — what the decider was shown, frozen | **Superseded (it is a special case)** | Bitemporality: `valid_at`/`invalid_at` with `ended_known_at`, in `records/orders.py`. That answers *what was knowable at any instant about any fact*; this only preserves the fields somebody remembered to copy |
| Append-only triggers on evidence and archive reads | **Redundant** | Refusals 3 and 16 |
| `observation_capability` — absence is not "no findings" | **Redundant** | Refusal 13 |
| `notify.py` — SMS bodies from a fixed set, no interpolation point | **Redundant** | Refusal 7 and §4.1's minimisation rule |
| Enforcement concentrated on the write path | **Wrong emphasis** | §7.2: *narrate the read, gate the export*. The realistic harm is the transcript leaving, not the glance |
| `tests/test_mutation.py` and the pinned schema surface | **Portable** | Technique rather than domain; the same shape as `playgate` and `band-camp-arcade` |

So: **take the witness constraint and the harness technique. Leave the rest.**
Porting `guardian_links` in particular would import a defect.

## What the enforcement actually is

Safety properties are expressed as things the database cannot represent, not as
rules the application promises to follow.

`peer_channels` *is* the accepted state — a row existing is what "accepted"
means — so the foreign key from `peer_messages` covers every write path,
including ones not yet written. `staff_channels.witness_adult_id` is `NOT NULL`
and must differ from the sender, so a two-party adult–minor channel has no
representable form. `peer_messages` has no plaintext column at all.

## The gates, and why the mutation harness is the point

A green suite proves the tests ran, not that they are load-bearing.
`tests/test_mutation.py` removes each mechanism from the schema and asserts the
gate that claims to cover it goes red — 22 schema mutations and 2 on `notify`,
each with a control run proving an unmutated copy passes.

Building it caught three gates that were passing for the wrong reason: a test
that looked like it covered a constraint while a neighbouring one quietly
satisfied it. `terpsi-music`'s §7 had already named that shape — *"if the
predicate returned nothing to anyone, it would still pass"* — and prescribes the
companion assertion. Assume it is present anywhere a test asserts one failure
that several constraints could produce.

## Known hazard, and it is in the substrate

SQLite enforces foreign keys only when `PRAGMA foreign_keys = ON`, per
connection, off by default. Several guarantees above are foreign keys. There is
no way to bind the pragma to a schema, so it must be set in exactly one
connection factory; `test_fk_pragma_is_the_whole_ballgame` demonstrates the
unenforced case accepting an orphan row. Postgres has no equivalent hazard,
which is one more reason the consuming implementation should be the one with
row-level security rather than this one.

## What this cannot see

The gates cover a schema. There is no client, no transport, no key custody, no
device — so nothing here says anything about the half of a messaging system
where the hard parts live. `docs/DESIGN.md` ends with that list, and it matters
more than the pass count.

Every empirical and legal claim in `docs/DESIGN.md` is marked `assumed`:
outbound egress was blocked in the session that wrote it, no source was
retrieved, and no figure was invented to fill the gap.
