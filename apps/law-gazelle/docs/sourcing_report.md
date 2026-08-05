# Homestead · Affairs — Sourcing Report

> **Provenance.** Produced by a dedicated sourcing pass on 2026-08-04 and
> reviewed before landing. **Two load-bearing claims were independently
> re-verified:**
>
> 1. **`dateutil.parser.parse` invents missing date components** — reproduced
>    here: `'2026'` → `2026-08-04`, `'June'` → `2026-06-04`, `'30'` →
>    `2026-08-30`. It silently fills from *today*. That is BUG-1 inverted and
>    worse — BUG-1 returns `None` and loses a deadline; this would return a
>    confident wrong date. **Confirmed: keep it out of the deadline path.**
> 2. **`workalendar` reaches GPL through a transitive dependency** — PyPI
>    metadata for `lunardate` reads `GPL-3.0-or-later`. `workalendar`'s own MIT
>    license is irrelevant; the dependency tree is what governs. **This library
>    was named in the sourcing brief as a candidate and would have pulled GPL
>    into an Apache-2.0 project.** The trap was in the request, and the pass
>    caught it.
>
> Remaining license determinations were not independently re-verified. Each
> records where it was checked; confirm from the LICENSE file before adding any
> dependency.


**Date:** 2026-08-04 · **Scope:** open-source code that makes the `homestead-law` /
`homestead.keep` build substantially easier, under Apache-2.0.

**Method note.** Every license below was verified during this session against the
project's own artifacts — the `LICENSE`/`COPYING` file fetched from the canonical
repo over `raw.githubusercontent.com`, and/or the `license` / `license_expression` /
classifier fields in the PyPI metadata (which is generated from the project's own
`pyproject.toml` / `setup.py`). Where a repo LICENSE was ambiguous between BSD-2 and
BSD-3, I grepped for the "Neither the name … endorse or promote" third clause.
GitHub's REST API is blocked from this container, so **commit recency is proxied by
PyPI release history**, which I pulled in full for the load-bearing cases. Where that
proxy is weak, I say so.

**Import-purity note.** `stores/promote_check.py:243-256` AST-scans **our own core
files'** top-level imports against `_NET = {socket, ssl, urllib, http, requests,
httpx, aiohttp, websockets, urllib3}`. It does **not** walk into site-packages. So
`from holidays import US` in a core file passes mechanically. I still tested each
candidate empirically for what it actually pulls into `sys.modules` at import, because
the *spirit* of the gate is import-time network-freeness. **Caveat discovered while
testing:** on CPython 3.11, stdlib `pathlib` itself imports `urllib.parse`, so a naive
"is urllib in sys.modules" test is noise. All results below are baselined against that.

---

## The five

### 1. `holidays` (python-holidays) — **DEPEND**

| | |
|---|---|
| URL | https://github.com/vacanza/holidays |
| License | **MIT** |
| Verified where | Repo `LICENSE` (full MIT text, "Permission is hereby granted, free of charge…", no BSD endorsement clause) **and** repo `pyproject.toml` line 10: `license = "MIT"`. PyPI `license_expression: MIT`. |
| Maintained | **Yes, aggressively.** v0.102 released **2026-08-03** — one day before this report. Release cadence is roughly monthly. |
| Runtime deps | **One**: `python-dateutil` (Apache-2.0 AND BSD-3-Clause dual — repo LICENSE carries the Apache-2.0 grant; PyPI classifiers list both). Which in turn pulls `six` (MIT). |
| Core or adapter | **Core-safe.** Empirically its only `_NET` touch is `socket`, pulled transitively by `holidays/version.py:13` → `importlib.metadata` → `email.message` → `email.utils:29 import socket`. That is a stdlib version lookup, not a network path. Nothing in `holidays` opens a socket. |

**What it solves here.** The `homestead.keep` deadline engine needs a *legal holiday*
calendar, and US court deadline rules are written directly against one. FRCP 6(a)(6)
defines "legal holiday" as the eleven named federal holidays, plus any day declared a
holiday by the President or Congress, plus — for periods measured *after* an event —
any day declared a holiday **by the state where the district court is located**.
`holidays.US(years=…)` gives the federal set with correct observed-day shifting;
`holidays.US(subdiv="MA", …)` gives the state overlay, across **57 subdivisions** (all
50 states, DC, and the territories). That is a near-exact structural match to the rule
text, which is unusual and worth taking.

Verified live in this session:

```
n US federal holiday dates 2026: 12          (11 holidays + one observed shift)
Juneteenth: 2027-06-18 '…(observed)' + 2027-06-19  ← observed logic is present
MA-only 2026: 2026-04-20 "Patriots' Day"     ← subdiv overlay works
subdivisions available: 57
```

**Ties to:** BUG-1/BUG-3 remediation, E-2 (`homestead.keep` deadline engine),
E-8 (the `justice-almanac` edge — this is the *engine-side* half; the almanac supplies
jurisdiction-specific overrides).

**Honest downside.** 13 MB on disk, almost all of it data for 150+ countries we will
never touch — a real cost for a "dependency-light" claim, though it is inert data, not
code surface. More importantly: **it is a national/state holiday calendar, not a court
calendar.** Individual courts close on days `holidays` does not know — local judicial
conference days, county-specific closures, furlough days, emergency closures after
weather. If the engine treats `holidays.US(subdiv=X)` as authoritative it will compute
a confidently wrong deadline. The design must make the calendar **injectable and
overridable per jurisdiction** (which is also what E-8 wants), and the UI must keep
Principle 3's "presented for human confirmation" on top of it. Also: its single dep,
`python-dateutil`, last released **2024-03-01** — 2.4 years. dateutil is effectively
feature-complete and its low churn is not alarming on its own, but it is worth knowing
that a court-deadline tool's transitive tree bottoms out in a slow-moving package.

---

### 2. The counting rules — **WRITE IT OURSELVES (~80 lines)**

This is the single most important finding in the report, and it is a negative one.

**There is no open-source Python court-rules deadline engine.** I searched for one
specifically. The space is entirely commercial: LawToolBox advertises 30,000+ court
rules across all US jurisdictions, Clio's Court Rules covers 50 states and ~2,300
jurisdictions, and the free tools (deadlinecalculator.org, jcalculator.com) are
closed-source web calculators. Nothing open exists to depend on, vendor, or even fork.

That is not a gap to be sad about — it is the correct outcome for this build. The rules
themselves are short. Here is FRCP 6(a)(1) + 6(a)(6) — exclude the trigger day, count
every calendar day including weekends and holidays, then roll forward off any Saturday,
Sunday, or legal holiday — working, on top of `holidays`, in four lines:

```python
def frcp_6a(start: date, days: int, cal) -> date:
    d = start + timedelta(days=days)
    while d.weekday() >= 5 or d in cal:
        d += timedelta(days=1)
    return d
