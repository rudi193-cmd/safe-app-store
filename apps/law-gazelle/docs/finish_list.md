# Law Gazelle — Finish List

> **Reconciled 2026-08-04 — much of this list is dead.** It was written when the
> plan was to *repair* law-gazelle; the decision is now to **rebuild** as
> `homestead-law`. Six of Track A and one of Track B describe work that will
> never happen; five more items are resolved by design decisions. Verdicts are
> in [`docs/STATE.md`](../../../docs/STATE.md) — **read that before working
> anything here.**
>
> Still live and unchanged by the rebuild: **C-6** (`personas.py` is still in
> this repo and is still a liability), C-3, C-5, E-1, E-4, E-7 through E-12, and
> all of Track F.

*The standing list of what remains, across all five tracks. Kept here rather
than in a session, because the work spans sessions.*

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
standing between this app and a passing `tests_green [M]` gate — though A-1's
end state is now E-3, which deletes the dependency rather than declaring it.*

| # | Item | Where | Status |
|---|---|---|---|
| **A-1** | **Declare the host-lib dependencies.** `requirements.txt` is `requests` + `textual`; `pyproject.toml` declares the same two. But `gazelle_paths.py`, `safe_integration.py`, and `core/db.py` import `vault_paths` / `pg_sqlite_shim`, and `gazelle_paths` sits under nearly every import chain in the app. Tests pass in CI only because `store-ci.yml` installs `libs/vault-paths` and `libs/pg-sqlite-shim` out of band. The declared dependencies are false relative to what the code imports. **Superseded as an end state by E-3** — with `/.homestead`, `vault_paths` is deleted rather than declared — but A-1 remains the correct *interim* fix, because until E-3 lands a cold checkout still fails and `tests_green [M]` stays red. | 🟢 here | open |
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
| **D-2** | **Restructure an import-pure core worth declaring** — a real `law_gazelle/` package holding the network-free logic (deadline computation, queue ranking, detail assembly), with the TUI, MCP server, and Ollama client as impure adapters outside it. **Superseded by E-2** — the import-pure core is `homestead.keep` in the seat repo, shared by every module on the face rather than private to this one. | 🟢 here | superseded |
| **D-3** | **Extract to its own repo**, then repoint this host as a consumer. Follows Nestor and Jeles as the worked standard. **Superseded by E-5** — the destination is named: `homestead-affairs/homestead-law`. | 🟡 decision + 🟢 here | superseded |
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

## Track E — Face 4 · `homestead-affairs`

*The die placement: this app becomes **`homestead-law`**, module one of
**Homestead · Affairs** — "the affairs you handle yourself." Full reasoning in
[`docs/homestead-affairs-face.md`](../../../docs/homestead-affairs-face.md).
Several of these **supersede** items in Tracks A and D rather than adding to
them; cross-references are noted.*

**Already done:** GitHub org stood up as **`homestead-affairs`** (handle confirmed 2026-08-04 — no rename needed) · `.github` repo created.

