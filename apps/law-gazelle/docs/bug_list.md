# Law Gazelle — Bug Hunt Findings

Target: `/home/user/safe-app-store/apps/law-gazelle` (~7,300 LOC Python, local-first legal case management TUI + MCP server).
Baseline: `python3 -m pytest tests/ -q` → **72 passed, 9 skipped** (unchanged; no files under the repo were modified).
All reproduction scripts and a synthetic demo Nest live in the scratchpad only.

Reference date used in all reproductions: **2026-08-04**.

**Verification provenance.** Found by a dedicated bug-hunt pass, then
**independently re-verified** before landing here: BUG-1, BUG-2, BUG-3, BUG-4,
BUG-5 and BUG-6 were each reproduced or re-derived from source a second time by
a different reader. BUG-7 through BUG-11 carry the hunt's own CONFIRMED
reproductions and were not independently re-run. BUG-12 is **PLAUSIBLE only** —
`willow_gate` is not installed on this machine, so the enforcement path could
not be exercised at all.

**Two things the re-verification sharpened:**

1. **BUG-1's failure is data-dependent, not uniform** — which is why it survives
   casual testing. `"May 5 2026"` is exactly 10 characters, so it slips through
   the truncation and parses correctly (`-91`). `"May 5, 2026"` is 11 and
   returns `None`. The same deadline, written with and without a comma, gives
   opposite answers.
2. **BUG-1 and BUG-3 make two fields disagree with each other.** A deadline can
   simultaneously carry `days_until = -91` and `overdue = False`, because
   `days_until` parses the date while `overdue` string-compares the raw value.
   Any code trusting one field over the other gets a different answer, and both
   are wrong in different directions.

**Priority note.** BUG-1 and BUG-2 outrank every item in
[`finish_list.md`](finish_list.md). That list is about promotion readiness,
pilot readiness, and hygiene; these two are wrong answers about court deadlines
in an application whose stated purpose is that a self-represented litigant does
not miss one. MISSION.md puts it directly: *"a missed deadline here is not a bug
ticket; it is harm."*

---

## Summary table