# 14 days from 2026-12-19 (federal cal) -> 2027-01-04   [verified this session]
```

The full set the three matter types need — calendar-day counting, court-day counting
(exclude weekends/holidays *while* counting, e.g. California CCP §12a), backward
counting from a hearing date (where the roll goes *backward*, not forward), and
service-method extensions (FRCP 6(d)'s +3 days for mail; state analogues) — is on the
order of 80–150 lines of pure arithmetic over an injected calendar. Every branch is
testable against published worked examples.

**Why writing it beats depending, specifically here.** A dependency that computes a
court deadline is a dependency you must audit line-by-line anyway, because MISSION
Principle 3 says a missed deadline is harm, not a bug ticket. The audit is the
expensive part; the code is the cheap part. A 100-line module you wrote, with a
regression test per rule and a per-jurisdiction rule table pinned from
`justice-almanac`, is a **smaller trust surface** than any library, and it is the thing
that makes `homestead.keep` worth pinning from other faces. Buying this would be buying
the wrong half.

**Ties to:** E-2, E-8, and the BUG-1/BUG-2 transfer precondition.

---

### 3. Strict date parsing in the core — **WRITE IT OURSELVES (~26 lines)**

BUG-1 and BUG-4 are both parsing failures, and the obvious reach is
`dateutil.parser.parse`. **Do not put `dateutil.parser.parse` in the deadline path.**
It does not fail on garbage — it *invents*. Verified this session:

```
dateutil.parser.parse('2026')     -> 2026-08-04     ← today's month and day filled in
dateutil.parser.parse('June')     -> 2026-06-04     ← today's day filled in
dateutil.parser.parse('30')       -> 2026-08-30
dateutil.parser.parse('Monday')   -> 2026-08-10
dateutil.parser.parse('03/04/2026') -> 2026-03-04   (dayfirst=True -> 2026-04-03)
```

A `content_notes` field reading `"2026"` or `"June"` would silently become a hard
deadline. That is BUG-1's failure mode inverted and strictly worse: BUG-1 returns
`None` and loses the item; this returns a plausible wrong date and the user acts on it.

A fixed `strptime` format list over stdlib does the job and cannot invent. Verified —
it accepts every realistic Law Gazelle fixture and rejects every garbage input:

```python
_FMTS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y", "%B %d %Y",
         "%b %d, %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y")

def parse_date(s: str | None) -> date | None:
    if not s: return None
    s = s.strip().rstrip(",")
    for f in _FMTS:
        try: return datetime.strptime(s, f).date()
        except ValueError: pass
    try: return datetime.fromisoformat(s).date()   # ISO w/ time, offset, Z
    except ValueError: return None
```

```
ACCEPTS: '2026-08-10' 'August 10, 2026' 'July 1, 2026' 'January 1, 2027'
         'May 5, 2026' 'May 5 2026' '08/11/2026' '2026-07-01T00:00:00'
         '1 Jul 2026' 'Aug 10, 2026' '2026-08-10T09:00:00+00:00' '2026-8-4'
REJECTS: 'TBD' 'see order' 'Monday' '2026' 'June' '30' 'on or before Aug 1'
         '12/31/2026 or sooner' '' 'next week'
