# The Squirrel — Bugs Log

Found by driving the app, not by reading it. Each entry: what breaks, how to
reproduce, severity, and status. Fuzz-playground findings count — an absurd
input that produces wrong output is still wrong output.

Severity: **P0** data loss / crash / security · **P1** wrong result a user
would trust · **P2** rough edge, wrong-but-harmless · **P3** cosmetic.

---

## Open

### B-006 · Watcher silently drops commands under burst/concurrent writes — P1
**Found:** 2026-07-16, concurrency drive.
Fire 20 `add person` commands at `/write` in parallel: all 20 lines land in
`Squirrel.md` (the file lock holds), but only **8 persons** are created.
Twelve commands are silently dropped — no error in the journal, no error in
the server log. The file (the app's declared ground truth) says the command
happened; the app never ran it.
**Mechanism:** `squirrel_watcher._Handler.on_modified` reads new bytes from
`_last_size` to the current size and processes them — but then does
`self._last_size = self._path.stat().st_size` to skip past the bot responses
it wrote. Any concurrent `/write` that appended *during* processing sits
between the batch just read and that new size, so the reset leaps over it and
it is never processed. watchdog event coalescing compounds it (N appends can
collapse into one `on_modified`, and only the bytes visible at read time are
seen).
**Why it matters:** silent loss of user intent. Single-user hunt-and-peck
never triggers it (the web UI navigates away and waits between commands), but
any burst source does — a paste of multiple lines, a programmatic driver, an
MCP integration writing the journal, or Jeles appending in a future mode.
"The file is the interface / the file is ground truth" is violated exactly
when the file and the DB disagree.
**Repro:**
```
for i in $(seq 1 20); do
  curl -s -X POST localhost:8425/write -H 'Content-Type: application/json' \
    --data-raw "{\"text\":\"@squirrel: add person Race$i\"}" &
done; wait
# journal: 20 'add person' lines · DB: ~8 persons
```
**Fix sketch:** the watcher must not conflate "bytes I processed" with "bytes
present now." Track a processed-offset that only advances past lines actually
handled; after processing, re-stat and if the file grew, loop and process the
new tail instead of skipping it. Distinguish bot-written responses from user
lines by marker/sentinel rather than by "everything up to current size."
Better: decouple ingestion from the file — POST `/write` could enqueue the
command directly to the responder and treat the file as a render log, so
correctness never depends on winning a stat race.
**Status:** open. Design-level — the single meatiest find so far.

### B-008 · `bind fragment all` silently processes only the first 200 — P1
**Found:** 2026-07-16, 1000-person bulk-import drive.
`Binder.auto_bind` reads `get_unsynced_fragments(limit=200)` and calls itself
"bind **all**." With 1000 unsynced fragments it examines 200 and never looks
at the other 800 — and reports `✓ Auto-bound N fragment(s)` with no hint that
800 were skipped. Observed: 3 fragments named "Oak Acorn" existed; only the
1 within the first 200 got bound, the other 2 were invisible to the run.
**Why it matters:** the user reads "Auto-bound 1" and believes the stash is
reconciled; 800 fragments silently sit unexamined. Re-running doesn't
obviously help — same first-200 window unless earlier ones got synced out.
Also O(batch × persons) with no index, but the cap hides the perf cost rather
than fixing it.
**Repro:** import 1000 fragments, add one matching person, `bind fragment all`
→ "Auto-bound 1", 999 still unsynced.
**Fix sketch:** page through ALL unsynced fragments (loop until the query is
dry), or state the bound explicitly: "examined 200 of 1000 — run again for
the next batch." Never call a bounded pass "all" silently.
**Status:** open.

### B-007 · Stash page renders 100 of N with no indication — P2
**Found:** 2026-07-16, bulk-import drive.
`_render_stash` does `all_frags[:100]` but the subtitle prints the full count:
the page reads "1000 fragments" and shows 100 rows, no "showing 100 of 1000."
**Why it matters:** a user scrolls, sees 100, assumes that's everything.
Same silent-truncation class as B-008, cosmetic tier.
**Fix sketch:** show "100 of 1000 — refine with a filter" or paginate.
**Status:** open.

### B-009 · Control characters pass through into stored names — P3
**Found:** 2026-07-16, malformed-GEDCOM (TRLR) drive.
A GEDCOM `1 NAME Null\x00Byte Person` or `Bell\x07Char Name` imports as-is —
the raw NUL / BEL / other C0 control chars land in `person_name` and
`story_text`. Not an injection (HTML rendering escapes `<>&`, and browsers
ignore most control chars), but dirty data: a name nobody can retype, a NUL
that can truncate the string in C-based tooling downstream.
**Fix sketch:** strip/replace C0 control chars (except tab/newline) on
fragment and person write, at the db layer so every path is covered.
**Status:** open.

### B-010 · Import of a non-file path shows a raw errno, not a message — P3
**Found:** 2026-07-16, TRLR drive.
`cmd_import_gedcom` guards `path.exists()` but not `path.is_file()`, so
`import gedcom <a directory>` passes the guard, `import_ged` raises
`IsADirectoryError`, and the user sees an **Error** block reading
``[Errno 21] Is a directory: …``. The responder catches it (watcher
survives, app stays up) — it's cosmetic, but a raw errno is not an answer.
**Fix sketch:** in the command, check `is_file()` and return
"`<path>` is not a readable file"; keep `import_ged` raising for callers.
**Status:** open.

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
- **1000-person GEDCOM import** — 1000 individuals parsed and stored as
  fragments in ~6s, no error, DB intact. Import scales fine; it's the
  binder and stash *rendering* of that volume that cap silently (B-007/008).
- **Parser: case + whitespace** — `@SQUIRREL:` with runs of spaces parses;
  nested `@squirrel: @squirrel:` refuses rather than birthing a person.
- **Control-command injection** — `skin ../../etc/passwd`, `skin '; DROP…`,
  `mode banana` all whitelist-rejected; no config written.
- **GEDCOM round-trip** — re-importing the hostile export brings the
  `DROP TABLE` / `<script>` names back as fragments, not persons; DB intact.
- **Malformed GEDCOM (the whole TRLR arm)** — the importer is the sturdiest
  component driven so far. Missing `TRLR` still flushes the last person;
  empty / TRLR-only / 2KB of `/dev/urandom` yield 0 fragments, no crash; a
  single INDI with 50,000 `NAME` lines resolves last-write-wins in ~74ms with
  no memory blowup; a 21-digit level number doesn't overflow (Python bigint);
  reading a binary sqlite file or `/etc/passwd` as GEDCOM stores nothing.
  A directory or missing path is caught by the responder — the watcher thread
  survives every case (see B-010 for the cosmetic errno).

ΔΣ=42
