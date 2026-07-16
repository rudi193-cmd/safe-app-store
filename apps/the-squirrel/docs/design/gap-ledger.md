# Design: The Acknowledged-Unknowns Ledger

Status: **SHIPPED**. Modeled on `ask-jeles`'s gap backlog
(`apps/ask-jeles/docs/design/verified-corpus.md` §1–5,
`askjeles/corpus.py:log_gap`).

## 1. Why

Every Squirrel file signs off `ΔΣ=42` — the suite's motif for "42 acknowledged
unknowns," the *"how do you know that?"* running through everything
(`VISION.md`). But the app acknowledged none: a miss — `Person not found`, an
ambiguous bind — was printed once and forgotten. Genealogy is *made of*
unknowns (the empty ancestor slot, the branch that got lost), so an app about
reuniting forgotten branches with no memory of which branches it couldn't
reunite was hollow where it mattered most.

`sap/core/gaps.py` is that memory: a miss becomes a tracked gap, a repeated
miss bumps a count instead of duplicating, and gaps are worked down over time —
directly Jeles's pattern.

## 2. The one deliberate divergence from Jeles — and it's the point

Jeles **forwards** its gaps to willow-mcp's fleet-wide backlog, because its
gaps are public-knowledge questions ("what is a Vespa?"). The Squirrel's gaps
name family members — *"unknown person: Oscar Mann's father"* — which is **PII**.

So the Squirrel's ledger is **local, in the box, and never forwards.** This is
not an omission; it is the same rule that demoted Wikipedia from a live fetch
to a link and that `tests/test_chokepoint.py` enforces: the app makes zero
network calls of its own. Forwarding gaps would send the tree — or questions
that reveal the tree — off the machine. *The tree stays in the tree; so do the
questions about it.* `gaps.db` sits at `0600` inside the `0700` box, beside
`vault.db` and `receipts.db`.

## 3. What gets logged, and what doesn't

Following Jeles's "two kinds of ask, two rules": only **deliberate** misses
log, never passive/incidental ones.

| Kind | Logged from | Not logged |
|------|-------------|------------|
| `unknown_person` | a name referenced in `tree` / `show kin` / `link` that isn't in the tree | every keystroke of a live `search` (would flood) |
| `ambiguous_bind` | a fragment `bind all` matched to several people (the B-008 tie) | a fragment with no match at all (not yet — see §5) |

Dedup is by `uuid5(kind + normalized-subject)`, so "Oscar Mann", "oscar mann",
and "Oscar  Mann" are one gap with a rising `asked_count`.

## 4. The loop closes

Adding a person resolves any open `unknown_person` gap that named them
(`cmd_add_person` → `gaps.resolve_subject`). You ask for Carl Mann, he's not
there, the gap opens; weeks later you add him, the gap closes itself and says
so. `@squirrel: gaps` lists what's open (most-asked first); `@squirrel: gaps
resolve <id>` settles one by hand.

## 5. Open questions

- **Unmatched fragments as gaps.** A fragment that `bind all` couldn't match to
  anyone is the purest genealogy gap ("who is this?"), but logging one per
  unmatched fragment could be noisy at import scale. Deferred until there's a
  UI to triage them.
- **Empty-slot gaps.** Every `Unknown` in a pedigree is an implicit gap; auto-
  logging them all would bury the deliberate ones. A future `@squirrel: gaps
  --pedigree <name>` could surface a specific tree's holes on request.
- **A web `/gaps` view** to match the command, alongside People/Tree/Stash.

ΔΣ=42