```

That is the whole of BUG-1's fix, zero dependencies, fully in the import-pure core.
BUG-2 then routes `milestones()` through the same function and skips-with-flag rather
than calling `date.fromisoformat` on a truncated string. BUG-3 derives `overdue` from
the parsed value, never from a string comparison.

One deliberate design point worth writing into `homestead.keep`: `'%m/%d/%Y'` is in the
list but `'%d/%m/%Y'` is not, and the two are indistinguishable for `03/04/2026`.
Either pin US ordering explicitly and document it, or — better, and in keeping with
Principle 3 — return an `Ambiguous` result for two-digit-day/two-digit-month strings
and make the user disambiguate once, then store the ISO form.

---

### 4. `dateparser` — **DEPEND, adapter only**

| | |
|---|---|
| URL | https://github.com/scrapinghub/dateparser |
| License | **BSD-3-Clause** |
| Verified where | Repo `LICENSE` — contains the third "Neither the name of Scrapinghub nor the names of its contributors … endorse or promote" clause. PyPI `license_expression: BSD-3-Clause`. |
| Maintained | **Yes.** v1.4.2 released **2026-08-04** — today. |
| Runtime deps | 4: `python-dateutil` (Apache-2.0/BSD-3), `pytz` (MIT), `regex` (Apache-2.0 AND CNRI-Python), `tzlocal` (MIT). All acceptable; each verified from PyPI metadata. `convertdate` and `langdetect` are **extras only**, not pulled by default — this matters, see the workalendar warning below. |
| Core or adapter | **Adapter only** — not because of network (verified: adds no `_NET` modules at import) but because the core must never guess a deadline. |
| Size | 3.3 MB + 20 KB data. |

**What it solves here.** Two adapter-layer jobs, both outside the deadline path:

1. **BUG-4, the snooze field.** The modal is free text; `"next week"` currently snoozes
   an urgent item forever and `"08/11/2026"` silently no-ops. `dateparser` resolves
   `"next week"` → `2026-08-11` correctly. The right UX is: parse it, **show the user
   the resolved ISO date, require confirmation**, store ISO. Never resolve silently.
2. **Ingest of operator-entered `_meta.response_deadlines`.** When the strict core
   parser returns `None`, the adapter can offer a suggestion for human confirmation
   rather than dropping the value on the floor.

Critically, `dateparser` with `settings={'STRICT_PARSING': True}` **fails closed** where
`dateutil` invents. Verified — it returned `None` for all ten garbage inputs above,
including `'2026'`, `'June'`, `'30'` and `'Monday'`.

**Honest downside.** `regex` is a compiled C extension, so this is the first candidate
that makes a cold `pip install` on a clinic laptop non-trivial (wheels exist for all
common platforms, so in practice it is fine, but it is no longer pure Python). The
whole point of `dateparser` — natural-language flexibility — is *hostile* to a
court-deadline tool if it ever leaks into the core; the guardrail is architectural, not
enforced by the gate, so it needs a comment and a test that asserts
`homestead.keep` does not import it. And 4 transitive deps is a real, if modest, cost
against `dependency-light [promotion criterion]`.

---

### 5. `pypdf` — **DEPEND, core-safe**

| | |
|---|---|
| URL | https://github.com/py-pdf/pypdf |
| License | **BSD-3-Clause** |
| Verified where | Repo `LICENSE` — three-clause BSD (retain notice / reproduce notice / "The name of the author may not be used to endorse or promote"). PyPI `license_expression: BSD-3-Clause`. |
| Maintained | **Yes.** v6.14.2 released 2026-06-23. Very active project under the `py-pdf` org. |
| Runtime deps | **Zero required.** `typing_extensions` only on Python < 3.11; `cryptography`, `Pillow`, `fonttools` are all *extras*. |
| Core or adapter | Core-safe on the network test (verified: adds no `_NET` modules at import). But file I/O belongs in the adapter anyway — put extraction in the adapter, keep the extracted-text data structure in the core. |
| Size | 3.6 MB. |

**What it solves here.** Finish-list **B-1** — PDF sync when source files appear in
Nest, `legal_documents.content_notes` → file path. The job is: given a path, get text
out, hash it, store the text so `document_store` / `chronology_builder` can index it and
so the semantic seam has something to read. `pypdf` does that with no dependency tail,
which is exactly right for a "dependency-light core" claim.

**Honest downside.** `pypdf`'s text extraction is adequate, not excellent — it loses
column order on multi-column layouts and has no table structure. For court documents
(caption blocks, service lists, proof-of-service tables) that will produce mangled text
sometimes. If layout fidelity turns out to matter, the upgrade is **`pdfplumber`** (MIT,
verified from repo `LICENSE.txt` "The MIT License (MIT)"; v0.11.10, 2026-06-15;
actively maintained) — but it pulls `pdfminer.six` (MIT, verified from repo LICENSE) +
`Pillow` + `pypdfium2`, three heavy deps instead of zero. Start with `pypdf`; escalate
only on a real failing document, and put the escalation behind the same adapter
interface so the core never notices. **`pypdf` cannot read scanned PDFs at all** — that
is the OCR question, handled separately below.

---

## Also recommended, lower confidence

### SQLite FTS5 — the zero-dependency baseline that actually clears D-1

**This is the honest answer to the semantic-search bar, and it should be said plainly.**

I read `stores/promote_check.py:267-277`. The `semantic_seam [M]` gate is **purely
structural** — it splits the declared `semantic_seam` on `:`, resolves `module` to a
file, and AST-checks that `symbol` is defined as a function/class/module-level
assignment. It never imports the module, never calls it, and never measures whether the
search is semantic. So the *real* bar is the prose in `stores/README.md`: *"the scaffold
ships the semantic-search socket; the document store is **injected**. The capability
travels; the corpus does not."*

FTS5 satisfies both, at zero dependency cost. Verified available in the ambient
`sqlite3` here (SQLite 3.45.1, `CREATE VIRTUAL TABLE … USING fts5` succeeds). It is
in-process, in-SQLite, open-format, no server, no model download, no network — every
architectural constraint satisfied by construction.

The design that clears the bar honestly:

```python
# homestead/keep/search.py  — import-pure
class Searcher:
    """Reader over an injected corpus. The corpus is a sqlite3.Connection the
    caller opens; this module never resolves a path and never owns the data."""
    def __init__(self, conn, embedder=None): ...
    def search(self, query: str, k: int = 10) -> list[Hit]: ...