| ID | Severity | Summary | Location | Confidence |
|----|----------|---------|----------|------------|
| BUG-1 | **critical** | `_days_until()` truncates the date string to 10 chars before parsing, so every long-form date it claims to support returns `None`; an overdue deadline is then shown as not overdue and sinks to the bottom of the urgent queue | `case_store.py:76` | CONFIRMED |
| BUG-2 | **critical** | `milestones()` parses the same deadline with `date.fromisoformat()` and raises an uncaught `ValueError`, taking down the milestone banner, `briefing_packet()`, `cross_case_overview()` and the TUI refresh | `case_store.py:117` | CONFIRMED |
| BUG-3 | **high** | `overdue`/`severity` for response deadlines are computed by lexicographic **string** comparison, so a 91-day-overdue deadline renders as "Due Soon" / `HIGH` even when `days_until` is correctly `-91` | `case_store.py:506` | CONFIRMED |
| BUG-4 | **high** | Free-text snooze dates are never validated: `"next week"` snoozes an urgent deadline **forever**, `"08/11/2026"` snoozes it not at all — and there is no un-snooze anywhere in the app | `gazelle_state.py:484`, `screens/detail.py:167` | CONFIRMED |
| BUG-5 | **high** | A fact marked `do_not_use` is neither blocked on its card nor excluded from the drafting packet / LLM prompt, while the Review Facts screen tells the user "Excluded from drafting" | `workflow.py:113`, `document_store.py:66`, `case_store.py:1331` | CONFIRMED |
| BUG-6 | **high** | Workers' comp — one of the three advertised matter types — is structurally absent from `urgent_queue()`, Today cards, and the MCP briefing packet, despite the docstring "Combined urgent items across all cases" | `case_store.py:539-544` | CONFIRMED |
| BUG-7 | **high** | The AI cache fingerprint ignores every substantive input: rewriting an atom's body, adding evidence, adding a note, or moving a deadline 4 days closer all yield the identical fingerprint, so a stale AI brief/draft is re-served for up to 7 days | `intelligence.py:107-126` | CONFIRMED |
| BUG-8 | **medium** | `save_document()` silently overwrites an existing draft, and the suggested draft filename is deterministic per day — regenerating a draft destroys the previous version with no warning | `document_store.py:352` | CONFIRMED |
| BUG-9 | **medium** | The AI-assistance disclosure is skipped for any body starting with `#` (the shape the app's own templates produce) or containing the word "DISCLOSURE" (a bankruptcy term of art) | `document_store.py:349` | CONFIRMED |
| BUG-10 | **medium** | `_parse_evidence_ids()` falls back to a hardcoded `EVD-\d{4}-\d{3}` regex and silently drops every evidence link that doesn't match, which then makes the fact-review screen report "No linked evidence / Find source before using" for a sourced fact | `case_store.py:57-70` | CONFIRMED |
| BUG-11 | **low** | `_set_fact_verification` hardcodes `source_db="coparent"` on the write while every read uses the card's real `source_db` — a latent cross-matter mis-attach | `app.py:748` | CONFIRMED (write/read key mismatch); latent |
| BUG-12 | **low** | `GateKeeper.checkin` stores the session before checking `ok`, and the gate branch of `_handle` is outside the try/except | `gazelle_gate.py:133`, `gazelle_mcp.py:576-596` | PLAUSIBLE |

---

## BUG-1 — `_days_until()` truncates before parsing long-form dates

**Severity: critical.** This is the single deadline-arithmetic function in the app. When it returns `None`, the item's `days_until` becomes `None`, `urgent_queue`'s sort key substitutes `9999`, and a hard court deadline that has already passed is sorted *below* items due in a month. The Today card downgrades from `overdue` to `ready_to_draft`. For the app's stated user — a self-represented litigant relying on Today to know what is due — this is a missed-deadline generator.

**Location:** `case_store.py:73-83`, specifically line 76.

```python
def _days_until(deadline: str | None) -> int | None:
    if not deadline:
        return None
    dl = deadline[:10]                                        # ← line 76
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y"):
        ...
```

**Mechanism.** The function declares support for `"%B %d, %Y"` and `"%B %d %Y"`, but slices the input to 10 characters first. No `"<Month> <D>, <YYYY>"` string fits in 10 characters, so those two formats are dead code for essentially every real value. The deadline comes from operator-supplied `coparent_db_export.json` `_meta.response_deadlines`, which the app reads "as-is (no schema migration)" — a human-entered `"July 1, 2026"` is entirely realistic.

**Confirmed:**

```
'2026-08-10'       -> 6
'August 10, 2026'  -> None      ([:10] = 'August 10,')
'July 1, 2026'     -> None      ([:10] = 'July 1, 20')
'January 1, 2027'  -> None
'May 5, 2026'      -> None      ([:10] = 'May 5, 202')
'May 5 2026'       -> -91       (exactly 10 chars, so it parses)
```

End-to-end on the synthetic demo Nest, same deadline written two ways (today = 2026-08-04):

```
ISO   '2026-07-01' -> days=-34  overdue=True   sev=URGENT
                      queue position 1 of 4;  card status = "overdue"

Long  'July 1, 2026'-> days=None overdue=False sev=HIGH
                      queue position 5 of 6;  card status = "ready_to_draft"
                      why = "Hard deadline: Schedule proposals (letter response)"
```

**Fix.** Parse the whole string: try each format against `deadline.strip()` first, and only fall back to `deadline[:10]` for the ISO-with-time case (or use `datetime.fromisoformat` for that branch specifically).

---

## BUG-2 — `milestones()` raises an uncaught `ValueError` on any non-ISO deadline

**Severity: critical.** Same trigger as BUG-1, different failure mode: instead of a wrong answer, the app throws. `milestone_banner()`, `briefing_packet()` (the primary MCP orientation tool) and `cross_case_overview()` all die, and the TUI's `action_refresh` (the `r` key) calls `milestone_banner()` outside any try/except at `app.py:404`.

**Location:** `case_store.py:111-125`, specifically line 117.

```python
def _enrich(items: list[dict]) -> list[dict]:
    out = []
    for m in items:
        d = date.fromisoformat(m["date"][:10])   # ← line 117
```

**Mechanism.** `milestones()` builds its base list from `response_deadlines()` using `d["deadline"][:10]`, then hands the truncated string to `date.fromisoformat`, which is strict. `"July 1, 2026"[:10]` is `"July 1, 20"`.

**Confirmed** (deadline set to `"July 1, 2026"` in the demo export):

```
FAIL milestones          ValueError Invalid isoformat string: 'July 1, 20'
FAIL milestone_banner    ValueError Invalid isoformat string: 'July 1, 20'
FAIL briefing_packet     ValueError Invalid isoformat string: 'July 1, 20'
FAIL cross_case_overview ValueError Invalid isoformat string: 'July 1, 20'
```

Via MCP this turns `gazelle_briefing` into `isError`; in the TUI, pressing `r` crashes the app.

**Fix.** Route milestone dates through the same (fixed) `_days_until` parser and skip/flag entries that cannot be parsed, rather than calling `date.fromisoformat` on a truncated string.

---

## BUG-3 — `overdue` and `severity` computed by lexicographic string comparison

**Severity: high.** Independent of BUG-1: it produces a wrong answer even when `days_until` is computed *correctly*. The Today card then labels a long-past deadline "Due Soon".

**Location:** `case_store.py:497-513`, specifically line 506.

```python
"overdue": due < today if due else False,                      # ← line 506
"severity": "URGENT" if due and due < today else "HIGH",       # ← line 507
```

where `today = date.today().isoformat()`.

**Mechanism.** `due` is compared as a raw string against ISO `today`. Any non-ISO representation compares by ASCII order, not chronology. `"May 5 2026" < "2026-08-04"` is `False` because `'M'` (0x4D) > `'2'` (0x32). `urgent_queue` then cannot repair it, because its guard is `if item.get("overdue") is None` — and `overdue` is `False`, not `None`. `workflow.infer_card_status` checks `item.get("overdue")` before `days_until`, so it falls through to the `days <= 7` branch and returns `due_soon`.

**Confirmed** (today = 2026-08-04):

```
due='May 5 2026'   days_until=-91  overdue=False  severity=HIGH
                   card status = due_soon | why = "Response due May 5 2026 (-91 days)"
due='2026-8-4'     days_until=0    overdue=False  severity=HIGH   (unpadded ISO)
due='2026-07-01'   days_until=-34  overdue=True   severity=URGENT  (control, correct)
```

A deadline 91 days past is presented as **"Due Soon"**.

**Fix.** Derive `overdue` and `severity` from the parsed `days_until` (`days is not None and days < 0`), never from a string comparison — `schedule_response_packet` at `case_store.py:1362` already does exactly this and is correct.

---

## BUG-4 — Unvalidated snooze dates hide urgent items permanently, with no un-snooze

**Severity: high.** The snooze modal is a free-text `Input` with no validation, and `is_snoozed` compares the stored value to today as a string. Entering a date in any format other than `YYYY-MM-DD` either hides a hard deadline forever or silently does nothing — and there is no code path anywhere in the app that removes a snooze row.

**Location:** `gazelle_state.py:479-484` (`is_snoozed`), `screens/detail.py:167-168` (unvalidated input), `app.py:734-737` (write path).

```python
def is_snoozed(source_db, item_type, item_id, today=None) -> bool:
    until = get_snooze(source_db, item_type, item_id)
    if not until:
        return False
    today = today or date.today().isoformat()
    return until > today            # ← line 484: string comparison
```

```python
val = self.query_one("#snooze-date", Input).value.strip()
self.dismiss(val or None)           # ← screens/detail.py:167-168, no parsing
```

**Confirmed** (snoozing the schedule response deadline; today = 2026-08-04):

```
snooze until 'next week'   -> is_snoozed=True   removed from urgent queue
                              still is_snoozed=True on 2099-12-31
snooze until 'tomorrow'    -> is_snoozed=True   removed from urgent queue (forever)
snooze until 'Aug 11 2026' -> is_snoozed=True   removed from urgent queue (forever)
snooze until '2026/08/11'  -> is_snoozed=True   removed from urgent queue (forever)
snooze until '08/11/2026'  -> is_snoozed=False  NOT snoozed at all (silent no-op)
no un-snooze API exists:  gazelle_state has no clear_snooze / delete-from-snooze
```

`grep -rn snooze` across the whole app confirms the only writes are `snooze_until` (INSERT/UPSERT); nothing ever deletes. `clear_status()` exists for `item_status` but has no `snooze` counterpart, and no TUI binding or MCP tool calls it.

**Fix.** Validate the modal input with `date.fromisoformat` (reject and re-prompt on failure), compare parsed dates rather than strings in `is_snoozed`, and add a `clear_snooze` with a TUI binding.

---

## BUG-5 — `do_not_use` facts are not blocked and still reach the drafting packet

**Severity: high.** The app's stated principle is that it never presents unverified facts as usable, and the Review Facts screen literally tells the user a `do_not_use` fact is "Excluded from drafting". It is not excluded from anything.

**Locations:**
- `workflow.py:113` — `return status == "needs_source"` (only `needs_source` blocks)
- `workflow.py:382-390` — `_review_action` returns `"Excluded from drafting"` for `do_not_use`
- `document_store.py:66-105` — `draft_context()` selects atoms purely by `status='open'` and domain; never reads `fact_verification`
- `case_store.py:1331-1360` — `schedule_response_packet()` filters on `effective_resolved` and `is_snoozed` only; never reads `fact_verification`

**Mechanism.** `_fact_blocked()` treats only `needs_source` as blocking, so an atom the user explicitly marked `do_not_use` gets `infer_card_status` → `ready_to_draft` and `infer_recommended_action` → `draft_schedule_response`. Separately, neither of the two functions that assemble drafting material consults `fact_verification` at all, so both `needs_source` and `do_not_use` atoms flow into the packet, into `format_draft_context_markdown`, and from there into the `gazelle_ai_draft` prompt — unmarked.

**Confirmed** (ATM-001 → `do_not_use`, ATM-002 → `needs_source`):

```
Today cards:
  coparent:atom:ATM-001 | ready_to_draft | draft_schedule_response   ← do_not_use
  coparent:atom:ATM-002 | blocked        | verify_fact               ← needs_source

draft_context('schedule_response').atom_ids     = ['ATM-001', 'ATM-002']
schedule_response_packet().proposals            = ['ATM-001', 'ATM-002']
'ATM-001' in drafting packet markdown           = True
'do_not_use' / 'Do not use' in packet markdown  = False
Review Facts row for ATM-001: "do_not_use | Excluded from drafting"
```

For the *deadline* card — the primary drafting path (`ACTION_DRAFT_SCHEDULE`, which pulls in up to 15 schedule atoms) — the card status is `due_soon` regardless of how many of its constituent facts are unverified, and inspecting the LLM context bundle shows the exclusion never reaches the prompt in any structured form:

```
context block sources: gazelle, gazelle_detail, gazelle_draft, gazelle_chronology, gazelle_activity
  gazelle_draft    | contains ATM-001: True   | mentions do_not_use: False
  gazelle_activity | contains ATM-001: True   | mentions do_not_use: True   ← only as a raw
                                                 activity-log line, not as a directive
```

`tool_context.gazelle_context_for_card` emits a `gazelle_verification` block only for the card's *own* item, never for the constituent atoms of a deadline card.

**Fix.** Make `_fact_blocked` block on `status in ("needs_source", "do_not_use")` and extend it to deadline cards by checking the atoms they aggregate; and have `draft_context`/`schedule_response_packet` drop `do_not_use` atoms and explicitly tag `needs_source` ones in the packet.

---

## BUG-6 — Workers' comp items never reach the urgent queue, Today, or the briefing

**Severity: high.** The README advertises workers' comp as one of three supported matter types, and `urgent_queue`'s own docstring says "Combined urgent items **across all cases**". It isn't. An urgent workers' comp item — e.g. a statutory appeal window — is invisible on the home screen and invisible to any LLM using `gazelle_briefing` / `gazelle_urgent`.

**Location:** `case_store.py:539-544`.

```python
def urgent_queue(show_resolved: bool = False) -> list[dict]:
    """Combined urgent items across all cases, sorted for display."""
    items: list[dict] = []
    items.extend(response_deadlines())   # coparent meta only
    items.extend(urgent_flags())         # bankruptcy only
    items.extend(urgent_atoms())         # coparent only
```

`workers_comp_atoms()` exists at `case_store.py:1506` and is called only from `app.py:992` (the dedicated Workers' Comp matter screen). It is never called by `urgent_queue`, `today_cards`, or `briefing_packet`.

**Confirmed** — inserted an `atoms` row into the demo `workers_comp.db` with `priority='urgent'`, `status='open'`:

```
workers_comp_atoms():          [('WCA-900', 'urgent')]
urgent_queue ids:              ['deadline:schedule','FLAG-001','FLAG-002',
                                'deadline:all_other','ATM-001','ATM-002']
WCA-900 in urgent queue:       False
WCA-900 in today_cards:        False
WCA-900 in briefing_packet:    False
```

**Fix.** Add `items.extend(workers_comp_atoms(...))` (filtered to urgent/high, mirroring `urgent_atoms`) to `urgent_queue`, or correct the docstring and README if the omission is deliberate — but the current combination is silently misleading.

---

## BUG-7 — AI cache fingerprint is blind to the case data it summarizes

**Severity: high.** `fingerprint_payload`'s docstring is "Stable hash for cache invalidation **when inputs change**", and `_cached_or_run` is documented as returning cache "when fingerprint matches". The fingerprint contains none of the inputs. With a 7-day TTL, an AI brief or draft that analyzed a superseded version of the record is re-served as the current answer.

**Location:** `intelligence.py:107-126` (`_card_fingerprint`); consumed by `_cached_or_run` at `intelligence.py:44-82` and `gazelle_state.get_ai_cache` at `gazelle_state.py:141-163`. TTL is `_AI_CACHE_TTL_DAYS = 7` (`gazelle_state.py:88`).

**Mechanism.** The payload is `{card_id, status, recommended_action, source_item_id, verification}` plus a small `extra`. None of the atom body, action text, linked evidence, sidecar notes, or the actual deadline **date** are hashed. `status` is bucketed (`overdue` / `due_soon` / …), so a deadline can move several days closer without changing it.

**Confirmed** (each mutation applied to the synced demo case DB / sidecar, fingerprint recomputed):

```
baseline fingerprint:                              d41d10c686779c11600849e5
after rewriting ATM-001 body + action_required:    same fingerprint? True
after linking a brand-new evidence row:            same fingerprint? True
after adding a sidecar note to ATM-001:            same fingerprint? True
deadline moved 2026-08-09 -> 2026-08-05
  (5 days out vs 1 day out, both "due_soon"):      same fingerprint? True
     13942c53b382e4a2ce5a2f12 == 13942c53b382e4a2ce5a2f12
```

So a brief that said "you have 5 days to respond" is served verbatim when 1 day remains, and a brief written against facts that have since been rewritten is served as current analysis.

**Partial mitigation, stated honestly:** the TUI does render `cached sidecar @ <timestamp>` in the result header (`app.py:511-514`), and the MCP response carries `cached: true` / `cached_at`. A careful user or agent *could* notice. Nothing tells them the underlying record changed.

**Fix.** Fold the material inputs into the fingerprint — atom body/action text, evidence IDs, note count or latest note timestamp, and the raw deadline date string — rather than only the card's derived display state.

---

## BUG-8 — `save_document()` silently overwrites a prior draft

**Severity: medium.** Loss of user work product with no warning and no recovery path. Realistic because the suggested filename is deterministic per day.

**Location:** `document_store.py:352` (`path.write_text(...)`, no existence check). The suggested name is built at `intelligence.py:250` / `intelligence.py:277` as `f"CaseDraft_{doc_type}_{date.today().isoformat()}.md"`, and `screens/intelligence.py:89` saves under exactly that name from the "Save draft to Nest" button.

**Mechanism.** Generate a draft, save it, revise, regenerate, save again on the same day → identical filename → the first version is destroyed. The return value is `{"ok": True, ...}` with no `overwritten` flag.

**Confirmed:**

```
save_document('CaseDraft_schedule_response_2026-08-04.md', 'Draft v1 ...')
save_document('CaseDraft_schedule_response_2026-08-04.md', 'Draft v2 ...')
same path: True
r2 ok: True | warning/overwrite/backup keys in result: []
file now contains: Draft v2
```

**Fix.** Detect an existing target and either refuse (returning an error the caller can act on), suffix with a counter/timestamp, or write a `.bak` — and surface `overwritten: true` in the result dict either way.

---

## BUG-9 — AI-assistance disclosure silently skipped for the most common draft shapes

**Severity: medium.** Not a wrong fact, but a stated invariant of the module ("Not legal advice", "prepared with AI assistance") that fails exactly in the normal case. A pro se litigant may send or file an AI-drafted letter with no disclosure.

**Location:** `document_store.py:349-350`.

```python
if not body.startswith("#") and "DISCLOSURE" not in body:
    body = f"<!-- {DISCLOSURE} -->\n\n{body}"
```

**Mechanism.** Two independent holes:
1. Any body starting with `#` is exempted — and `#` is precisely how the app's own `structure_template()` output and `gazelle_draft`'s "produce a draft letter in markdown" instruction begin. The exemption presumably assumes the template's inline `**{DISCLOSURE}**` survived, but nothing verifies that the LLM kept it.
2. The guard tests for the literal token `"DISCLOSURE"`, not for the disclosure text. "Disclosure statement" is a Chapter 11 term of art and "financial disclosure" is routine in family law, so a legitimate letter mentioning either suppresses the notice.

**Confirmed:**

```
body='# Schedule Response Letter\n\nDear X, I propose 3:30pm.'
  -> disclosure present: False
body='Dear X,\n\nEnclosed is my DISCLOSURE STATEMENT for the Chapter 13 plan.'
  -> disclosure present: False
body='Dear X,\n\nPlain letter.'
  -> disclosure present: True
```

**Fix.** Test for the actual disclosure sentence (`DISCLOSURE not in body`, comparing the constant, not the word), and drop the `startswith("#")` exemption — prepend as an HTML comment or a leading blockquote regardless.

---

## BUG-10 — `_parse_evidence_ids()` silently drops evidence links that don't match a hardcoded ID pattern

**Severity: medium.** Downstream, this makes the app report a *sourced* fact as unsourced. `workflow._review_action(status, evidence_count)` returns `"Find/source before using"` whenever `evidence_count == 0`, and `_evidence_summary` prints `"No linked evidence"` — a wrong statement about whether a fact has support, in the exact screen built to answer that question.

**Location:** `case_store.py:57-70`.

```python
try:
    parsed = literal_eval(raw)
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
except (ValueError, SyntaxError):
    pass
return re.findall(r"EVD-\d{4}-\d{3}", raw)      # ← line 70
```

**Mechanism.** When `related_evidence` is not a Python list literal, the fallback keeps only substrings matching `EVD-<4 digits>-<3 digits>` exactly, and discards everything else with no error, no log, and no gap report. Since the app reads operator DBs "as-is (no schema migration)", any other evidence-ID scheme silently loses all links. The regex is also non-anchored, so a 4-digit sequence number is truncated rather than rejected.

**Confirmed:**

```
'["EVD-2099-001"]'                     -> ['EVD-2099-001']    (list literal path, fine)
'EVD-2099-001, EVD-2099-002'           -> ['EVD-2099-001', 'EVD-2099-002']
'EVD-2099-0001'                        -> ['EVD-2099-000']    ← truncated to a non-existent ID
'E-2099-001'                           -> []
'EX-14; EX-15'                         -> []
'see evidence ledger items 3 and 4'    -> []
'EVD-2026-1'                           -> []
```

**Scope caveat, stated honestly:** if the operator's DB stores JSON/Python arrays (as the demo seed does), `literal_eval` succeeds and the IDs pass through verbatim — the bug is confined to free-text `related_evidence` fields. I could not determine what real Nest data uses, since real case DBs are correctly kept out of the repo.

**Fix.** Split on common separators and return every non-empty token rather than pattern-matching, and report unresolvable IDs as an explicit gap (the app already has this pattern in `chronology_builder`'s `gaps` list) instead of dropping them.

---

## BUG-11 — Fact-verification write key hardcodes `coparent` while every read uses the card's real matter

**Severity: low** (latent today; would become a cross-matter data-integrity bug the moment BUG-6 is fixed).

**Location:** `app.py:748`.

```python
gazelle_state.set_fact_verification("coparent", "atom", row["atom_id"], status)
```

**Mechanism.** Every *read* of `fact_verification` resolves the matter dynamically:
- `workflow._fact_blocked` (`workflow.py:110-112`) uses `item.get("source_db")`
- `workflow.fact_review_rows` (`workflow.py:299`) uses `source.get("source_db", "coparent")`
- `intelligence._fact_scope` (`intelligence.py:85-88`) uses the card's `source_item.source_db`
- `app.py:643` (`_show_detail` for a fact row) uses the card's `source_item.source_db`

Only the write is pinned to `"coparent"`. For a non-coparent atom card the verification would be written under `("coparent", "atom", <atom_id>)` and read under `("workers_comp", "atom", <atom_id>)` — so the decision would never take effect, and if a coparent atom happened to share the ID, the `do_not_use` would attach to the **wrong matter's** atom.

**Why I am calling it latent rather than active:** the Review Facts route is reachable only from a Today action card, and Today is fed by `urgent_queue`, which (BUG-6) never emits a workers' comp item. So today every card that reaches `fact_review` really is `coparent`, and the two bugs mask each other. I confirmed the key mismatch by reading all four call sites; I could not produce a live wrong-attach without first fixing BUG-6.

**Fix.** Derive the source_db from the row's card the same way `_show_detail` and `_fact_scope` already do, instead of the literal `"coparent"`.

---

## BUG-12 — `GateKeeper.checkin` stores the session before checking `ok`; gate branch is outside the error handler

**Severity: low** (the gate is off unless `GAZELLE_GATE=1`). **Confidence: PLAUSIBLE.**

**Location:** `gazelle_gate.py:129-142`; `gazelle_mcp.py:576-596`.

```python
try:
    ok, msg, session = self._gate.check_in(header)
except Exception as exc:
    return {"ok": False, "error": str(exc)}
self._session = session                     # ← line 133: assigned regardless of `ok`
return {
    "ok": ok,
    ...
    "trust_level": session["trust_level"],  # ← TypeError if session is None
```

**Mechanism (two branches, depending on willow-gate's contract):**
1. If `check_in` returns `(False, msg, <session>)` for a *rejected* header, the keeper still latches it. `authorize()` then stops returning `"DENIED — no live gate session"` and instead delegates to `self._gate.authorize_tool(session, ...)`. Whether that is a bypass depends entirely on what willow-gate puts in a rejected session.
2. If it returns `(False, msg, None)`, `session["trust_level"]` raises `TypeError`. The `gazelle_gate_checkin` branch in `gazelle_mcp._handle` sits **outside** the `try/except` that wraps ordinary `_dispatch` calls, and `main()` calls `_handle(req)` with no handler of its own — so the exception propagates out of the stdio loop and kills the MCP server.

**What I could not verify and why.** `willow_gate` is not installed anywhere on this machine (`find / -name 'willow_gate*'` returns nothing) and is not vendored in the repo, so I could not determine `check_in`'s return contract for a rejected header, and I could not exercise either branch. All 9 enforcement tests in `tests/test_gazelle_gate.py` are `@unittest.skipUnless(_HAVE_GATE, ...)` and skip; the 2 that pass only assert that the gate is inert when disabled. **The entire enforcement path — `checkin`, `checkout`, `authorize`, and the `TOOL_CLASS` map — is unexercised by the test suite**, which is itself the main risk here.

**Fix.** `if not ok: return {"ok": False, "error": msg}` before assigning `self._session`, guard the `session[...]` accesses, and move the gate-tool branch inside `_handle`'s `try/except` (or wrap `_handle(req)` in `main`) so a gate fault cannot take the server down.

---

## Areas I examined and consider clean

- **Path traversal in `document_store._safe_filename()` / `save_document()`.** I could not break it. `../../../ESCAPED.md` → `.._.._.._ESCAPED.md`, `/etc/pwn.md` → `_etc_pwn.md`, `..%2f..%2fx.md` → `.._2f.._2fx.md`, `....//....//y.md` → `...._...._y.md` — all land inside the drafts directory. The `subdir` parameter *is* unsanitized (`document_store.py:339,343`), but no caller passes it: `gazelle_mcp.py:463` and `screens/intelligence.py:89` both omit it, so it is not reachable. (Minor nit only: an empty filename produces a hidden `.md` file.)
- **SQL construction.** No injectable interpolation. Every user- or agent-supplied value is bound. The two f-strings are safe: `gazelle_state.py:247` assembles a WHERE clause from a fixed set of column names with `?` placeholders for all values, and `case_store.py:1294` interpolates a table name that must first match `^[a-zA-Z_][a-zA-Z0-9_]*$` and comes from `sqlite_master` of the app's own copy, not from input. `core/db.py:70-71` uses `psycopg.sql.Identifier`.
- **Bare `except:` / silent swallows.** There are none in the live modules. The two `except Exception: pass` sites are `commit_package.py:155` (swallows only an activity-log write, after the manifest is already durably written) and `src/ecf_parser.py:129` (one of the known orphan modules). `document_store.chronology_builder` catches broadly but records the failure in its `gaps` list rather than hiding it — good practice, worth preserving.
- **MCP write-surface invariant.** I tried to break "agent writes go to the sidecar only, except explicit drafts and commit manifests" and could not. Structurally: `gazelle_note` / `gazelle_resolve` reach only `gazelle_state.db`; `gazelle_save` reaches Nest `drafts/` or the app's own `cases/drafts/`; `gazelle_commit` writes only `legal_commit_<date>.json` into Nest; `gazelle_sync` writes only into the app's own `cases/`. `intelligence.inspect_fact_row` is genuinely review-only — it writes an `ai_cache` row and an activity line, and never calls `set_fact_verification`, matching its documented contract. Notably, `commit_package`'s unvalidated `session_date` does **not** yield traversal, because the `legal_commit_` prefix means every escape attempt needs a `legal_commit_*` directory to exist first; I tested `../../outside/ESCAPED` and got a clean `FileNotFoundError`.
- **Sync / staleness (`sync_cases`, `check_stale`, `_copy_if_updated`).** Behaves correctly on the paths I exercised: `check_stale` is empty after a sync, reports the file after touching the Nest source, and is empty again after re-sync (`shutil.copy2` preserves mtime, so the comparison stays consistent); the workers-comp filename aliases resolve (`wca.db` → `workers_comp.db`). One cosmetic inconsistency, not worth a bug entry: the trailing stale block at `case_store.py:220-225` uses `source / filename` instead of `_find_workers_comp_source`, so an aliased workers-comp DB is never listed there — but the copy has already happened by that point.
- **Sidecar key handling for note / resolve / snooze.** `_item_key` (`case_store.py:87`) and the TUI's `_triage_target` (`app.py:682-696`) agree: the TUI correctly unwraps an action-card row to its `source_item` before writing, so triage from Today lands on `("coparent","atom","ATM-001")` and not on the synthetic `("workflow","action_card",...)` key. I found no way to make a note/resolve/snooze attach to the wrong item through these paths. The one keying defect I did find is the *fact-verification* write, BUG-11.
- **`document_store._safe_filename` ext handling, `list_drafts`, `list_artifacts`, `commit_package.read_latest_manifest`** — no defects found.
- **`legal_documents.content_verified` truthiness.** I suspected a TEXT `'0'` would render as "verified"; I tested it and SQLite's INTEGER column affinity converts it to `0`, so `verified_label` correctly reads `unverified`. **Refuted** — not a bug.
