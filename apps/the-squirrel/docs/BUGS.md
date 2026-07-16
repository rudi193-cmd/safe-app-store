# The Squirrel — Bugs Log

Found by driving the app, not by reading it. Each entry: what breaks, how to
reproduce, severity, and status. Fuzz-playground findings count — an absurd
input that produces wrong output is still wrong output.

Severity: **P0** data loss / crash / security · **P1** wrong result a user
would trust · **P2** rough edge, wrong-but-harmless · **P3** cosmetic.

Every fix below was diagnosed, then adversarially verified by an independent
agent (live repro + fix critique) before implementation — each of the three
P1 fix sketches was refined by that pass. See commit history.

---

## Open

### B-011 · Pedigree silently truncates to 2 parents — P2
**Found:** 2026-07-16, cross-parentage drive (biological vs. raising parent).
A person with more than two `parent` links renders only the first two in the
pedigree, with no indication the others exist. Steve Jobs has four parent
links (bio: Jandali + Schieble; adoptive: Paul + Clara Jobs) — the tree shows
only Jandali + Schieble and drops the parents who *raised* him. Augustus loses
Julius Caesar (the adoptive father who made him emperor); Nero loses Claudius.
**Why it matters:** `build_ancestors_dict` takes `parents[:2]` because an
Ahnentafel pedigree structurally has exactly two parent slots. But insertion
order decides which two survive, and the raising/adoptive parents are almost
always linked *after* the biological ones — so the default silently favors
blood over the socially-real family, in an app whose whole pitch is reuniting
the branches everyone forgot. `show kin` correctly lists all four; only the
pedigree lies. The dropped parents aren't even in the tree's person count.
**Repro:** give one person 3–4 `parent` links, `tree <name>` → only 2 shown,
no "2 of 4" note.
**Fix sketch:** at minimum, annotate ("+2 more parents — see kin"); better,
let the pedigree show alternate parent sets or pick by an explicit primary
flag rather than insertion order. Depends on B-012.
**Status:** open.

### B-012 · No biological vs. adoptive/foster parentage distinction — P3 (design)
**Found:** 2026-07-16, cross-parentage drive.
The relationship model has one flat `parent` type. "Fathered by one, raised by
another" — adoption, foster, step, illegitimacy — can only be expressed as
multiple undifferentiated `parent` links. GEDCOM's `FAMC`/`PEDI` linkage
(`birth` | `adopted` | `foster`) has no representation, so import can't capture
it and export can't emit it.
**Why it matters:** for a genealogy app that markets itself on the branches
"everyone forgot about on purpose," adoptive and illegitimate parentage is the
core case, not an edge. It's also the root of B-011 — with a linkage subtype
the pedigree could show the primary line and mark the rest.
**Fix sketch:** add a nullable `parent_kind` (`birth`/`adopted`/`foster`/
`step`) to the parent relationship; thread it through link parsing, kin
display, the pedigree, and GEDCOM import/export `PEDI`.
**Status:** open — design change, not a defect.

### B-004 · `stash` person-name heuristic is naive — P2
`cmd_stash` takes the first two words of the fragment text as `person_name`.
"Lieserl Einstein b. Jan 1902…" works; "The quilt is hers" files under person
"The quilt". Misleads the binder, which matches on person_name.
**Fix sketch:** accept an explicit `--person "Name"` flag; fall back to the
heuristic only when it's absent.
**Status:** open.

### B-005 · Name search is prefix-fragile — P2
`search_persons` is a substring `LIKE`, so "Albert Einstein" also matches
"Hans Albert Einstein". Commands acting on `matches[0]` (link, tree, show kin)
disambiguate only by alphabetical order — correct by luck, not by rule.
**Fix sketch:** prefer an exact (case-insensitive) full_name match before the
substring fallback; on >1 exact match, surface the ambiguity.
**Status:** open. (The B-008 fix added the same margin-of-confidence idea to
the binder; the same principle applies here.)

### B-007 · Stash page renders 100 of N with no indication — P2
`_render_stash` does `all_frags[:100]` but the subtitle prints the full count:
the page reads "1000 fragments" and shows 100 rows, no "showing 100 of 1000."
Same silent-truncation class as B-008 (now fixed), cosmetic tier.
**Fix sketch:** "100 of 1000 — refine with a filter" or paginate.
**Status:** open.

### B-009 · Control characters pass through into stored names — P3
A GEDCOM `1 NAME Null\x00Byte Person` imports as-is — raw NUL/BEL/other C0
chars land in `person_name` and `story_text`. Not injection (HTML escapes
`<>&`), but dirty data: a name nobody can retype, a NUL that truncates strings
in downstream C tooling.
**Fix sketch:** strip/replace C0 control chars (except tab/newline) at the db
write layer so every path is covered.
**Status:** open.