```

`semantic_seam: "homestead.keep.search:Searcher"`. Corpus injected → the wood stays with
whoever grew it. `embedder=None` → pure lexical FTS5. Pass an embedder → vector search.
The seam is the same either way, which is the point.

**Do not let the word "semantic" push you into a model dependency you do not need.** For
a household's own case corpus — hundreds to low thousands of documents, and the user
knows their own vocabulary because they wrote most of it — BM25 over FTS5 with a
`porter` tokenizer will outperform a small embedding model on recall of the thing the
user is actually looking for, and it will never hallucinate a neighbour. Ship FTS5 first.

### `sqlite-vec` — **DEPEND (adapter), when and if vectors are actually needed**

| | |
|---|---|
| URL | https://github.com/asg017/sqlite-vec |
| License | **Dual MIT / Apache-2.0** |
| Verified where | Repo root carries **both** `LICENSE-MIT` (full MIT text, "Copyright (c) 2024 Alex Garcia") and `LICENSE-APACHE` (Apache 2.0 text). PyPI `license: "MIT License, Apache License, Version 2.0"`. Either is fine for us; take the Apache-2.0 side for matching. |
| Maintained | **Qualified yes — this is the weak point.** v0.1.9 released 2026-03-31; latest is a *pre-release*, 0.1.10a4, 2026-05-18. Full release history shows a **16-month gap** between 0.1.6 (2024-11-20) and 0.1.7 (2026-03-17). Still pre-1.0 after two years. |
| Runtime deps | **Zero Python deps.** Ships a prebuilt loadable SQLite extension. |
| Core or adapter | **Adapter.** `conn.enable_load_extension()` + loading a `.so` is not core behaviour. |

Verified working here: `vec_version() = v0.1.9`, `CREATE VIRTUAL TABLE … USING vec0(embedding float[4])` succeeds against the ambient sqlite3.

**Why it is the right vector store *if* one is wanted:** it keeps the vectors inside the
same SQLite file as everything else — one file the household owns, in an open format,
no server, no separate index to keep in sync, no `chromadb`-shaped daemon. That is a
near-perfect fit for constraint 1 and constraint 4.

**Honest downside.** Pre-1.0 with a documented long dormancy, in a tool a clinic is
asked to trust — that is a real risk. Mitigate by keeping it strictly behind the
`Searcher` seam so it can be swapped or removed without touching a caller, and by
keeping FTS5 as the default so a `sqlite-vec` failure degrades to lexical search rather
than to no search. Loadable extensions also require `enable_load_extension` to be
compiled in, which some distro Python builds disable — that is a support-burden line
item for a pilot install.

**The embedder is the harder half, and it is already solved.** The app requires a local
Ollama (`llm_client.py`, `OLLAMA_BASE_URL`, default `llama3.2:3b`). Ollama exposes
`POST /api/embed`. That is **~15 lines over the existing `requests` adapter and zero new
Python dependencies** — no `sentence-transformers`, no `torch`, no `huggingface-hub`, no
model2vec, nothing. Write it. This is the second clear "write it ourselves".

### Free Law Project — `courts-db`, `eyecite`, `reporters-db` — **STUDY / pin as data, do not depend**

| | |
|---|---|
| URLs | https://github.com/freelawproject/{courts-db,eyecite,reporters-db} |
| License | **BSD-2-Clause, all three** |
| Verified where | `courts-db` and `eyecite` repo `LICENSE` files both open "BSD 2-Clause License / Copyright (c) 2020, Free Law Project". `reporters-db` repo `LICENSE` is the same BSD text with the endorsement clause **absent** (grepped) → 2-clause. All three PyPI `license_expression: BSD-2-Clause`. **The task brief warned these might not be uniform; here they are.** `juriscraper` is also BSD-2-Clause. |
| Maintained | Yes — `courts-db` 0.10.27 (2026-03-25), `eyecite` 2.7.8 (2026-07-01), `reporters-db` 3.2.66 (2026-06-25). |
| Deps | `courts-db` and `reporters-db`: **zero**. `eyecite`: 6, including `lxml` and `pyahocorasick` (compiled). |

**What I actually measured, rather than assumed.** `courts-db` holds **2,809** courts
(2,111 trial, 364 appellate, 101 bankruptcy). But its matcher is tuned for the strings
that appear in appellate opinions, not the strings a self-represented litigant types:

```
find_court("Court of Appeals of Texas")                          -> ['texapp']   ✓
find_court("E.D. Pa.")                                           -> []          ✗
find_court("Eastern District of Pennsylvania")                   -> []          ✗
find_court("Superior Court of California, County of Los Angeles")-> []          ✗
find_court("Los Angeles County Superior Court")                  -> []          ✗
```

And coverage is lopsided against this face's three matter types: **101 bankruptcy
courts** (excellent — consumer bankruptcy is well served), **71 courts with "family" in
the name** (thin — most states run family matters through general-jurisdiction trial
courts that `courts-db` lists without that word), **4 workers' compensation bodies**
(`arkworkcompcom`, `connworkcompcom`, `njlaborcomp`, `tennworkcompapp` — effectively
useless, since workers' comp is administrative and state-specific).

**So: this is E-8 material, not a dependency.** The *data* — the court identifier
vocabulary, the jurisdiction taxonomy, the `regex`/`examples` fields — is genuinely
valuable and BSD-2 lets us use it however we like. Pin it from `justice-almanac` as a
data table on face 3, exactly as the face doc already argues public data should flow.
Do not put `courts_db` in `homestead.keep`'s dependency list to get a lookup that
returns `[]` on the strings your users actually enter.

**`eyecite` gets a specific warning that is not about license.** It is good software
(verified: it correctly parsed `In re Reynoso, 477 F.3d 1117 (9th Cir. 2007)` including
`court='ca9'`, and `11 U.S.C. § 110`). But finish-list **C-6** is on the books precisely
because `personas.py` promises *"statute lookup: cite the actual law, the actual
deadline, the actual form number."* MISSION says the app does not apply law to facts.
Adding a citation parser puts the capability one import away from the liability, and
*In re Reynoso* turned on **self-presentation**, not on what the code did. If `eyecite`
ever lands in this repo, it should be for **recognising citations the user typed so they
can be linked to the user's own evidence** — never for resolving law. That distinction
needs to be written down before the dependency is added, not after.

### `docassemble` — **STUDY only; do not depend, at all**

License **MIT**, verified from `LICENSE.txt` at the root of
https://github.com/jhpyle/docassemble ("The MIT License (MIT), Copyright (c) 2015-2026
Jonathan Pyle"). Last PyPI release of the umbrella package 1.6.5, 2025-03-04.

MISSION.md names docassemble as the intake direction (step 3), so the license question
matters and the answer is clean. **But docassemble is a server** — Flask, Celery, Redis,
PostgreSQL, a Docker deployment, background workers. Architectural constraint 1
disqualifies the whole thing outright. No component is meaningfully usable standalone:
`docassemble.base.util` is welded to the interview runtime and its session model.

What *is* usable is the **format** and the **community**. Suffolk LIT Lab's
`docassemble.ALToolbox` and the Document Assembly Line are MIT (per the LIT Lab's
published statement that all Document Assembly Line code is MIT on GitHub — I did not
open the individual `LICENSE` file, so treat that as **secondhand and re-verify before
depending**, though nothing here proposes depending on it). The right relationship is
what MISSION already implies: interoperate at the boundary — accept a docassemble
interview's *output* as a case file — rather than adopt the runtime. That is also the
E-9 reconciliation point, since "guided interview front end" and "the affairs you handle
yourself" pull in different directions.

---

## Dependency only, never vendor — MPL-2.0 / LGPL

These are *usable*, with care, as unmodified separately-installed dependencies. Their
source may **never** be merged into an Apache-2.0 file, and any modification to them
must be published under their own license.

| Package | License | Verified | Note |
|---|---|---|---|
| `ocrmypdf` | **MPL-2.0** | PyPI `license_expression: MPL-2.0` | v17.8.1, 2026-07-16, active. The best OCR-a-PDF-in-place tool there is. File-level copyleft: using it as an installed library or, better, as a **subprocess** is fine; copying any of its source into `homestead.keep` is not. Also drags 13 runtime deps. |
| `pikepdf` | **MPL-2.0** | PyPI `license_expression: MPL-2.0` | v10.11.0, 2026-07-31. Arrives transitively under `ocrmypdf`. Same rule. |
| `pymeeus` | **LGPL-3.0** | PyPI `license: 'LGPLv3'` + LGPLv3 classifier | v0.5.12, **2022-12-11 — dormant.** Never a direct dep; it arrives through `convertdate`. See the workalendar warning. Avoid the whole path. |

**Clean OCR alternative, if OCR is wanted at all.** `pytesseract` (**Apache-2.0**,
verified from PyPI `license: 'Apache License 2.0'` + Apache classifier) shelling out to
the `tesseract` binary (**Apache-2.0**, verified from the repo `LICENSE` at
tesseract-ocr/tesseract), with `pdf2image` (**MIT**, verified classifier) to rasterise.
`pdf2image` invokes `poppler-utils` as a **separate process**, which is invocation not
linking — that is the distinction that keeps it clean, see the trap list. Downside:
`pytesseract` last released **2024-08-16, two years ago** — thin wrapper, low churn, but
flag it. And OCR quality on scanned court filings is mediocre without preprocessing.
**My recommendation is to defer OCR entirely** — B-1 says "PDF sync when source files
appear in Nest", and text-layer PDFs (which is what e-filed court documents are) are
handled by `pypdf` alone. Scanned paper is a later problem and a much bigger one.

---

## What NOT to use, and why

### License-incompatible — hard reject

**`PyMuPDF` / `fitz` / `pymupdf4llm` — AGPL-3.0.**
Verified: repo `COPYING` at pymupdf/PyMuPDF is the full **GNU AFFERO GENERAL PUBLIC
LICENSE Version 3**; PyPI `license: "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex
Commercial License"`. An Apache-2.0 project cannot absorb it, and the dual option is a
paid commercial license from Artifex. This is the trap the brief flagged and it is real:
`PyMuPDF` is materially the best PDF text extractor in Python, it is what every blog
post and every LLM recommends first, and it is unusable here. **AGPL §13 is additionally
fatal to the MCP-server shape** — a network-facing tool surface built on AGPL code
triggers the source-provision obligation for anyone who runs it, which is exactly the
thing you cannot ask a legal aid clinic's IT department to reason about.