| # | Item | Where | Status |
|---|---|---|---|
| **E-0** | ~~Confirm the org handle reads `homestead-affairs`.~~ **Done 2026-08-04** — confirmed correct; the earlier `homestead-sovereign` naming never went live, so no rename and no redirect to clean up. | 🟢 here | **done** |
| **E-1** | **Teach `tools/vault_leak_lint.py` a `HOMESTEAD_HOME` root.** **Do this first — it blocks E-3.** The linter treats a persistence path as clean only when the line derives from `WILLOW_STORE_ROOT` / `WILLOW_HOME`; anything else home-rooted holding data is a leak, and `"case"` is in its data-name hints. `store-ci.yml` runs it `--strict`. Moving to `/.homestead` before the linter learns it flips `vault_leak [M]` — the one promotion gate this app passes — from PASS to FAIL, and reddens CI. Host-side edit, small, lives in this repo. | 🟢 here | open |
| **E-11** | **Nestor seam.** Contract drafted 2026-08-04 — [`docs/drafts/nestor_seam.py`](../../../docs/drafts/nestor_seam.py); destination `homestead-affairs/homestead` → `homestead/keep/nestor_seam.py`. Nestor is Apache-2.0 with **zero required dependencies**, and its `Storage` protocol is genuinely injected. **But the hash-chained ledger is not part of that protocol** — it resolves via `_LEDGER_OVERRIDE` → `$NESTOR_LEDGER` → `data/ledger.jsonl`, and `EntityResolver.resolve()` appends on every call, recording the resolved `canonical` **in cleartext**. Injecting the store is not sufficient; the ledger must be pinned inside `/.homestead` before any resolver is constructed. Seam fails closed if unbound. Blocked on choosing the pin and on E-2. | 🟢 here | drafted |
| **E-2** | **Build `homestead.keep`** — the import-pure record / deadline / evidence engine, in the **seat repo** `homestead`, pinned by tag from each module. **Supersedes D-2**: this is the import-pure core, and it is worth pointing the gate at because it holds real logic rather than a stub. Note the deviation: base repos are optional elsewhere on the die; this seat is load-bearing, because nothing can pin an engine that doesn't exist. | 🟢 here | open |
| **E-3** | **Move path resolution to `/.homestead`** via `homestead.keep.paths`, and **delete the `vault_paths` import**. **Supersedes A-1**: with its own root this stops being a dependency to *declare* and becomes one to *remove*, and `inversion [M]` passes by construction rather than by pinning. **Criterion — audience, not face:** a product gets its own root only when *someone who does not run the fleet installs it*; everything else stays on `~/.willow` + `vault-paths`. Face 4 is currently the only face answering yes. Note the root is **not** for isolation — same uid, same permissions, and a directory name is not a security boundary; the gate and store-scope wall are what keep Nestor out. **`~/.willow` is not being migrated** — the fleet root stays as it is. Blocked on E-1. | 🟢 here | blocked on E-1 |
| **E-12** | **Rung model — `L1`–`L5`.** Drafted 2026-08-04: [`docs/homestead-rungs.md`](../../../docs/homestead-rungs.md). Adapted from `terpsi-music/docs/SENSITIVITY.md`, whose own crossing table was written in the shape of law-gazelle's permission table — the loan runs both ways. Scored against four **surfaces** (operator screen, model prompt, agent/MCP, egress) rather than Terpsi's inter-personal entitlement edges, which a one-operator household mostly collapses. Key claim: at `L4` the **derived instruction** is the normal serving mode and the payload requires a declared purpose — the Today card reads "medical records response due Aug 15," not the diagnosis. **A model prompt is a rendering**, so `intelligence.py` is a governed path. This is what `_fact_blocked` becomes, and it makes **BUG-5 unrepresentable** (`do_not_use` → `L5`, never served anywhere). Blocked on E-2. | 🟢 here | drafted |
| **E-4** | **Matter-type registry** — descriptors carrying tables, item types, deadline rules, and detail renderers, replacing the three hardcoded types in `MATTER_NAV` and the per-matter functions in `case_store`. Prerequisite for any fourth matter type and for the module layer; ranked candidates are housing (eviction/foreclosure), debt-collection defense, benefits appeals, small claims. **Bankruptcy is retained** — highest-exposure matter type in the legal review, and the doctrinal root of the artifact's name. | 🟢 here | open |
| **E-5** | **Extract to `homestead-affairs/homestead-law`**, then repoint this host as a consumer. **Supersedes D-3.** Promotion is an extraction with preconditions, not a tree move: BUG-1/BUG-2 fixed with regression tests, E-2 and E-3 done, D-1 built. | 🟡 decision + 🟢 here | blocked |
| **E-6** | **Place `private-ledger` on the face as module two.** Already built, currently faceless. Settle whether it keeps its name — the earlier rejection of `homestead-ledger` was about a settler-order module *inside* `homestead-law`, a different question. | 🟡 decision | open |
| **E-7** | **Re-derive the module names.** `compact / claim / ledger / fence / remedy` came from the "settler order without a county" framing that the rename removes. *Claim*, *remedy*, *ledger* may survive on merit; *compact* and *fence* came from the settler framing specifically. Do not inherit them through a rename. | 🟡 decision | open |
| **E-8** | **Draw the `justice-almanac` → deadline-engine edge.** Court rules and deadline tables are public data and belong to face 3, which already has that vertical. Tables pinned from the almanac; engine lives here. Gives face 4 a producer role instead of pure consumption. | 🟡 decision | open |
| **E-9** | **Reconcile `MISSION.md` with the face.** It tells an access-to-justice story — pilot org, docassemble, LSC TIG grants — that is not the same product as *the affairs you handle yourself*. Both are defensible; they are not identical, and MISSION is still the only document a partner org would read. | 🟡 decision | open |
| **E-10** | **Write the org profile — `homestead-affairs/.github` → `profile/README.md`.** The repo exists and is empty. This is the first thing a reader sees on the org, including a pilot partner's ethics counsel running diligence, and it is a **self-presentation surface**: *In re Reynoso* turned on how a tool described itself, not on what its code did, and *FTC v. DoNotPay* is the same shape for capability claims. The handle was made safe; the profile is the next place the same care applies. It must say what the household holds, never what the software knows — and it must not out-claim `MISSION.md`, which is itself unreconciled (**E-9**). Draft it before the org is shown to anyone. **Draft written 2026-08-04** — [`docs/homestead-affairs-profile-README.md`](../../../docs/homestead-affairs-profile-README.md); review, then copy to `homestead-affairs/.github` as `profile/README.md`. | 🟢 here | **drafted** |

**Ordering inside Track E:** E-1 → E-2 → E-3 are a chain and the only part that
is pure engineering. E-4 is independent and can run in parallel. E-5 is the
gate, blocked on everything above plus the two critical bugs. E-6 through E-9 are decisions,
not builds. **E-10 gates showing the org to anyone outside.**