### B-010 · Import of a non-file path shows a raw errno — P3
`cmd_import_gedcom` guards `path.exists()` but not `path.is_file()`, so
importing a directory surfaces `[Errno 21] Is a directory` in an Error block.
Caught by the responder (app survives); a raw errno is not an answer.
**Fix sketch:** check `is_file()` in the command; keep `import_ged` raising for
callers.
**Status:** open.

---

## Fixed

### B-008 · `bind fragment all` silently processed only the first 200 — P1 — FIXED
**Found:** 1000-person bulk-import drive. **Fixed:** binder rework + schema
migration. **Verifier caught:** a deeper defect than the cap — *no column
stored which person a fragment bound to* (the `person_id` was computed and
discarded), and the 0.8 matcher *mis-bound* (0.81 crossed threshold on shared
suffixes; ties silently picked whichever the query returned first).
**Fix:** `auto_bind` now examines every unsynced fragment within a work budget
(no 200 cap) and returns an honest report (examined / bound / ambiguous /
remaining); a match must clear the threshold AND beat the runner-up by a
margin, else it's counted ambiguous and left for a human; `bound_person_id`
persists the target (added to the schema, migrated onto existing tables).
**Regression:** `tests/test_binder_scale.py` (past-200, tie-skip,
shared-suffix, provenance, honest-empty). Live: 1000 fragments, 3 matches at
positions 250/600/900 all bound, `remaining=0`, 0.04s.

### B-006 · Watcher dropped commands under burst/concurrent writes — P1 — FIXED
**Found:** concurrency drive (20 parallel writes → 8 persons). **Fixed:** new
`journal.py`. **Verifier caught:** the naive "loop-to-EOF" fix would execute
the bot's own output as commands — a usage string `` `@squirrel: stash "…"` ``
parses as a live command — and `/write` vs `state.append` used two different
locks.
**Fix:** one shared `RLock` held across the entire read→dispatch→append→advance
cycle, so a concurrent `/write` can't land between the read and the offset
advance, and bot output is never re-read as a command. All writers route
through the `Journal`.
**Regression:** `tests/test_journal.py` (interleaved bot-append, usage-string
non-execution, 50-burst, concurrent threads). Live: 20 parallel writes →
20 persons, 0 dropped, 0 spurious.

### B-002 / B-003 · No ancestor cycle detection; self-links double-counted — P1 — FIXED
**Found:** absurd-census drive (Ratatosk as his own grandfather). **Fixed:**
`add_relationship` guard + path-local walker. **Verifier caught:** a
parent-only write-check leaves the `child`-link door open to the same cycle;
the checking walk itself needs a visited-set (legacy data may already be
cyclic); and the render-time visited-set must be *path-local* or it erases
legitimate pedigree collapse (same grandfather in slots 4 and 6).
**Fix:** direction-agnostic cycle rejection (normalizes parent/child to
(child, parent), walks ancestors with a visited-set), self-links refused for
every relationship type (kills B-003's double-count), and
`build_ancestors_dict` guarded path-locally.
**Regression:** `tests/test_cycles.py` (self, parent-side, child-side, mixed,
grandparent, pedigree-collapse-preserved, survives-preexisting-cycle).

### B-001 · Reverse relationship rows not inverted — P1 — FIXED
**Found:** Einstein drive. **Fixed:** commit e4f59ca. A row `(child, parent,
'parent')` read from the parent's side displayed as `PARENT` and polluted the
pedigree walk. Person page, `show kin`, and the ancestor walker now handle
reverse rows explicitly. **Regression:** `tests/test_kin_direction.py`.

---

## Verified NOT bugs (drive-tested, held correctly)

- **SQL injection** — `Robert'); DROP TABLE persons;--` stored as a literal
  name; table intact. Parameterized queries throughout.
- **Stored XSS** — `<script>alert('nuts')</script> Jones` renders escaped; a
  live browser with a dialog listener fired zero alerts.
- **Unicode / emoji names**, **261-char surname**, **dangling link target**
  (no-ops, no phantom row).
- **Gate scope (willow-mcp drive)** — out-of-scope store write and unpermitted
  `session_enter` both denied and receipted.
- **1000-person GEDCOM import** — parsed and stored in ~6s, no error.
- **Malformed GEDCOM (TRLR arm)** — missing trailer flushes the last person;
  empty / garbage / binary yield 0; 50k `NAME` lines resolve in ~74ms with no
  blowup; 21-digit level numbers don't overflow; reading a binary/`/etc/passwd`
  stores nothing; the watcher survives directory/missing paths.
- **Parser** — `@SQUIRREL:` + runs of spaces parses; nested `@squirrel:
  @squirrel:` refuses; `skin ../../etc/passwd`, `mode banana` whitelist-rejected.
- **Cross-parentage kin** — `show kin` correctly lists ALL parent links for a
  person with multiple parents (bio + adoptive); the flat list is honest. Only
  the pedigree truncates (B-011); the underlying data holds every link.

ΔΣ=42