**`workalendar` — MIT itself, but it drags GPL-3.0 and LGPL-3.0 into your tree.**
**This is the most valuable warning in this report**, because `workalendar` is the
single most obvious thing to reach for when you need US business-day and holiday math,
its own license is clean, and the problem is invisible unless you walk the tree.

- `workalendar` LICENSE: MIT (verified, repo `LICENSE`, "Permission is hereby granted,
  free of charge…"). PyPI classifier: MIT. **So far so good.**
- Its PyPI `requires_dist` lists, **unconditionally, not as extras**:
  `['python-dateutil', 'lunardate', 'convertdate', 'pyluach', …]`.
- **`lunardate` is GPL-3.0-or-later.** Verified twice: its `setup.py` contains
  `license = 'GPL-3.0-or-later'`, and its `LICENSE.txt` is the GNU General Public
  License text. PyPI `license: 'GPL-3.0-or-later'`.
- **`convertdate` (MIT) requires `pymeeus`, which is LGPL-3.0.** Verified from PyPI
  metadata for both.

So `pip install workalendar` puts GPL-3.0 code in the runtime environment of an
Apache-2.0 product. Reasonable people argue about whether *importing* a GPL library
across a Python `import` creates a derivative work; **you do not want that argument
happening in a pilot partner's diligence review of a legal tool.** Reject.

And even setting licensing aside, `workalendar` fails the maintenance bar independently:
its last release is **17.0.0 on 2023-01-01 — three and a half years ago.** For a
dependency that decides when a court deadline falls, dormancy is disqualifying on its
own. `holidays` does the same job, MIT, with one clean dependency, shipping monthly.

**`pdftotext` (the PyPI package) — MIT wrapper, GPL-2.0 payload.**
PyPI `license_expression: MIT`, so it looks safe in a metadata scan. It is a C++
extension that **links libpoppler**, which is GPL-2.0-or-later. Linking makes the
combined work GPL. The metadata will not tell you this. Contrast with `pdf2image`, which
*shells out* to the `pdftoppm` binary — separate process, mere aggregation, clean. That
linking-vs-invoking line is the whole difference and it is worth writing into whatever
dependency policy `homestead-affairs` adopts.

**`camelot-py` — MIT wrapper, AGPL backend.** Its Ghostscript backend is AGPL. Same
shape as above.

**Anything GPL/AGPL generally**, and specifically: do not reach for AGPL tools "as an
optional extra." An optional dependency that a user installs is still a dependency your
install instructions created.

### Architecturally disqualified regardless of license

**`chromadb`, `qdrant-client` + server, `weaviate`, PostgreSQL + `pgvector`, `milvus`.**
Licenses vary and several are Apache-2.0. All require a server or a heavyweight
persistent runtime. Constraint 1 rejects them. `chromadb` in particular markets an
"embedded" mode that is a large dependency tree with its own storage format — not the
open SQLite-and-plain-files posture constraint 4 requires.

**`txtai` — Apache-2.0 (verified: PyPI `license: "Apache 2.0…"` + Apache classifier),
actively maintained (v9.12.0, 2026-07-30), and still a reject.** Its required deps are
`torch`, `transformers`, `faiss-cpu`, `huggingface-hub`, `safetensors`, `numpy` — that
is multiple gigabytes and dozens of transitive packages for a tool whose entire premise
is that a self-represented litigant can install it. Fails "dependency-light" by an order
of magnitude. It is genuinely good software for a different deployment.

**`fastembed` — do not use, and note the metadata problem.** Its PyPI `license` field
says `"Apache License"` but its **classifier says `License :: Other/Proprietary
License`.** That inconsistency alone means I could not verify it to the standard this
report requires — mark **UNVERIFIED**. Independently it has **19 runtime dependencies**
including `requests` and `onnxruntime`. Not recommended on either ground.

**`model2vec` — MIT (verified: repo `LICENSE`, "MIT License, Copyright (c) 2024 Thomas
van Dongen"), v0.8.2 2026-05-29, only 6 deps** — the most defensible of the local-embedder
options, and still not recommended here. Verified empirically: **importing it pulls
`socket` and `ssl`** via `huggingface_hub`, i.e. real network machinery, not the benign
`importlib.metadata` chain `holidays` triggers. Adapter-only at best, and only with
`local_files_only=True` plus a vendored model file. Given that Ollama is already a
required component and already does embeddings, this is a dependency with no job.

**`usearch` — Apache-2.0 (PyPI `license: 'Apache-2.0'`; its `numkong` dep is also
Apache-2.0), active (v2.26.0, 2026-07-10).** Clean, but it stores vectors in its own
index file *outside* SQLite, which splits the household's data across two formats and
two consistency domains. `sqlite-vec` keeps one file. Prefer `sqlite-vec`.

**`sentence-transformers`** — Apache-2.0, but pulls `torch` + `transformers` +
`scikit-learn` + `scipy`. Same weight objection as `txtai`.

### Rejected on "a dependency where there is no problem"

**The `mcp` Python SDK.** MIT (verified: PyPI `license: 'MIT'` + classifier), v2.0.0
2026-07-28, well maintained. And it has **16 required runtime dependencies** —
`starlette`, `uvicorn`, `pydantic`, `opentelemetry-api`, `pyjwt[crypto]`,
`sse-starlette`, `python-multipart`, `httpx2` — most of which exist to serve HTTP
transports this app will never use. `gazelle_mcp.py` is 624 lines of newline-delimited
JSON-RPC over stdin/stdout and it works. Adopting the SDK would trade a working
zero-dependency stdio loop for a web framework, and would put `httpx` and `starlette` in
the import graph of a tool that promises no network egress. **Keep the hand-rolled
server.**

**The `ollama` Python client.** MIT (verified: PyPI `license_expression: MIT`), v0.6.2
2026-04-29. Pulls `httpx` + `pydantic` to replace roughly fifteen lines of `requests`
that `llm_client.py` already has. No.

**`pluggy` (MIT, v1.6.0 2025-05-15) and `stevedore` (Apache-2.0, v5.9.0 2026-07-02) for
the matter-type registry (E-4) — the answer is a plain dict of dataclasses.**
Both licenses are fine; both are well maintained; neither should be used here, for two
reasons.

*Design.* The face doc is explicit: *"Matter packs live **inside** `homestead-law` —
custody, bankruptcy, workers' comp, and later housing, benefits, debt defense, small
claims. They belong to the registry, not the org."* There is no third-party plugin
surface. The registry is a **closed set of seven-ish descriptors defined in the same
repo**. A plugin framework's entire value is loading code the author did not write, and
that is precisely what is not happening.

*Security.* `pluggy` and `stevedore` both discover implementations through
`importlib.metadata` **entry points** — meaning any distribution installed in the same
environment can advertise a matter type and get its code executed inside a process that
holds custody and bankruptcy records. For an app whose §6 lane rule is default-deny
reach, opening an ambient-registration channel is a straight regression.

What E-4 wants is about thirty lines:

```python
@dataclass(frozen=True)
class MatterType:
    key: str                      # "custody" | "bankruptcy" | "workers_comp"
    label: str
    tables: tuple[str, ...]
    item_types: tuple[str, ...]
    deadline_rules: tuple[DeadlineRule, ...]
    render_detail: Callable[[dict], RenderTree]

REGISTRY: dict[str, MatterType] = {m.key: m for m in (CUSTODY, BANKRUPTCY, WORKERS_COMP)}
```

`MATTER_NAV` becomes a view over `REGISTRY`; the per-matter functions in `case_store`
become `render_detail` fields; BUG-6 (workers' comp missing from `urgent_queue`) becomes
structurally impossible, because the queue iterates `REGISTRY.values()` instead of three
hardcoded calls. **That last point is the real argument** — the registry is not a
framework question, it is the fix for a whole class of "we forgot to add matter type N
to function M" defects, of which BUG-6 and BUG-11 are two instances already found.

---

## Where the answer is "write it ourselves"

Collected, because these are the places a dependency would be a mistake rather than a
cost.

| Item | Size | Why |
|---|---|---|
| **Strict date parser** (BUG-1, BUG-2, BUG-4) | ~26 lines | Demonstrated above. Every library alternative either invents dates (`dateutil`) or is too permissive for the core (`dateparser`). A fixed format list cannot invent, and it is auditable at a glance — which is what Principle 3 actually demands. |
| **Court-day / calendar-day counting rules** (E-2, E-8) | ~80–150 lines | No open-source implementation exists to depend on; verified by search. The rules are short arithmetic; the *audit* is the expensive part and you must do it either way. Small and audited beats large and trusted for a value that causes harm when wrong. |
| **Ollama embedding call** (D-1) | ~15 lines | `POST /api/embed` over the `requests` adapter that `llm_client.py` already owns. Replaces `sentence-transformers` / `fastembed` / `model2vec` and their entire dependency trees with nothing. |
| **Matter-type registry** (E-4) | ~30 lines | A frozen dataclass and a dict. `pluggy`/`stevedore` solve third-party plugin loading, which is not the problem, and open an entry-point injection surface, which is a new one. |
| **Append-only / hash-chained record** | ~40 lines | If the canonical store needs tamper-evidence: a `prev_hash` column plus `hashlib.sha256` over a canonically-serialised row, verified on read. There is no library worth adding for this, and a hand-rolled chain in SQLite stays in the open format constraint 4 requires. |
| **Two-device sync / CRDT** | defer entirely | `pycrdt` is MIT (verified classifier), active (v0.14.2, 2026-07-30), and light (`anyio` + `typing-extensions`) — genuinely the best option **if the problem ever exists.** It does not yet. And the architecture already softens it: the canonical record store is one the app **may not mutate**, so only the sidecar needs merging, and last-write-wins plus an explicit conflict list is a correct and much smaller first answer. Revisit when a real household actually runs two devices. |

---

## Summary table

| Candidate | License | Verified from | Maintained | Verdict | Core? |
|---|---|---|---|---|---|
| `holidays` | MIT | repo LICENSE + `pyproject.toml` L10 | v0.102, 2026-08-03 | **depend** | yes |
| counting rules | — | — | — | **write (~80 ln)** | yes |
| strict date parser | — | — | — | **write (~26 ln)** | yes |
| `dateparser` | BSD-3-Clause | repo LICENSE (3rd clause present) | v1.4.2, 2026-08-04 | **depend** | adapter only |
| `pypdf` | BSD-3-Clause | repo LICENSE + PyPI expr | v6.14.2, 2026-06-23 | **depend** | yes (I/O in adapter) |
| SQLite FTS5 | stdlib | — | — | **use as baseline** | yes |
| `sqlite-vec` | MIT / Apache-2.0 | repo LICENSE-MIT + LICENSE-APACHE | v0.1.9 2026-03-31; pre-1.0, past 16-mo gap | **depend if needed** | adapter |
| Ollama embeddings | — | — | — | **write (~15 ln)** | adapter |
| matter-type registry | — | — | — | **write (~30 ln)** | yes |
| `courts-db` / `reporters-db` | BSD-2-Clause | repo LICENSE (no endorsement clause) | 2026-03 / 2026-06 | **pin as data (E-8)** | n/a |
| `eyecite` | BSD-2-Clause | repo LICENSE | v2.7.8, 2026-07-01 | **study; C-6 risk** | n/a |
| `pdfplumber` | MIT | repo LICENSE.txt | v0.11.10, 2026-06-15 | fallback only | adapter |
| `docassemble` | MIT | repo LICENSE.txt | v1.6.5, 2025-03-04 | **study; it's a server** | no |
| `pytesseract` + tesseract | Apache-2.0 both | PyPI + tesseract repo LICENSE | wrapper 2024-08-16 (stale) | defer OCR | adapter |
| `ocrmypdf`, `pikepdf` | **MPL-2.0** | PyPI `license_expression` | active | **dependency only, never vendor** | adapter |
| `pymeeus` | **LGPL-3.0** | PyPI license + classifier | 2022-12 dormant | **avoid the path** | — |
| `workalendar` | MIT **but pulls GPL-3.0 `lunardate` + LGPL-3.0 `pymeeus`** | workalendar LICENSE; lunardate `setup.py` + LICENSE.txt | last release 2023-01-01 | **REJECT** | — |
| `PyMuPDF` / `pymupdf4llm` | **AGPL-3.0** | repo COPYING | active | **REJECT** | — |
| `pdftotext` (PyPI) | MIT wrapper, **links GPL-2.0 poppler** | PyPI expr + poppler | active | **REJECT** | — |
| `camelot-py` | MIT wrapper, **AGPL Ghostscript backend** | PyPI | active | **REJECT** | — |
| `txtai` | Apache-2.0 | PyPI license + classifier | v9.12.0, 2026-07-30 | reject on weight (torch) | — |
| `fastembed` | **UNVERIFIED** (`license` says Apache, classifier says Proprietary) | PyPI metadata conflict | active | **do not use** | — |
| `model2vec` | MIT | repo LICENSE | v0.8.2, 2026-05-29 | not needed; pulls socket+ssl | adapter at best |
| `usearch` | Apache-2.0 | PyPI license | v2.26.0, 2026-07-10 | prefer `sqlite-vec` | — |
| `mcp` SDK | MIT | PyPI license + classifier | v2.0.0, 2026-07-28 | reject: 16 deps vs working 624-line server | — |
| `ollama` client | MIT | PyPI expr | v0.6.2, 2026-04-29 | reject: httpx+pydantic for 15 lines | — |
| `pluggy` / `stevedore` | MIT / Apache-2.0 | PyPI license + classifiers | active | reject: use a dict | — |
| `pycrdt` | MIT | PyPI classifier | v0.14.2, 2026-07-30 | defer | — |
| `chromadb` etc. | various | — | — | reject: needs a server | — |

---

## Net effect on the promotion bar

If the recommendations above are taken, `homestead.keep`'s **required** runtime
dependency list is:

```
holidays        # -> python-dateutil -> six
pypdf           # -> nothing
```

Two direct, three transitive, all MIT / BSD-3 / Apache-2.0. Plus stdlib `sqlite3` for
both persistence and search. `dateparser` and `sqlite-vec` sit in the adapter layer and
are optional extras. That is a defensible reading of *dependency-light*, and it leaves
the deadline arithmetic — the part where being wrong is harm — as code this project
wrote, tested, and can point at.

ΔΣ=42
