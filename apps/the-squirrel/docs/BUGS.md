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

### B-004 · `stash` person-name heuristic is naive — P2
`cmd_stash` takes the first two words of the fragment text as `person_name`.
"Lieserl Einstein b. Jan 1902…" works; "The quilt is hers" files under person
"The quilt". Misleads the binder, which matches on person_name.
**Fix sketch:** accept an explicit `--person "Name"` flag; fall back to the
heuristic only when it's absent.
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

### B-011 / B-012 · Cross-parentage: no linkage subtype; pedigree truncated silently — P2/P3 — FIXED
**Found:** cross-parentage drive (Roman adoptive emperors, Steve Jobs, Moses).
**Fixed:** `parent_kind` linkage feature. The relationship model now carries a
subtype — `birth` / `adopted` / `foster` / `step` (None = unspecified) — added
to the schema and migrated onto existing tables. Entered via the link grammar
(`link Steve Jobs → adopted parent → Paul Jobs`), shown in `show kin` and the
person page, and exported to GEDCOM as `FAMC` + `PEDI` (the exporter emits real
`FAM` records now — it ignored relationships entirely before). B-011's silent
truncation is closed: the pedigree fills its two slots birth-first (by kind
priority, not insertion order) and `tree` NAMES any further parents with their
kind instead of dropping them. Live: Steve Jobs shows Jandali/Schieble in the
slots, "Paul Jobs (adopted), Clara Jobs (adopted)" noted below, and exports two
FAM records with `PEDI birth` / `PEDI adopted`.
**Regression:** `tests/test_parent_kind.py` (16 tests: storage/validation,
grammar, kin, pedigree-birth-preferred-and-names-rest, GEDCOM PEDI).
**Hardened after an independent Sonnet review** caught four bugs in the first
cut (all fixed before merge, each with a test): a Postgres upgrade-migration
crash (rollback reverted the session `SET search_path`; now re-issued —
verified live on Postgres 16), the pedigree still silently dropping parents
linked via the reverse `child` grammar, and two GEDCOM export faults (mixed
kind-tagging splitting one couple into two single-parent `FAM`s; a 3rd
same-kind parent dropped from the `FAM`). The same `SET search_path` fix was
applied to the B-008 `bound_person_id` migration, which had the identical
latent bug.

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

### B-009 · Control chars pass into stored text — P3 — FIXED (cross-app)
**Found:** malformed-GEDCOM drive. **Fixed:** a sanitizer at each app's single
write boundary — the one bug that translated cleanly across both Knowledge OS
apps. C0 control chars (NUL, BEL, …), which have no place in a name nobody can
retype or a NUL that truncates downstream C-string tooling, are stripped on
write; tab/newline survive. **the-squirrel:** `db.sanitize` / `clean_params`,
applied at `add_person`, `add_fragment`, and `update_person_field`.
**ask-jeles:** `corpus._clean` at the `_put` chokepoint — one place covers
nuggets and gaps. **Regression:** `tests/test_sanitize.py` (Squirrel),
`tests/test_corpus.py::test_control_chars_stripped_at_write_boundary` and
`::test_logged_gap_is_sanitized` (Jeles).

### B-007 · Stash page renders 100 of N with no indication — P2 — FIXED (Squirrel-only)
**Found:** bulk-import drive. **Fixed:** `_render_stash` now says "showing 100
of N fragments" when truncated, "N fragments" otherwise — no truncated list
reads as complete. *Not* a cross-app bug: ask-jeles's list surfaces
(`corpus_list`/`corpus_gaps`) take an explicit caller-chosen `limit` and never
inflate a total they don't show, so there was nothing to fix there — audited,
confirmed honest. **Regression:** `tests/test_sanitize.py`
(`test_stash_render_is_honest_about_truncation`).

### B-005 · Name search is prefix-fragile — P2 — FIXED
**Found:** Einstein drive. **Fixed:** `resolve_person` confidence floor.
`search_persons` is a substring `LIKE`, so "Albert Einstein" also matched
"Hans Albert Einstein", and every command acting on `matches[0]` (link, tree,
show kin, show person, bind, the web tree) picked by alphabetical luck.
**Fix:** `db.persons.resolve_person(conn, query)` returns
`("found", person)` / `("ambiguous", [persons])` / `("none", None)` —
borrowing ask-jeles's MIN_ASK_SCORE idea. An exact (case-insensitive)
full_name match beats a substring match, so "Albert Einstein" resolves
cleanly; a lone substring match is confident; multiple equally-good matches
surface a "did you mean" list (`formatter.did_you_mean`) instead of a guess,
and identical names (father/son "Oscar Mann") are ambiguous, never picked by
sort order. All six call sites converted; the web tree renders the
disambiguation too.
**Regression:** `tests/test_resolve.py` (exact-beats-substring, lone-substring
confident, multi-substring ambiguous, identical-names ambiguous, tree draws on
exact / refuses on ambiguous, link refuses an ambiguous endpoint).

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
