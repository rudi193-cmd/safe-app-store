# Law Gazelle — Finish List

*The standing list of what remains, across all four destinations. Kept here
rather than in a session, because the work spans sessions.*

**Last verified:** 2026-08-04 · **b17:** E472A

---

## Verified state (not claimed — measured)

Everything below was run against this checkout. The commands are in
[Re-checking](#re-checking) so any line here can be falsified.

| Check | Result |
|---|---|
| `pytest tests/` **with CI deps installed** | **72 passed, 9 skipped** (skips: `willow-gate not installed`) |
| `pytest tests/` **from a cold checkout** | **7 collection errors** — `ModuleNotFoundError: No module named 'vault_paths'` |
| bare `pytest -q` (*what the promotion gate runs*) | **1 collection error** — `_archived/test_case_store.py` shadows `tests/test_case_store.py` |
| `tools/vault_leak_lint.py --app law-gazelle` | **PASS** — 0 FAIL · 0 WARN · 0 UNKNOWN |
| Python LOC (excl. `_archived/`) | 9,333 |
| Catalog (`.willow/store/catalog.json`) | `status: gated`, `tier: playground` |
| Keeping record (`stores/python/stored/law-gazelle.json`) | `state: gated` |
| `promotion.json` | absent |

**Blocker legend** — where an item can actually be done:

- 🟢 **here** — doable in the repo/container, verifiable now
- 🔴 **private data** — needs real Nest at `~/Desktop/Nest` or
  `~/.willow/apps/law-gazelle/`; per `CLAUDE.md` that never enters git and is
  not in any container. Buildable against synthetic fixtures, *verifiable*
  only on the operator's machine
- 🟣 **second hand** — §0.2: proposing and ratifying never rest in the same
  hand, so this cannot be done by whoever did the building
- 🟡 **decision** — needs a call, not a commit

---

## Track A — Cheap real fixes

*Worth doing regardless of destination. A-1 and A-2 are the only things
standing between this app and a passing `tests_green [M]` gate.*

| # | Item | Where | Status |
|---|---|---|---|
| **A-1** | **Declare the host-lib dependencies.** `requirements.txt` is `requests` + `textual`; `pyproject.toml` declares the same two. But `gazelle_paths.py`, `safe_integration.py`, and `core/db.py` import `vault_paths` / `pg_sqlite_shim`, and `gazelle_paths` sits under nearly every import chain in the app. Tests pass in CI only because `store-ci.yml` installs `libs/vault-paths` and `libs/pg-sqlite-shim` out of band. The declared dependencies are false relative to what the code imports. | 🟢 here | open |
| **A-2** | **Stop `_archived/` shadowing the live suite.** `_archived/test_case_store.py` and `tests/test_case_store.py` share a module basename, so bare `pytest -q` dies at collection. The spec footnotes this as a "use `pytest tests`" workaround — but `promote_check.py` runs bare `pytest -q` with `cwd=candidate`, so the workaround is not available to the gate. Fix by excluding `_archived` from collection (`[tool.pytest.ini_options] norecursedirs`) or renaming the archived file. | 🟢 here | open |
| **A-3** | **Correct the spec's stale boxes.** `docs/law_gazelle_spec.md` Phase 3 lists "archive or remove dead stubs (`legal_db.py`, old `SAFESession` path)" as open, but `legal_db.py` and `gazelle_engine.py` are *already* in `_archived/`. The archiving happened; the doc didn't. | 🟢 here | open |
| **A-4** | **`safe_integration.py` self-shadowing re-export.** The top-level module does `sys.path.insert(0, .../src)` then `from safe_integration import SAFESession` — importing a different module of its own name. It resolves today (tests pass), but it depends on path-insert ordering and will confuse anyone reading it, and it mutates `sys.path` at import time. Worth a plain relative import. | 🟢 here | open |
| **A-5** | **README refresh** — spec Phase 3's "update README when the local markdown read hook permits it". | 🟢 here | open |
| **A-6** | **`seed_demo.py` takes any argv[1] as a destination.** `scripts/seed_demo.py:227` is `seed(Path(sys.argv[1])...)` with no parsing, so `--help` seeds four case files into a directory named `--help`; a typo'd path seeds them wherever the typo points. Found by accident on 2026-08-04 — the stray dir had to be deleted rather than committed, since case DBs never enter git. Wrong failure mode for an app whose premise is that case data lands only where the operator expects, and `demo.sh` advertises `--fresh`, which trains flag-passing to this family of scripts. Add argparse: a real `--help`, and refuse a destination that starts with `-`. | 🟢 here | open |
| **A-7** | **Four orphan modules inside the live tree** — 510 LOC imported by nothing, and referenced nowhere outside the Python tree either (no docs, shell, Makefile, or CI): `src/ecf_parser.py` (225), `backfill_from_willow.py` (171, plausibly a standalone script — confirm before archiving), `client_profile.py` (78, imports only itself; its docstring targets `gazelle_engine.create_session()`, which is archived), `personas.py` (36 — see **C-6**, it is more than dead weight). Archive rather than delete (`CLAUDE.md` §4), and check `_archived/` naming against **A-2** so nothing new shadows the live suite. | 🟢 here | open |

---

## Track B — Phase 3 features

*From `docs/law_gazelle_spec.md` § Phase Roadmap. These close the app's own
declared scope.*

| # | Item | Where | Status |
|---|---|---|---|
| **B-1** | **PDF sync** when source files appear in Nest (`legal_documents.content_notes` → file path). | 🔴 private data (build on fixtures) | open |
| **B-2** | **Surface remaining populated tables** — `decision_log`, communication/correspondence, schedule, hearing log. Spec Open Gate #2 asks which group comes next; `legal_documents` was the first pass. | 🔴 private data (build on fixtures) | open |
| **B-3** | **Verify `nest_watcher` alerts on manifest drop** (Phase 1's one open box). Manual, needs the watcher in `willow-1.9` and a real Nest. | 🔴 private data | open |
| **B-4** | **Draft evidence guard** — decide whether `save_document` must auto-reject unverified facts, or keep flagging only. Principle 3 ("verify everything… a missed deadline is not a bug ticket; it is harm") argues for reject; usability argues for flag. Spec Open Gate #4. | 🟡 decision | open |
| **B-5** | **CourtListener** — `include_courtlistener` is accepted by the AI tools, but `tool_context.courtlistener_search` is the only surface and real REST/MCP integration is marked Horizon 2. Either build it or mark the parameter unimplemented so it doesn't read as working. | 🟡 decision | open |

---

## Track C — Pilot-ready

*The finish line if the destination is a legal-aid partner rather than the
store bar. Mostly about a stranger's first five minutes.*

| # | Item | Where | Status |
|---|---|---|---|
| **C-1** | **A cold checkout must work first try.** Same root cause as A-1: `make demo` is advertised as zero-config in both README and MISSION, and a fresh clone can't satisfy the imports without knowing about `libs/vault-paths`. This is the single highest-leverage pilot item — it's the first thing a partner org hits. | 🟢 here | open |
| **C-2** | **Exercise the demo end-to-end on a clean machine** — `./demo.sh --fresh`, confirm the seeded `.demo/` Nest renders Today/urgent/detail and touches nothing outside `.demo/`. | 🟢 here | open |
| **C-3** | **PII scrub before any public push** — confirm repo *history*, docs, and screenshots contain only code, tests, and synthetic data. Spec Open Gate #5, and MISSION's public-repo claim depends on it. | 🟢 here | open |
| **C-4** | **MISSION/README for a non-fleet reader.** MISSION.md is strong already; README still assumes fleet vocabulary (Nest, sidecar, b17, Grove, the session-end ritual). A clinic director is the target reader. | 🟢 here | open |
| **C-5** | **Name the pilot partner** — MISSION step 2. Everything downstream (jurisdiction, intake scope, grant posture) waits on this. | 🟡 decision | open |
| **C-6** | **`personas.py` states the opposite of MISSION.** The "Gazelle" persona describes doing issue classification, "statute lookup: cite the actual law, the actual deadline, the actual form number," and "next steps: what to file, where, by when, what it costs" — that is applying law to facts. MISSION says the app *does not apply law to facts, recommend strategy, or predict outcomes* and will **never** give legal advice. The file is a survivor of the archived `gazelle_engine` template-assistant era and is imported by nothing today, so it changes no behavior — which is exactly why it is filed here rather than under A. It is a **liability in the repo a partner org reads**, and a loaded gun for whoever wires it back in and silently reverses the app's stated ethics. Archive it with a note saying why, so the reversal can't happen by accident. **Escalated 2026-08-04:** independent legal research ([`legal_obligations_us.md`](legal_obligations_us.md) §1) reached this file on its own and rates it a live liability rather than refactoring debt — the persona text is close to a verbatim template for the self-presentation that *In re Reynoso*, 477 F.3d 1117 (9th Cir. 2007), penalized when it swept a bankruptcy-software provider into statutory petition-preparer status for holding itself out as "an expert system [that] knows the law." | 🟢 here | open |

---

## Track D — Promotion gates

*Scored against `stores/promote_check.py` as it actually executes — 9 gates
plus the attestation precondition. **2 of 9 pass today.***

| Gate | Now | What it needs |
|---|---|---|
| `manifest [M]` | ✅ **pass** | `safe-app-manifest.json` has `app_id`, `permissions`, `privacy_tier`. Nothing to do. |
| `vault_leak [M]` | ✅ **pass** | Verified clean. Keep it that way — re-check after B-1/B-2 add write paths. |
| `tests_green [M]` | ❌ fail | **A-1 + A-2.** Two independent failure modes; both must be fixed. The gate installs nothing and uses no workaround. |
| `semantic_seam [M]` | ❌ fail | **Nothing to point at.** No search seam exists — the only `search` in the tree is `tool_context.courtlistener_search`, a remote REST call, not a semantic reader over the app's own knowledge. This is a build (D-1), not paperwork. |
| `import_pure_core [M]` | ❌ fail | **No honest target.** `core/` is 81 lines with an empty `__init__.py`; the app is ~30 flat top-level modules. See D-2 and the warning below. |
| `inversion [M]` | ❌ fail | Core must not import its host. Today `vault_paths` is a host lib imported directly; post-extraction it must be an injected seam or a declared external dependency. |
| `own_repo [A]` | ❌ fail | `repo_url` must not contain `safe-app-store`. This is the extraction — the largest single item (D-3). |
| `host_repointed [A]` | ❌ fail | Host consumes it as a dependency. Depends on D-3. |
| `witnessed [M]` + `attestation` | ❌ fail | No `promotion.json`; and `verified_by` must differ from `author`. |

### Promotion work items

| # | Item | Where | Status |
|---|---|---|---|
| **D-1** | **Build the semantic-search seam** — a reader over the app's own document/case corpus, with the corpus *injected* (`stores/README.md`: "ship the mold and the reader; the wood stays with whoever grew it"). Natural home is alongside `document_store.py` / `chronology_builder`. Buildable against synthetic fixtures. | 🟢 here | open |
| **D-2** | **Restructure an import-pure core worth declaring** — a real `law_gazelle/` package holding the network-free logic (deadline computation, queue ranking, detail assembly), with the TUI, MCP server, and Ollama client as impure adapters outside it. | 🟢 here | open |
| **D-3** | **Extract to its own repo**, then repoint this host as a consumer. Follows Nestor and Jeles as the worked standard. | 🟡 decision + 🟢 here | open |
| **D-4** | **Write `promotion.json`** — `app_id`, `author`, `verified_by`, `repo_url`, `host`, `core_module`, `semantic_seam`, `host_repointed`, `major: python`. Only truthfully authorable *after* D-1→D-3. | 🟢 here | blocked on D-1..D-3 |
| **D-5** | **Run the gate and record the verdict** — `--record` writes `stores/python/promoted/law-gazelle.json`. | 🟣 second hand | blocked |
| **D-6** | **Choose the verifier.** Open as of 2026-08-04. Cannot be whoever authors the build. | 🟡 decision · 🟣 | open |

> **A warning worth keeping in the list.** `core_module: "core"` would
> *technically* resolve against the existing 81-line stub and probably clear
> the network scan — a passing gate that measured nothing. That is precisely
> the hollow-attestation failure mode: pointing the check at a stub so it finds
> nothing to object to. D-2 exists so the gate has something real to measure.
> A green gate over an empty target is worse than a red one, because it spends
> trust it didn't earn.

---

## Suggested order

> **Before any of this: [`bug_list.md`](bug_list.md) BUG-1 and BUG-2.** A
> dedicated bug pass found 12 defects, two of them critical, in the deadline
> arithmetic — a long-form date like `"July 1, 2026"` parses to `None`, so an
> overdue court deadline renders as not-overdue and sinks in the urgent queue;
> the same value raises an uncaught `ValueError` out of `milestones()` and takes
> down the briefing packet and the TUI refresh. Nothing on this list outranks a
> wrong answer about when something is due.

1. **A-1, A-2** — the only fixable-today reason a mechanical gate is red, and
   the same fix is C-1, the top pilot item. One change, two tracks.
2. **A-6, C-6** — the two items that are wrong in a way a reader can see:
   a seeder that writes case files wherever the first argument points, and a
   persona file asserting the app does the thing MISSION promises it never
   does. Neither changes behavior today; both misrepresent the app.
3. **A-3, A-4, A-5, A-7** — hygiene, cheap, while the context is loaded.
4. **C-2, C-3** — prove the demo and the privacy claim, since both are already
   asserted in public-facing docs.
5. **D-1, D-2** — the two real builds. Independently valuable: a search seam
   and a pure core are better architecture whether or not promotion happens.
6. **B-1, B-2** — feature surface, on fixtures here, verified by the operator
   against real Nest.
7. **D-3 → D-6** — extraction, attestation, witnessed run. Needs D-6 answered
   first.

Decisions outstanding: **B-4** (draft evidence guard), **B-5** (CourtListener:
build or mark unimplemented), **C-5** (pilot partner), **D-6** (verifier).

---

## Re-checking

```bash
# From repo root — the CI environment, reproduced
pip install -e libs/vault-paths -e libs/pg-sqlite-shim
pip install -r apps/law-gazelle/requirements.txt pytest

cd apps/law-gazelle
python3 -m pytest tests/ -q          # what CI runs        → 72 passed, 9 skipped
python3 -m pytest -q                 # what the gate runs  → currently errors (A-2)

# From repo root
python3 tools/vault_leak_lint.py --app law-gazelle       # → PASS
python3 stores/promote_check.py apps/law-gazelle         # → no promotion.json (fail-closed)
```

A cold check — no installs — is the honest one for A-1 and C-1:

```bash
python3 -m venv /tmp/lg && /tmp/lg/bin/pip install -q pytest
cd apps/law-gazelle && /tmp/lg/bin/python -m pytest tests/ -q
```

---

## Related

- [`MISSION.md`](../MISSION.md) — who this serves, and the four things it will never do
- [`docs/law_gazelle_spec.md`](law_gazelle_spec.md) — architecture, phase roadmap, open gates
- [`stores/promote_check.py`](../../../stores/promote_check.py) — the gate, and the `[M]`/`[A]` split
- [`stores/README.md`](../../../stores/README.md) — the promotion bar in prose
- [`docs/on-this-side-of-the-law.md`](../../../docs/on-this-side-of-the-law.md) — Part VII reads this gate as a legal order; the hollow-attestation warning above is its argument applied here

ΔΣ=42