---

## Track F — Household safety

*From [`household_safety.md`](household_safety.md), 2026-08-04. Every item below
was **independently re-verified in source** before landing. These outrank most of
Tracks A–E: they are exposures to a person whose adversary may share their
house.*

| # | Item | Where | Status |
|---|---|---|---|
| **F-1** | **`dev.sh` puts the case package on the Desktop.** `dev.sh:17` defaults `NEST_SOURCE` to `$HOME/Desktop/Nest`, overriding the clean vault default at `gazelle_paths.py:30`. Drafts, letters, DBs and `legal_commit_<date>.json` — an index of the whole case — land in the least private directory on a shared machine. The documented launcher is the leak. Fix: default to the vault; make Desktop an explicit opt-in with a warning. `L3`–`L4` · S4. | 🟢 here | open |
| **F-2** | **The authorization gate never sees the operator.** `gazelle_gate` is imported only by `gazelle_mcp.py`. `app.py` does not import it, so with `GAZELLE_GATE=1` fully configured the TUI's save-to-Nest export — the very thing the gate exists to ledger — is ungated, along with every local-LLM call and sidecar write. The control governs agents and is blind to the screen. | 🟢 here | open |
| **F-3** | **The citation regex matches home addresses and POSTs them.** `_CITATION_RE` (`tool_context.py:29`) matches `1420 Maple 87501`; `courtlistener_search` issues a live `requests.get`; `build_context_bundle` defaults `include_courtlistener=True`. It also *misses* `347 F.3d 1120`, so it fails in both directions. In a custody matter this is a residential address, possibly protected. Fix: anchor on reporter abbreviations, and default the flag off. `L4` · S4. | 🟢 here | open |
| **F-4** | **Private notes reach the model prompt via the activity log.** `add_note` copies the first 80 chars of every note into the activity log (`gazelle_state.py:415`); `tool_context.py:149` puts the last 8 activity rows into every prompt. Under the rung model a prompt is a rendering (**E-12**), so this is `L3`/`L4` content on S2 with no purpose declared. The log is also one keystroke (`a`) from the TUI — a confession timeline for anyone who opens the app. | 🟢 here | open |
| **F-5** | **No authentication, lock, or timeout anywhere.** One command renders the whole record; `on_mount` draws the queue before any human input. Cannot be fully solved — a shared OS account is the same uid and is not securable by an application — but a cover screen, an idle blank, and a deliberate encrypted move-off-machine flow are all real mitigations. **Do not ship a panic wipe:** spoliation, discoverability under oath, it does not reach the canonical store or editor backups, and given the lack of any lock it is equally the *adversary's* destroy key. | 🟡 decision + 🟢 here | open |
| **F-6** | **Split the audit trail.** A supervising attorney, LSC Part 1636 and any breach clock all require a log; the abuser reads it with one keypress. Recommendation: a redacted operator-visible log plus a sealed hash-chained one the app can append to but never render. Cost: two logging paths, and the sealed half is worthless to a user who loses the key. | 🟡 decision | open |
| **F-7** | **No subject apparatus for the other parent or the child.** The app holds a structured dossier on third parties with no party index, no source requirement, no purpose scoping, and `"permanent local"` retention. No classifier can distinguish an evidence chronology from a surveillance log — only provenance, scope and purpose can. Require a source and an issue for every third-party observation. Depends on **E-12**. | 🟢 here | open |
| **F-8** | **First-run shared-machine question, ending in a referral.** If the answer is "yes, with the other party," the right destination is a domestic-violence safety-planning referral, not a settings page. Documentation and copy, not a control. | 🟢 here | open |

---

## Suggested order

> **Before any of this: Track F, then [`bug_list.md`](bug_list.md) BUG-1 and
> BUG-2.** Track F's F-1 and F-3 are exposures to a person whose adversary may
> share their house; F-3 sends data off-device. They come first.
>
> **Then: BUG-1 and BUG-2.** A
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
4. **E-1 → E-2 → E-3** — the face-4 engine chain, and the only part of Track E
   that is pure engineering. E-1 first or CI goes red. E-3 retires A-1.
5. **C-2, C-3** — prove the demo and the privacy claim, since both are already
   asserted in public-facing docs.
6. **D-1 + E-4** — the semantic seam and the matter-type registry. Both are
   better architecture whether or not promotion happens. (D-2 is retired by
   E-2.)
7. **B-1, B-2** — feature surface, on fixtures here, verified by the operator
   against real Nest.
8. **E-5, D-4 → D-6** — extraction, attestation, witnessed run. Needs D-6
   (the verifier) answered first.

Decisions outstanding: **E-6** (private-ledger's name), **E-7** (module names),
**E-8** (almanac edge), **E-9** (MISSION vs the face), **B-4** (draft evidence
guard), **B-5** (CourtListener:
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
