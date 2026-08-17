# Homestead Table — a vision note

> **Status: reflection, not a spec.** Nothing is built from this yet. It's written
> down so the thinking isn't lost (the same lesson as the design map: the one
> piece of a session's work that only lives in chat is the piece that vanishes).

## Where this came from

This started as a game-master spine — the code in `apps/the-table/`. The PR title
"The Table" was the tell: it was never really about games. A table is what a
household gathers *around*; the gaming table is just one way to sit at it.

## The home: Homestead, module three

Homestead is a family of self-contained, local-first desktop **Affairs** modules
over a shared record engine (`homestead.keep`, distributed as `homestead-affairs`),
sharing one `~/.homestead` root, on embedded SQLite — no listening socket, no
server.

- **homestead-law** (prose name *Law Gazelle*) — the household's deeds and disputes.
- **homestead-ledger** — the household's books (money), *mirrored*.
- **Homestead Table** — module three (not built): where the household gathers.

## The engine DNA — and why the Table belongs here

- **Canonical is read-only by type (I-6);** corrections go in a **Sidecar beside**
  the record, never on top. (kitchen-pudding's correction-log pattern, formalized.)
- **Rung model L1–L5; absence fails closed to L5** — unknown/corrupt reads as the
  *most* protected on the way out, never the least.
- **L5 never leaves the house.** Sync is a gated egress where an L5 record never
  crosses; only what the household *chose* to expose syncs. The money ledger even
  carries a guard that refuses to dial out at all.
- **"Mirror, not judge."** A module reflects the household; it never authors a
  judgment about anyone. Law Gazelle's resting cover shows only counts that survive
  a re-identification check.

## What the Table is — the kept-clear surface

Most tables become the collection spot for bills, mail, the "deal with it later"
pile — because the house has nowhere else to put it. Homestead gives that stuff a
home (Law, Ledger), and **that is what lets a table stay a table.**

So the Table isn't a third place that *collects*. It's the surface kept
deliberately clear — **defined by what it refuses to hold.** The room in the house
with no ledger. For eating, a kid reading, a little something crafty — presence
without a record. Unusual for software, which almost always wants to capture more.

## Sealed vs. living — why the Table inverts the engine

Law and Ledger hold what must be **pinned**: a deed, a deadline, a dollar. Things
whose whole point is that they can't quietly change — *writes never silently
overwrite* — because the record has to stand on its own later, sometimes against
someone.

The Table holds the opposite — the **living and adaptive**:

- A game needs no seal because **the playing is the attesting** — it's how the
  story goes, and it goes differently every time.
- A meal is the same: you don't certify a dinner, you eat it; next month the kid
  who loved it won't touch it.

These aren't facts to fix. They're *supposed* to move.

## The tender principle — protect the growing by refusing to fix them

A child's taste, a child's version of how the story goes, are *meant* to adapt.
To seal them is to tell a growing person "this is who you are" and make it stick —
the same wrong turn as logging who was at dinner. It pins something that has a
right to change. So the Table:

- **does not record who was present or how a person behaved** — no attendance log,
  no per-person profile;
- if it holds anything, it holds the **meal** (a thing), not the **people**
  (subjects) — and kitchen-pudding is already the recipe half of that;
- is the one surface where the present is **allowed to be replaced** — what's true
  at the table *right now*, which tomorrow is something else. Not an append-only
  chain. **A memory that forgets on purpose.** No trail kept against anyone.

## The safety turn, resolved by the ground it stands on

An earlier draft of this idea drifted into logging the kids' nightly presence into
a permanent, tamper-evident ledger. That is creepy, and it could be used against a
minor or anyone not in control of their situation. The very properties that make a
ledger *good* for decisions — append-only, tamper-evident, no deletion, attributed
— become a **weapon** the moment the subject is a person instead of a choice, and
"only a person seals" protects the *sealer's* authority while a household's sealer
(a parent) and subject (a child) are two different people with a power gap.

Homestead's engine already makes that failure hard to build: anything about a
person is **L5** (fails closed, never egresses), the module **mirrors rather than
judges**, and it is **local and household-owned**. The fix stops being a rule to
remember and becomes a property of the ground the Table stands on.

## Left open, on purpose

What the Table concretely holds beyond the meal — and how "allowed to be replaced /
forgets on purpose" is expressed on an engine whose invariants are about *not*
overwriting — is unresolved. That's the next conversation, not a gap to paper over.
