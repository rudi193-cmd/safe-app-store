# The Squirrel — Bugs Log

Found by driving the app, not by reading it. Each entry: what breaks, how to
reproduce, severity, and status. Fuzz-playground findings count — an absurd
input that produces wrong output is still wrong output.

Severity: **P0** data loss / crash / security · **P1** wrong result a user
would trust · **P2** rough edge, wrong-but-harmless · **P3** cosmetic.

---

## Open

### B-002 · No ancestor cycle detection — P1
**Found:** 2026-07-16, absurd-census drive.
A person may be their own ancestor. `link Ratatosk → parent → Ratatosk`
is accepted, and `tree Ratatosk` then renders him in all seven pedigree
slots (self as father, mother, all four grandparents) until the depth
bound stops the walk. `Zeus → parent → Odin` + `Odin → parent → Zeus`
makes a stable 2-cycle that also renders as a "pedigree."
**Why it matters:** for a real tree this is a silent data-integrity fault —
a genealogy app should refuse to make someone their own grandfather, not
draw it. Harmless in the fuzz box; wrong in the field.
**Repro:**
```
@squirrel: add person Loop One
@squirrel: link Loop One → parent → Loop One
@squirrel: tree Loop One          # Loop One fills its own ancestry
```
**Fix sketch:** reject a `parent` link whose target is already a
descendant of the source (walk down before writing); guard
`build_ancestors_dict` against revisiting a person_id in the current path
as defense-in-depth.
**Status:** open.

### B-003 · Self-relationship double-counts in the pedigree — P2
**Found:** 2026-07-16, absurd-census drive. Related to B-002 but distinct.
A self-parent link matches both directions of the relationship query, so
one self-link surfaces as *two* parents. Even with cycle detection added,
`build_ancestors_dict` should dedupe a relationship that names the same
person on both ends.
**Status:** open (fold into the B-002 fix).

### B-004 · `stash` person-name heuristic is naive — P2
**Found:** 2026-07-16, Einstein drive.
`cmd_stash` takes the first two words of the fragment text as the
`person_name`. "Lieserl Einstein b. Jan 1902…" happens to work; "The
quilt is hers" files under person "The quilt". Fine for freeform notes,
misleading when the binder later matches on person_name.
**Fix sketch:** accept an explicit `--person "Name"` flag; fall back to
the heuristic only when it's absent.
**Status:** open.

### B-005 · Name search is prefix-fragile — P2
**Found:** 2026-07-16, Einstein drive.
`search_persons` is a substring `LIKE`, so "Albert Einstein" also matches
"Hans Albert Einstein". Commands that act on `matches[0]` (link, tree,
show kin) currently disambiguate only by alphabetical order — correct by
luck, not by rule.
**Fix sketch:** prefer an exact (case-insensitive) full_name match before
falling back to substring; when >1 exact match, surface the ambiguity
instead of silently picking one.
**Status:** open.

---

## Fixed

### B-001 · Reverse relationship rows not inverted — P1 — FIXED
**Found:** 2026-07-16, Einstein drive. **Fixed:** commit e4f59ca.
A row `(child, parent, 'parent')` read from the parent's side displayed as
`PARENT` on the person page and in `show kin`, and `build_ancestors_dict`
walked reverse rows back into the subject — correct pedigrees were an
accident of insertion order. Person page, `show kin`, and the ancestor
walker now handle reverse rows explicitly.
**Regression:** `tests/test_kin_direction.py` (seeds the child row first so
order can't mask it).

---

## Verified NOT bugs (drive-tested, held correctly)

- **SQL injection** — `Robert'); DROP TABLE persons;--` stored as a literal
  name; 11 rows intact, table present. Parameterized queries throughout.
- **Stored XSS** — `<script>alert('nuts')</script> Jones` renders escaped;
  a live browser with a dialog listener fired zero alerts.
- **Unicode / emoji names** — `🐿️ von Nutkin` stores and renders.
- **Absurd length** — 261-char surname accepted; card wraps.
- **Dangling relationship target** — `link X → parent → <unknown>` no-ops
  with "Person not found", creates no phantom row.
- **Gate scope (willow-mcp drive)** — out-of-scope store write and
  unpermitted `session_enter` both denied and receipted.

ΔΣ=42
