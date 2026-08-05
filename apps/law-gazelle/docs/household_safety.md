# Law Gazelle / Homestead · Affairs — household safety & security analysis

> **Provenance.** Produced by a dedicated safety pass on 2026-08-04. **Every one
> of the top five was independently re-verified against the source before this
> landed** — these are not reported claims:
>
> - **Desktop default — CONFIRMED.** `dev.sh:17` is
>   `NEST_SOURCE="${NEST_SOURCE:-$HOME/Desktop/Nest}"`, exported at `:64` and
>   passed at `:82`. It overrides the clean vault default at
>   `gazelle_paths.py:30` (`app_data() / "nest"`). The documented launcher puts
>   the case package on the Desktop.
> - **The gate is blind to the operator — CONFIRMED.** `gazelle_gate` is
>   imported by `gazelle_mcp.py`, its own module, and its test. **`app.py` never
>   imports it.** With `GAZELLE_GATE=1` fully configured, the TUI's save/export
>   path, every local-LLM call and every sidecar write are ungated. The control
>   governs the agent surface only.
> - **The citation regex matches home addresses — CONFIRMED, executed.**
>   `_CITATION_RE` (`tool_context.py:29`) matches `'1420 Maple 87501'` and
>   `'88 Ridgeline 90210'`, and returns **nothing** for `'347 F.3d 1120'` — a
>   real federal citation, missed because `F.3d` contains a digit. It fails in
>   both directions. `courtlistener_search` issues a live `requests.get`
>   (`:241`), and `build_context_bundle` defaults `include_courtlistener: bool
>   = True` (`:284`).
> - **Private notes reach the model prompt — CONFIRMED.** `add_note` copies
>   `body.strip()[:80]` into the activity log (`gazelle_state.py:415`), and
>   `tool_context.py:149` places `list_activity(limit=8)` into every prompt.
>   Note to activity log to prompt, and the log is one keystroke from the TUI.
>
> Findings below the top five carry the pass's own confidence tags and were not
> independently re-run.


**Scope:** `/home/user/safe-app-store` only. Read-only pass, 2026-08-04.
**Frame:** minors and adults, intra-household (shared device / shared home) and
inter-household (two homes, one child).
**Vocabulary:** rungs `L1`–`L5` and surfaces `S1`–`S4` from
[`docs/homestead-rungs.md`](../../../home/user/safe-app-store/docs/homestead-rungs.md).
**Not re-reported:** the twelve defects in `apps/law-gazelle/docs/bug_list.md`.
Where one of them has a *safety* consequence nobody has written down, it is
named as such and marked **[extends BUG-n]**.

---

## The inversion this document is about

For most software, "local-first, no cloud, no account" is the privacy answer.
Here it is the threat model's *premise*, not its mitigation.

Law Gazelle's most likely adversary is not remote. It is a person with physical
access to the same machine, who is frequently **the opposing party in the matter
the app is tracking** — the co-parent in the custody case, sharing a house and a
computer during the pre-separation months when the evidence is being gathered.
Against that adversary, "your data never leaves your machine" reads:

| Local-first property | Reads as protection | Reads as exposure |
|---|---|---|
| No server | no remote breach, no vendor | **no remote backup** — the record dies with the laptop, or with whoever gets angry |
| No account | nothing to phish, no credential store | **no authentication at all** — the record has no owner the software can distinguish |
| No cloud | no third-party processor (real, and the app's strongest single control) | **no revocation** — nothing can be un-shared, no session ended, no device de-authorized |
| No telemetry | no surveillance of the user | **no detection** — nobody can tell the record was read (`legal_obligations_intl.md` §1.8 already reaches this, from the GDPR breach-clock direction) |
| Files the user owns, open formats | portability, no lock-in (Art. 20 compliant by construction) | **files anyone at that keyboard owns** — SQLite and Markdown are as readable to the abuser as to the user |

Everything below follows from that table. The architecture's genuine wins — the
read-only canonical store, the sidecar separation, mandatory human fact
verification, local-only inference — are all wins against *the wrong adversary*.
They protect the record from the software and from vendors. Nothing in the tree
protects the record from the person standing behind the chair.

---

## Executive summary — top five exposures, in order of harm

| # | Exposure | Sense | Rung / surface | Confidence |
|---|---|---|---|---|
| **F-1** | **There is no authentication, lock, or idle timeout anywhere in the app.** One command opens the entire record — deadlines, evidence, verbatim quotes, the other parent's name, the child's schedule. `grep -riE "password\|passphrase\|encrypt"` over the app tree returns nothing in any live module. | intra | up to `L5` on `S1` | **CONFIRMED** |
| **F-2** | **The documented launcher puts the whole case package on the Desktop.** `dev.sh:17` defaults `NEST_SOURCE=$HOME/Desktop/Nest`; drafts, letters, case DBs and `legal_commit_<date>.json` all land there. The least private directory on a shared machine, visible in every file dialog and every screen share. | intra + inter | `L3`–`L5` on `S4`, spilled onto `S1` | **CONFIRMED** |
| **F-3** | **The activity log renders a keystroke-away confession timeline.** `a` → `gazelle_state.list_activity(limit=40)` → 40 timestamped rows including the first 80 characters of every note the user wrote. It is what turns F-1 from "an adversary could read a SQLite file" into "an adversary presses one key." | intra | `L4`/`L5` on `S1` | **CONFIRMED** |
| **F-4** | **The citation-verification regex exfiltrates home addresses to a third party.** `tool_context.py:29-31` matches `1420 Maple 87501` and `88 Ridgeline 90210` as "citations" and POSTs them to courtlistener.com — while *failing* to match `347 F.3d 1120`, the commonest real citation form. | inter (address of a fleeing party) | `L4` on `S4` | **CONFIRMED** (regex traced and executed) |
| **F-5** | **The app builds a structured dossier on a non-consenting third party and a minor, with no rung enforcement, no subject-facing apparatus, and no retention bound.** `homestead-rungs.md` is drafted, `finish_list.md` E-12 says *blocked on E-2* — it is a document, not a control. The manifest declares sidecar retention **"permanent local."** | inter | `L3`–`L5`, all four surfaces | **CONFIRMED** (absence traced through every write path) |

**On weighting.** These are ordered by realistic harm to a person, not by
exploit sophistication. F-1 requires no skill and no tool; it is a chair. F-4 is
the most technically interesting and ranks fourth because it requires an API key
the default configuration does not set — but it ranks *this high* because the
datum it leaks (a relocated address) is the one whose disclosure gets people
killed, and because it leaks from a function whose name promises it is checking
case law.

---

# A — Intra-household: shared devices and homes

## F-1 · No authentication, no lock, no timeout, no per-user boundary

**CONFIRMED.** Intra-household. Reaches `L5` on `S1`.

**What creates it.** Nothing does — that is the finding. There is no credential
prompt, no lock screen, no idle timeout, no re-auth on the sensitive routes, and
no concept of "who is running this." `app.py:1284` constructs `LawGazelleApp()`
and calls `.run()`. `app.py:215` `on_mount` immediately calls `action_refresh()`,
which syncs from Nest and renders the Today queue before any human interaction.
The first frame after launch already shows matter names, deadline dates,
severity, and case-item titles.

The app's only authorization concept, WillowGate, is analysed in **F-6**; it is
not an answer here, because it wraps the MCP surface and not the TUI.

**Who is harmed, how badly.** The parent documenting a custody case on the family
computer during the months before separation — the app's own wedge population
(`MISSION.md:37`). The opposing party opens a terminal, runs the same command the
user runs, and reads the case strategy, the evidence ledger, and every note.
There is no artifact of the intrusion and no way for the user to learn it
happened. In a matter involving a protective order or an abuse allegation, the
harm is not "privacy"; it is that the adversary learns *what the victim knows,
what they can prove, and when they intend to act.*

**The honest limit of any fix.** Same OS account = same uid = same file
permissions. `finish_list.md` E-3 already states this precisely and correctly:
*"the root is not for isolation — same uid, same permissions, and a directory
name is not a security boundary."* That sentence is right and should be promoted
out of a work item into user-facing documentation. A passphrase on the app is
defeated by reading `gazelle_state.db` directly. **The only real intra-household
control is at-rest encryption keyed to something the adversary does not have** —
and that is a device/OS decision (separate OS accounts, FileVault/LUKS with
distinct passphrases), not an application feature.

**What the app should do anyway, and why it is still worth doing:**

1. **An app-level passphrase that encrypts the sidecar and the synced `cases/`
   copy** (SQLCipher or an age-encrypted container mounted for the session).
   This is the only measure that survives direct file access. Cost: a forgotten
   passphrase destroys the record, in a tool whose users are under stress and
   have no recovery channel by design. That cost is real and must be presented,
   not buried — see the recovery discussion under **F-13**.
2. **An immediate blank/cover keystroke** (`Ctrl-L` → neutral screen, requires
   passphrase or Escape-sequence to restore). Cheap, useful against the actual
   common case (someone walks in), useless against a determined adversary. Ship
   it and say exactly that.
3. **An idle timeout that drops to the cover screen**, defaulting to something
   short. The TUI already runs `self.set_interval(1.0, self._update_ai_status)`
   at `app.py:217`, so the timer infrastructure exists.
4. **Refuse to launch without an explicit "this machine is not shared"
   acknowledgment on first run**, recorded in the sidecar. This is a
   documentation control wearing a UI costume, and that is fine — it is the
   moment where a safety-planning referral belongs (see §D).

## F-2 · Where the files actually land — traced

**CONFIRMED.** Intra + inter. `L3`–`L5` on `S4`, deposited in the most-observed
directory on `S1`.

The task asked me to trace four paths rather than assume. The result is a
**split between what the resolver says and what the launcher does**, and the
launcher wins.

**`gazelle_paths.py` (the resolver) is clean.** `nest_source()` at
`gazelle_paths.py:28-30` returns `app_data()/nest` → `vault_paths.app_dir` →
`~/.willow/store/law-gazelle/nest`. No Desktop anywhere. `vault_paths/__init__.py`
is a careful, single-decision module and its docstring is right that
`vault_root()` is a security boundary.

**`dev.sh` (the documented launcher) overrides it back to the Desktop.**
`dev.sh:17`:

```bash
NEST_SOURCE="${NEST_SOURCE:-$HOME/Desktop/Nest}"
```

and `dev.sh:64` exports it, `dev.sh:82` passes it as `--source`. `README.md:55`
tells the user to run exactly this script. So in the shipped, documented flow the
env override is *always set*, and the vault default at `gazelle_paths.py:30` is
dead in practice.

**Everything downstream inherits that.** `case_store.py:26`
`DEFAULT_SOURCE = gazelle_paths.nest_source()`; `document_store.py:21`
`NEST = case_store.DEFAULT_SOURCE`; `commit_package.py:20` the same. Then:

- **Drafts.** `document_store.save_document()` at `document_store.py:339-341`
  builds `NEST / "drafts"`, `mkdir(parents=True, exist_ok=True)`, and writes.
  Under `dev.sh` that is `~/Desktop/Nest/drafts/`. The docstring at
  `document_store.py:332` states it outright: *"Default: ~/Desktop/Nest/drafts/."*
  The AI "Save draft to Nest" button (`screens/intelligence.py:89`) calls it with
  `dest="nest"` and no subdir override — so a first-pass AI-drafted letter about
  the other parent lands on the Desktop under a **predictable filename**
  (`CaseDraft_schedule_response_<today>.md`, `intelligence.py:260`).
- **`_nest_drafts_dir()` is orphaned.** Defined at `document_store.py:52-55`,
  called by nothing (`grep -rn "_nest_drafts_dir" --include=*.py` → one hit, the
  definition). It is a dead function that would `mkdir` a Desktop directory as a
  side effect if anyone wired it back in. It should be deleted or made the single
  path helper that `save_document` and `list_drafts` both use — right now the
  drafts-directory decision is duplicated across `document_store.py:52`,
  `:339`, and `:366`.
- **Commit manifests.** `commit_package.write_commit_manifest()` at
  `commit_package.py:146` writes `legal_commit_<date>.json` into the Nest root —
  the Desktop. Its **contents are an index of the whole case package**:
  `find_artifacts()` (`commit_package.py:40-58`) enumerates `coparent.db`,
  `bankruptcy.db`, `workers_comp.db`, every `*_Letter*.docx`, and every file under
  `drafts/`, and `build_manifest()` (`:74`) stamps in the case number. A file
  named `legal_commit_2026-08-04.json` sitting on a shared Desktop, listing
  `drafts/CaseDraft_schedule_response_2026-08-04.md`, is a **map of the case for
  anyone who opens the folder** — including someone who has no idea what Law
  Gazelle is.
- **The seeder's own destination.** `scripts/seed_demo.py:226` defaults to
  `<app>/.demo/nest`, which is gitignored. That part is fine. Its destructive
  behaviour is **F-7**.
- **Synced copies.** `case_store.sync_cases()` copies every case DB, the export
  JSON, `session_meta.db`, every matched letter `.docx`, **and the entire Nest
  `drafts/` tree** (`case_store.py:212-218`) into `APP_DATA/cases/`. So there are
  now two full copies. `dev.sh:18` puts the second at
  `~/.willow/apps/law-gazelle/cases/` — better than the Desktop, still
  same-uid-readable, and *not* what `gazelle_paths.app_data()` says (the resolver
  says `~/.willow/store/law-gazelle`). Two writers disagreeing about where the
  vault is, is exactly the drift `vault_paths`' docstring warns about.
- **A script whose help text teaches Desktop exports.**
  `scripts/export_schedule_response.py:8` documents
  `-o ~/Desktop/schedule_response_briefing.md`. That file is the full schedule
  briefing: every atom, evidence, verbatim quotes, plan citations.

**Who is harmed.** Anyone who shares a desktop session, a screen, or a
screenshot. A file dialog in any other application on the machine lists
`Nest/`. A screen-share for work shows it. A child using the family computer for
homework sees a folder with their own custody case in it — which is its own
harm, distinct from the adversary case and arguably worse.

**What the app should do.**

- **Change the `dev.sh` default to the vault path and make the Desktop an
  explicit, warned-about opt-in.** One line. It is the highest
  harm-reduction-per-character change in this document.
- **Never write a manifest, draft, or export into a directory the OS treats as a
  desktop.** If `NEST_SOURCE` resolves under `~/Desktop`, `~/Documents`,
  `~/Downloads`, or a synced-cloud folder, refuse and explain — the same
  fail-closed posture the gate already claims. That check is ~10 lines in
  `gazelle_paths.py` and would be the app's first control that is actually about
  the household rather than about the software.
- **Make `save_document`'s default destination the app data dir**, and make
  "export to a location I choose" a deliberate, per-file act that says where the
  file is going before it goes. Egress at `L3`+ is supposed to be *"explicit
  act, ledgered"* per the rung table; today it is a button labelled "Save draft
  to Nest" whose destination the user is never shown.
- **Name the manifest neutrally.** `legal_commit_2026-08-04.json` announces
  itself. A dotfile inside the app data dir does the same job.

## F-3 · The activity log is a plaintext timeline of what the user did and when

**CONFIRMED.** Intra-household. `L4`/`L5` on `S1`; also `S2` (see below).

**What creates it.** `gazelle_state.log_activity()` (`gazelle_state.py:112-128`)
is called on every meaningful act: `mark_resolved` (`:355`), `snooze_until`
(`:391`), `add_note` (`:416`), `set_fact_verification` (`:289`),
`set_matter_stage` (`:323`), `commit_package.py:150`, and every AI call
(`intelligence.py:193, 281, 343, 439`). The TUI exposes it at `app.py:860-880`
under a single unmodified keystroke, `a` (`app.py:152`), rendering 40 rows of
`created_at`, `event_type`, and 60 characters of `summary`.

**The part that matters most.** `add_note` at `gazelle_state.py:415-422`:

```python
preview = body.strip()[:80]
log_activity("note", f"Note added: {preview}{'…' if len(body.strip()) > 80 else ''}", ...)
```

The **first 80 characters of every private note** are copied verbatim into the
activity table. Notes on a custody matter are where a person writes the things
they are not yet ready to say — "he was drunk again at pickup", "call the
shelter Tuesday", "ask about the bruise." Those first 80 characters are the
whole sentence. `set_fact_verification` at `:289` similarly logs
`"Fact ATM-017 marked do_not_use"`, which under the rung model is `L5` by
definition (*"any fact the operator marked `do_not_use`, and why"*) — and it is
sitting in a table any co-resident can render with one keypress, and,
separately, in the model prompt (below).

**And it reaches the model prompt.** `tool_context.gazelle_context_for_card()` at
`tool_context.py:149-162` unconditionally appends the last **8 activity lines**
to the LLM context bundle for every AI brief and every AI draft. Under
`homestead-rungs.md`'s composition rule (*"a model prompt is the `max` of
everything in its context window"*), that alone makes every AI call an `L5`
prompt. `bug_list.md` BUG-5 already observed this block leaking `do_not_use` into
the prompt; the safety framing is stronger than the correctness framing — the
activity block is a **narrative of the user's fears in the order they had
them**, and it is being posted into a cache (`ai_cache.body`, **F-11**) that
persists for seven days with no user-facing eraser.

**Who is harmed.** Everyone in the intra-household case, worst for the person
whose safety depends on the adversary not knowing what they have noticed.

**What the app should do.**

- **Stop storing note bodies in the activity summary.** Log `("note", "Note added", source_db, item_type, item_id)` and nothing more. The item reference is
  enough for the log's stated purpose. This is a one-line change at
  `gazelle_state.py:415-418` and removes the single richest leak in the sidecar.
- **Classify activity rows.** `note`, `fact_verification`, and any row whose
  `item_id` resolves to a `do_not_use` fact are `L4`/`L5`; `sync`, `commit`, and
  `matter_stage` are `L2`. Render `L4`+ rows on `S1` as
  `"note added · ATM-017 · 14:22"` and never on `S2`.
- **Drop the activity block from the context bundle entirely**
  (`tool_context.py:149-162`). It is not evidence, the model has no legitimate
  use for it, and it is the highest-rung content in the bundle. If some
  recency signal is genuinely wanted, pass a count.
- **Give the log a retention bound and a visible eraser.** "Permanent local"
  (`safe-app-manifest.json`, `sidecar_state`) is the wrong default for a table
  that is mostly a diary.

**Tension, named:** an audit trail is exactly what a supervising attorney at a
D2 clinic will ask to see (`legal_obligations_us.md` §3), what LSC Part 1636
audit access assumes, and what starts a GDPR 72-hour clock. It is also exactly
what the abuser reads. **Recommendation:** keep the trail, but split it — a
**redacted operator-visible log** (what type of act, on which item, when) and a
**sealed integrity log** (hash-chained, encrypted to a key the operator holds
and can hand to counsel) that the running app can append to but never render.
`finish_list.md` E-11 already contemplates a Nestor hash-chained ledger and
flags that it currently records canonical values *in cleartext* — that is the
same wall, hit from the other side. Cost of the split: two logging paths to keep
consistent, and the sealed half is useless to a user who loses the key. Say so.

## F-4 · CourtListener "citation verification" exfiltrates addresses and dates

**CONFIRMED** for the regex behaviour (traced and executed); **PLAUSIBLE** that
real Nest data contains the triggering strings — I cannot check real case data,
which is correctly absent from the repo.

**What creates it.** `tool_context.py:29-31`:

```python
_CITATION_RE = re.compile(
    r"\b\d+\s+[A-Z][a-z.]*\s+\d+\b|\b\d+\s+U\.?\s*S\.?\s+\d+\b",
)
```

`courtlistener_context_for_card()` (`tool_context.py:255-256`) builds
`workflow.build_packet_markdown(card)` — which is the *entire* drafting packet:
atom bodies, `format_detail_text` per atom (including
`evidence.verbatim_quote`, `case_store.py:1020`), the chronology, plan citations
— and hands the whole string to `courtlistener_verify_citations()`. That function
(`tool_context.py:215`) takes the **first five regex matches** and POSTs them to
`https://www.courtlistener.com/api/rest/v4/citation-lookup/` with the operator's
API token.

**Executed, on plausible custody-matter prose:**

```
'Pickup at 1420 Maple 87501 per the order.'         -> ['1420 Maple 87501']
'she moved to 88 Ridgeline 90210 last month'        -> ['88 Ridgeline 90210']
'Child A.R. born 2018; 3 Elm 4 blocks from school.' -> ['3 Elm 4']
'Text on 12 March 2026 said she would be late.'     -> ['12 March 2026']
'IEP meeting 2 Feb 2026 at Lincoln Elementary'      -> ['2 Feb 2026']
'347 F.3d 1120'                                     -> []          ← a real citation, missed
```

A street address with a ZIP code is a **perfect** match for the pattern. The
commonest federal reporter form is not a match at all (`[A-Z][a-z.]*` cannot
cross the digit in `F.3d`). The function's true-positive rate on its stated job
is poor and its false-positive rate on residential addresses is high.

**Who is harmed, and how badly.** A parent who has relocated for safety. The
address of a person hiding from the other party is the single highest-harm datum
this application can hold, and this path sends it to a third-party server, over
the network, from a code path named "verify citations." `L4` payload crossing
`S4` — a combination the rung table marks *"explicit act + purpose + ledgered."*
There is no act, no purpose, and no ledger.

**Reachability — stated precisely, because it matters.** Three gates stand
between the code and the harm, and all three are weaker than they look:

1. `_courtlistener_enabled()` (`tool_context.py:196-199`) requires
   `COURTLISTENER_API_KEY`. Off by default. **Good.**
2. `intelligence.brief_card` / `draft_from_card` default
   `include_courtlistener=False` (`intelligence.py:144, 206`), and the TUI never
   passes `True` (`app.py:592, 599`). **Good.**
3. But `tool_context.build_context_bundle()` defaults it to **`True`**
   (`tool_context.py:284`) — so any *new* caller gets egress by default; and the
   MCP tools `gazelle_ai_brief` / `gazelle_ai_draft` take
   `include_courtlistener` straight from the caller
   (`gazelle_mcp.py:492`, `:511-517`). An agent asks for it, and it happens.

`finish_list.md` B-5 already flags CourtListener as "build it or mark it
unimplemented." That is the right instinct for a different reason than the one
recorded: the half-built version is not merely misleading, it is an egress.

**What the app should do.**

- **Do not send free-text case material to a citation API.** Extract citations
  from the `legal_ref` / `plan_citations` / `state_law` **fields**, which are
  structured and operator-entered, never from rendered packet prose.
- **Require a real citation grammar** (reporter abbreviations from a fixed list),
  and reject anything that does not match one. A pattern that cannot distinguish
  `410 U.S. 113` from `88 Ridgeline 90210` is not a citation detector.
- **Show the operator exactly what would be sent, and require confirmation**, per
  matter, every time. The rung table's "explicit act + ledgered" is satisfiable
  with a modal.
- **Flip `build_context_bundle`'s default to `False`.** Egress should never be
  the default value of a keyword argument.
- **Until the above lands, make `include_courtlistener` a no-op** and say so in
  the tool description — B-5's "mark unimplemented" option, chosen for safety
  rather than honesty.

## F-6 · The authorization layer is real code and a nominal control

**CONFIRMED.** Both senses. Governs `S3`, claims to govern `S4`.

The task asked me to say plainly where a control is real and where it is
nominal. WillowGate is the sharpest case in the tree, and the answer is *both*,
in a way the existing docs do not quite state.

**What is real.** `gazelle_gate.py` is careful work. `TOOL_CLASS`
(`gazelle_gate.py:51-68`) classifies every MCP tool and comments *"Unknown tools
are DENIED — fail closed."* `authorize()` (`:154-167`) returns a deny on missing
session, unknown tool, or any exception. `GateKeeper.__init__` (`:114-122`)
constructs the gate at import so a misconfiguration stops the server. `gazelle_save`
and `gazelle_commit` are correctly marked `export=True`. This is not
security theatre; someone thought about it.

**Where it is nominal — three layers, compounding:**

1. **Off by default.** `GAZELLE_GATE` unset → `authorize()` returns
   `(True, "gate disabled")` at `gazelle_gate.py:157`.
2. **Untested.** All nine enforcement tests are
   `@unittest.skipUnless(_HAVE_GATE, ...)` (`tests/test_gazelle_gate.py:17-21`)
   and skip, because `willow_gate` is not installed. `finish_list.md` records
   *72 passed, 9 skipped*. The entire `checkin`/`checkout`/`authorize` path has
   never been executed in CI. `bug_list.md` BUG-12 says this and is right to
   rate its own confidence as PLAUSIBLE for exactly that reason.
3. **The one nobody has written down: the gate does not cover the TUI at all,
   and the TUI is where the egress is.** `_KEEPER.authorize()` is called from
   exactly one place — `gazelle_mcp._handle()` at the `tools/call` branch
   (`gazelle_mcp.py:~570`). `app.py` never imports `gazelle_gate`. So with
   `GAZELLE_GATE=1` fully configured and a PGP-encrypted ledger:
   - `app.py:597-603` runs a local LLM draft (`query` class) — **ungated**;
   - `screens/intelligence.py:89` writes that draft into Nest — the
     `gazelle_save` **export**, the thing the gate exists to ledger — **ungated**;
   - `app.py:704`, `:721`, `:736`, `:748` write resolutions, notes, snoozes and
     fact verdicts to the sidecar — **ungated**;
   - `scripts/commit_package.py` writes the manifest from the CLI — **ungated**.

   The gate ledgers what an *agent* did and is blind to what the *operator's own
   screen* did. For the D2 story in `legal_obligations_us.md` §3 — a supervising
   attorney wanting to see how draft sign-off is enforced — the honest answer
   today is that the enforcement surface does not include the surface the human
   uses.

**What the app should do.** Turn the gate on by default before any D2
deployment (`legal_obligations_us.md` implications table row 3 already says
this); get `willow_gate` into CI so the nine tests run; and **move the
authorization call from the MCP dispatcher down to the write/egress functions
themselves** — `document_store.save_document`, `commit_package.write_commit_manifest`,
`gazelle_state.add_note` — so both the TUI and the MCP server pass through the
same door. That inversion is the same shape as the promotion bar's "injected
seams" rule and would make the control true for the first time.

## F-7 · The demo path can destroy the real record

**CONFIRMED.** Intra-household. Evidentiary harm rather than confidentiality
harm — which is why it belongs in this document rather than in the bug list.

`scripts/seed_demo.py:30`, first statement of `seed()`:

```python
shutil.rmtree(dest, ignore_errors=True)
```

`dest` is `Path(sys.argv[1]).expanduser()` (`:227`) with **no argument parsing
and no confirmation**, and `ignore_errors=True` suppresses every complaint.
`demo.sh:19` adds `rm -rf "$DEMO_ROOT"` behind `--fresh`, where `DEMO_ROOT` is
`${LAW_GAZELLE_DEMO_ROOT:-...}` — an environment variable.

`finish_list.md` A-6 has the seeding half of this ("seeds four case files into a
directory named `--help`"). **The half nobody has recorded is that it deletes
first.** `python3 scripts/seed_demo.py ~/Desktop/Nest` — a plausible mistake for
someone who has just read `dev.sh`'s `NEST_SOURCE=~/Desktop/Nest` — silently
removes the entire canonical case store: DBs, letters, drafts, manifests. There
is no remote backup, by design (§the inversion table).

In litigation this is not "data loss." It is **potential spoliation of
evidence**, with the destruction performed by the litigant's own tooling on a
path the app's own documentation trains them to type.

**What the app should do.** Add `argparse` (A-6's fix) and additionally: refuse
any `dest` that is not empty unless `--force` is passed; refuse any `dest` that
equals `NEST_SOURCE` or lies under a non-`.demo` path; and never `rmtree` with
`ignore_errors=True` on an operator-supplied path. This is a fifteen-line fix
protecting the only copy of a case file.

## F-8 · Hiding is easy, permanent, and invisible — and it is also a weapon

**CONFIRMED.** Intra-household. **[extends BUG-4]**

BUG-4 documents the mechanism completely: free-text snooze, string comparison in
`is_snoozed` (`gazelle_state.py:484`), `"next week"` hides an urgent deadline
until 2099, and no un-snooze exists anywhere. The bug list frames this as a
missed-deadline generator, which it is. Three safety consequences are not
recorded there:

1. **It is an adversary primitive.** Anyone who can open the app (F-1) can
   press `z` on the response deadline and type anything. The item vanishes from
   Today. There is no un-snooze, no "snoozed items" view (the `t` toggle is
   restricted to the home route, `app.py:449-452`), and the only trace is one
   activity row the adversary can see they left — and can bury under 40 more.
   **The most consequential state change in the application is a two-keystroke,
   irreversible, low-visibility action available to anyone at the keyboard.**
2. **It is a self-harm primitive under duress.** A frightened person who wants
   the case off their screen right now has exactly one tool for it, and that
   tool is the one that silently costs them the deadline.
3. **The hidden item is still in every export.** `schedule_response_packet()`
   filters snoozed atoms (`case_store.py:1345-1348`) but `document_store.draft_context()`
   does not consult snooze at all (`document_store.py:82-107`) — so a snoozed
   item is invisible on `S1` and fully present on `S2` and `S4`. Hiding
   something from the operator while keeping it in the model prompt is the wrong
   direction on every surface.

**What the app should do.** Beyond BUG-4's fix (validate, compare dates, add
`clear_snooze`): make snoozed items **visible by default in a distinct muted
row** rather than removed; require a reason for snoozing anything with a
computed deadline inside 14 days; and make snooze the *only* hiding primitive,
so that "make this disappear" has one well-understood door rather than three
half-doors (snooze, resolve, `do_not_use`) that behave differently on each
surface.

## F-9 · Terminal scrollback, launcher banners, and the CLI fallback

**CONFIRMED.** Intra-household. `L3`/`L4` persisted onto `S1` past app exit.

Textual runs in the alternate screen buffer, so quitting the TUI *does* clear
the case data from the terminal — a genuine, unremarked-upon protection. Three
paths bypass it:

- **`_cli_fallback()`** (`app.py:1188-1243`) runs automatically whenever
  `textual` fails to import (`app.py:62-64`) and prints the **entire urgent
  queue** — severity, days, deadline dates, item titles — plus every case
  number, cross-case intersections, workers'-comp atoms, and session metadata,
  to plain stdout. That is a full case briefing living in scrollback until the
  buffer rolls, recoverable by scrolling up, and captured by anything that logs
  the terminal. It triggers *silently*, on a machine where a dependency is
  missing — i.e. on the machine least likely to be the user's own.
- **`dev.sh:70-80`** echoes `nest:`, `cases:`, `app:`, and `branch:` to stderr on
  every launch. Those lines survive the alternate-screen restore and tell any
  later reader exactly where the case files are.
- **`--sync-only`** (`app.py:1276`) prints the full sync manifest JSON, including
  the source and destination paths and every copied filename.

**What the app should do.** Make `_cli_fallback` print counts and a "install
textual to view" line, never item content — a fallback renderer for sensitive
data should be *less* revealing than the primary, not more. Send `dev.sh`'s path
banner to a log file or behind `--verbose`. Suppress paths in the `--sync-only`
output unless asked.

## F-10 · `xdg-open` hands the document to the rest of the desktop

**PLAUSIBLE** — the call is confirmed; the downstream artifacts are
environment-dependent and I could not exercise a desktop session here.

`app.py:634`, `:770`, `:779`, `:788` all `subprocess.Popen(["xdg-open", path])`.
On a typical Linux desktop that means: the file is registered in the
freedesktop recent-documents list (`~/.local/share/recently-used.xbel`), the
handler application adds its own MRU entry, the window title of that handler
shows the filename, and editors commonly leave swap/autosave/backup files
(`.md~`, `.#file`, `~/.local/share/<editor>/`) next to or outside the Nest
directory. None of that is under Law Gazelle's control and none of it is
cleaned up.

**What could not be checked:** which handler is registered, whether the desktop
environment writes an MRU at all, and whether any handler leaves recovery files.

**What the app should do.** Prefer an internal read-only viewer for `.md`/`.txt`
drafts — the app already has `PacketScreen` and `IntelligenceScreen`, so the
widget exists. Reserve `xdg-open` for formats it genuinely cannot render
(`.docx`), and when it is used, warn once that the file is now visible to the
rest of the desktop and name the recent-documents list specifically.

## F-11 · The AI cache is a durable shadow copy of the highest-rung material

**CONFIRMED.** Intra + inter. `L4`/`L5` written to `S2` and stored.

`ai_cache` (`gazelle_state.py:71-82`) stores the **full LLM output body** with a
7-day TTL. What goes into the prompt that produced it:

- `tool_context._excerpt(detail, max_len=6000)` (`intelligence.py:415`) puts up
  to 6 KB of the raw atom detail dict into the fact-inspection prompt —
  evidence rows, `verbatim_quote`, `content_hash`, linked issues;
- `format_detail_text(detail)` for the card's own item (`tool_context.py:87-97`);
- **all sidecar notes** for that item, verbatim, up to ten
  (`tool_context.py:98-108`);
- the last 8 activity lines (F-3);
- the full drafting packet and chronology.

Composition is `max`, so every one of these prompts is at least `L4`, and any
including a `do_not_use` fact or a note about an allegation is `L5`. The rung
table's two hard stops are *"`L4` never reaches a model prompt as a payload"*
and *"`L5` has no override anywhere."* Both are crossed on every AI action,
today, by construction.

The model is local (`llm_client.py:15`, Ollama on `localhost:11434`) — which is
the app's strongest genuine control and the reason `legal_obligations_us.md` §3
can say the dominant Rule 1.6 / ABA Op. 512 risk *"does not occur by
architecture."* That remains true. But **"local" is a network claim, not a
confidentiality claim on a shared machine.** Two residues:

- `OLLAMA_BASE_URL` (`llm_client.py:24`) is an environment variable. Anyone who
  can set the user's environment can point inference at a remote host and every
  subsequent prompt — `L5` payload included — leaves the machine, with no
  indicator anywhere in the UI. There is no check that the resolved base URL is
  loopback.
- The cache body is a **plaintext narrative summary of the case**, indexed by
  card, sitting in the same unprotected SQLite file as everything else. An
  adversary who cannot be bothered to read the evidence ledger can read the AI's
  summary of it. `clear_ai_cache()` exists (`gazelle_state.py:217`) but has no
  TUI binding and no MCP tool — the user cannot clear it.

**What the app should do.** Pin `OLLAMA_BASE_URL` to loopback and refuse
anything else without an explicit, displayed override. Give the cache a visible
"clear AI results" action. Stop putting notes and activity in prompts. And take
`homestead-rungs.md`'s claim seriously in code: at `L4` the prompt gets the
**instruction**, not the payload — *"medical records response due Aug 15"*, not
the diagnosis. That is the difference between a classification and a label on a
leak, in the rung doc's own words.

## F-12 · The public repository discloses the operator and the shape of their matters

**CONFIRMED.** Intra + inter. `L2`/`L3` on `S4`, in git history.

- `apps/law-gazelle/.mcp.json` is **tracked** and contains eight absolute paths
  under `/home/sean-campbell/` — a real name, in a public repository, in git
  history. (Repo-wide: 20 tracked `.mcp.json` files, same pattern.)
- `MISSION.md:82` states the tool is *"running on real (private, off-repo) case
  data for user #1."*
- `README.md:31-35` and `case_store.py:28-32` enumerate the three compiled-in
  matter types: co-parent/family law, bankruptcy, workers' comp.

Composed: the public repo says *this named person is, right now, running a real
custody matter, a real bankruptcy, and a real workers' comp claim.* No case
content leaks — I checked the one committed screenshot,
`docs/img/demo_today.svg`, and it is genuinely synthetic (demo IDs, `.demo/app/cases`
paths, fictional atoms). The exposure is the **existence and character** of the
matters plus an identity, which is precisely what `L2`'s re-identification check
exists to catch: *"an aggregate is `L2` only after a check that it cannot be
resolved."*

For the inter-household sense: an opposing party who finds this repository
learns that the other parent is in bankruptcy and has an open injury claim, and
learns the tooling and therefore roughly the evidence-handling method. That is
usable in a custody matter.

`finish_list.md` C-3 ("PII scrub before any public push") is open and would
catch this if run. It should be run before the `homestead-affairs` extraction
(E-5), not after — history does not scrub retroactively without a rewrite.

## F-13 · Duress: the case for and against a panic wipe

**Reasoning, not a code finding.** Intra-household.

**What exists today.** Nothing. There is no lock, no hide, no wipe, no
decoy. The nearest thing is `snooze` (F-8), which is the wrong tool wearing the
right shape.

**The case for a panic control.** The user population includes people for whom
"the other person is walking in right now" is a weekly event. A tool that cannot
be made to disappear in one keystroke will be closed, minimized, or not used —
and a case file not kept is a case lost. This is a real usability-as-safety
argument and it should not be waved away.

**The case against a panic *wipe*, specifically.** Three arguments, and the
first is the serious one:

1. **Spoliation.** In active litigation, destroying case material — even your
   own — can draw an adverse-inference instruction, sanctions, or a
   contempt finding, and the fact that a *tool* did it does not help; the party
   is responsible for their own evidence. Worse, a panic-wipe feature is
   *discoverable*: opposing counsel who learns the software has one will ask
   whether it was used, and "I don't know" is a bad answer under oath. A feature
   whose existence creates a question the user cannot safely answer is a
   liability even when never used. The commit manifest (F-2) makes this
   concrete: `legal_commit_2026-08-04.json` on disk enumerates files; if those
   files are gone, the manifest is a receipt for their destruction.
2. **It does not work.** A wipe of `~/.willow/apps/law-gazelle/` leaves the
   canonical Nest (the thing that matters), the desktop drafts, the recent-documents
   entry, the editor backups, and the filesystem journal. Software deletion on
   a shared machine is a gesture.
3. **It fails toward the adversary.** A wipe available to whoever is at the
   keyboard is available to the abuser. Given F-1, a panic key is an
   adversary's *destroy the other parent's evidence* key.

**Recommendation, with its cost stated.**

- **Build the cover screen, not the wipe.** `Ctrl-L` → immediate neutral screen;
  restoring requires the passphrase from F-1. Instant, reversible, destroys
  nothing, and is not discoverable as a destruction feature. **Cost:** it does
  nothing about the files, and a user in real danger may believe it does more
  than it does — which is a documentation obligation, not an excuse.
- **Build a deliberate "move this case off this machine" flow** — encrypted
  archive to removable media or a trusted third party, with an integrity
  manifest, *then* remove the local copy, recording the removal as a preservation
  act rather than a destruction. That is the operation a person leaving a
  household actually needs, and it is the opposite of a panic wipe: slow,
  logged, and defensible. **Cost:** it takes minutes, needs a destination the
  user has decided on in advance, and is therefore useless in the moment the
  panic key is for. Both features are needed and they are not substitutes.
- **Do not ship a wipe.** If one is ever shipped, it must (a) require the
  passphrase, (b) refuse while any matter has an open deadline, (c) write a
  signed, timestamped record of *what* was removed to a location outside the
  wipe scope, and (d) be documented to counsel-facing standards. Those four
  conditions are most of the reason not to.

---

# B — Inter-household: two homes, one child

## F-5 · A structured dossier on a third party, with no third-party apparatus

**CONFIRMED** (traced through every write and render path). Inter-household.
`L3`–`L5` across all four surfaces.

**What the record contains about the other parent.** The other parent is
`parties.parent_b` (`document_store.py:151, 165-166`), a named addressee on every
generated letter, the subject of `evidence_ledger.verbatim_quote`
(`case_store.py:1020` — *their own words, quoted, timestamped, hashed*),
the counterparty in `context_events` (`event_type`, `description`,
`impact_notes`), a `creditors.relationship` row in the bankruptcy matter
(`case_store.py:1070`), and the implicit subject of most `atoms.body` text. The
`chronology_builder` (`document_store.py:382`) renders their conduct as a dated,
significance-scored timeline. That is a dossier by any ordinary meaning of the
word, and it is a legitimate one — this is what preparing a custody case *is*.

**What the app provides for them as a data subject: nothing.**
`legal_obligations_intl.md` §1.7 already works out that erasure and rectification
"cannot terminate inside Law Gazelle" because the canonical store is read-only to
the app. That is correct and is the polite version. The sharper version:

- There is **no way to enumerate what the record holds about a given person.**
  No party index, no `subject` column, no join from a name to the rows mentioning
  it. A subject-access request cannot be answered even in principle without a
  human reading every row. `_related_intersections()` (`case_store.py:1164-1180`)
  does substring matching over free text with four hardcoded tokens
  (`housing`, `garnish`, `support`, `coparent`) — that is the app's *only*
  cross-record association mechanism, and it is a keyword join, not an index.
- There is **no retention bound.** `safe-app-manifest.json` declares
  `sidecar_state` retention `"permanent local"`. `legal_obligations_us.md` §10
  flags this correctly against the 5–8 year professional norm. For the *other
  parent*, "permanent" means a private party holds a structured behavioural
  record of them for life, past the close of the matter, with no mechanism to end
  it — including after the matter settles amicably and the parties co-parent for
  fifteen more years.
- There is **no purpose scoping.** `document_store.draft_context()` with
  `doc_type="general"` pulls the 50 most recent open atoms
  (`document_store.py:104-107`) into the drafting context regardless of what the
  letter is about. GDPR Art. 9(2)(f)'s necessity boundary — which
  `legal_obligations_intl.md` §1.1 correctly identifies as the load-bearing and
  contested question — is not represented in the data model at all.

**Who is harmed.** The other parent, who has no notice and no channel; and,
downstream, the user, who is holding a special-category dossier without any of
the minimization discipline that makes Art. 9(2)(f) hold up. In a D2 clinic
deployment those become live obligations rather than analysis.

**What the app should do, store, display, refuse, erase.**

- **Store a party table.** `party_id`, display name, role
  (`self` / `other_parent` / `child` / `witness` / `professional`), and a
  `mentions` join from every atom, evidence row, and note. Nothing else about
  data subjects is buildable without it: no DSAR export, no erasure, no
  retention sweep, no rung classification that is more than a guess. This is the
  single highest-leverage schema change in the document and it is a prerequisite
  for the rung model actually landing (E-12).
- **Display, on the case screen, a plain sentence: "This record holds N items
  about [other parent] and M about [child]."** Making the dossier legible to the
  person keeping it is most of the discipline. It is also the honest version of
  the surveillance concern below.
- **Refuse to carry a matter past its retention horizon silently.** On matter
  close, require a decision: archive-encrypted, or purge-with-record. Default to
  archive; never to "permanent."
- **Erase:** the sidecar (notes, activity, AI cache, verifications) for a named
  party, on request, with the erasure recorded. The canonical store stays
  upstream, as §1.7 says — but the app should be able to *report* what is
  upstream so the user can act there.

## F-14 · The minor who is the subject of the record

**CONFIRMED** as an absence. Inter-household. `L4` throughout.

**What exists.** The child appears as parenting-time schedules, school logistics,
pediatrician visits, and `atoms.body` narrative (`scripts/seed_demo.py:66-86`
shows the shape). `homestead-rungs.md` classifies the child's name, DOB, and
school as `L4`, guardian-ad-litem and counselling records as `L4`, and
substance-use and protective-order material as `L5`.

**What does not exist.** There is no `child` entity, no date of birth, no age, no
concept of the child as a *subject* distinct from a *topic*. The record is
structured entirely around the matter and the parties to it.

**On the rights question, honestly.** The child's legal rights here are thin and
jurisdiction-specific: in most US family-law contexts a minor is not a party,
has no independent right of access to a parent's case file, and any voice they
have runs through a guardian ad litem or the court. COPPA does not apply
(`legal_obligations_us.md` §5 gets this right — it targets child-directed
collection, and here an adult is entering data *about* a child). FERPA does not
apply to a parent's own copy of a school record. GDPR Art. 8 governs consent for
information-society services offered *to* a child and is likewise not triggered
by an adult's local case file; the UK Age Appropriate Design Code is scoped to
services likely to be accessed by children and, on a fair reading, this is not
one. **So the legal answer is mostly "no rights that bind this software," and
that is exactly why the design question is interesting rather than settled.**

**"Majority does not declassify" — is the rung doc right?** It says:

> *Time does not declassify. A closed matter's medical records stay `L4`. A
> child turning eighteen changes who may hold the file, not what the data is.*

**Yes, and the reasoning is better than the sentence suggests.** The datum's
sensitivity was never a function of the subject's age — a therapy note about an
eight-year-old is `L4` because it is a health record about an identified person,
and it remains one about a twenty-eight-year-old. Age-based declassification
would be a category error: it would let time do the work that only an explicit,
dated act is supposed to do, and the doc's own rule (*"No rung falls by inertia,
on a schedule, or as a side effect"*) already forbids exactly that.

**But the second clause is doing more work than the doc acknowledges, and
nothing implements it.** *"Changes who may hold the file"* is a real event with
real consequences, and none of them are represented:

- At majority the subject arguably becomes the person with the strongest
  interest in the record and the only one who was never consulted about its
  creation. If a rung model has an answer for anyone's access, it should have
  one for theirs.
- The parent's Art. 9(2)(f)-style justification — necessary for the
  establishment or defence of a legal claim — **expires with the claim.** A
  custody matter ends when the child ages out. Retaining a structured
  behavioural record of a now-adult afterward has no lawful-basis story left,
  under any of the regimes surveyed in either obligations document. This is the
  cleanest argument in this entire analysis for a retention bound, and it lands
  on the rung model's blind side: the rung governs *rendering*, and says nothing
  about *keeping*.
- A record kept about a person from age six to eighteen and then indefinitely,
  by one parent, readable by that parent's household, is a thing worth having a
  position on even where no statute compels one.

**What the app should do.**

- **Add a `child` party record with a date of birth**, and derive a
  `majority_date`. Do not use it to declassify anything.
- **Fire a majority event**: at that date, the matter is closed for retention
  purposes; the app prompts for archive-or-purge; and any subsequent AI or
  export use of `L4` child data requires a fresh, declared purpose.
- **Build the record so it could be handed over.** Whatever the law requires, a
  parent may one day want to give their adult child the record kept about them,
  and a structured, exportable, party-indexed record is the difference between
  that being possible and being a shoebox. This is a design position, not a legal
  requirement, and should be stated as such.
- **Refuse to render `L4` child data on `S2`** — the rung table's hard stop,
  which today is crossed on every AI call (F-11).

## F-15 · Allegations, protective orders, and safety plans — the `L5` material

**CONFIRMED** as an absence. Inter-household. `L5` on every surface.

`homestead-rungs.md` puts *"allegations under a protective order"* and
*"substance-use treatment records (42 CFR Part 2)"* at `L5`: *never served on any
surface*. `legal_obligations_us.md` §5 flags Part 2 specifically and notes
*"the app's current architecture has no Part 2 awareness at all."*
`legal_obligations_intl.md` §1.11 reaches the same place from GDPR Art. 10.

**Traced, the situation is worse than "no flag."** There is no sealing concept
anywhere in the schema. An allegation lands in `atoms.body` or
`evidence_ledger.description` as ordinary text, and from there it flows into
every path indiscriminately:

- `format_detail_text` renders `verbatim_quote` in full on `S1`
  (`case_store.py:1019-1020`);
- `chronology_builder` gives it a row, a date, and a 🔴
  (`document_store.py:407-417`);
- `draft_context` sweeps it into the drafting packet by domain
  (`document_store.py:82-107`);
- `tool_context` puts the whole detail in the model prompt
  (`tool_context.py:87-97`), and the result is cached for seven days
  (`gazelle_state.py:71-82`);
- `save_document` can write it into a Desktop file (F-2);
- `_related_intersections` can surface it from an **unrelated** query, because
  it substring-matches `"support"` and `"housing"` across matters
  (`case_store.py:1176-1179`) — so a bankruptcy-side lookup can pull a
  coparent-side allegation into view, and composition-by-`max` means that view is
  now `L5`.

The `do_not_use` verdict is the nearest thing to a seal the app has, and BUG-5
establishes it does not block anything. `homestead-rungs.md` is right that the
rung model makes BUG-5 unrepresentable — that is a good argument for building the
rung model, not a description of the present.

**Who is harmed.** Everyone, worst case. A Part 2 substance-use record disclosed
in a custody filing without the patient's specific consent or a qualifying court
order is a federal violation *and* the exact disclosure the treated party feared.
A safety plan visible on `S1` in a shared household tells the adversary the plan.

**What the app should do.**
- **A `sensitivity` column on evidence, atoms, and documents**, defaulting to
  unclassified, with unclassified **failing closed to `L5`** — the rung doc's own
  rule, applied to the migration path so existing data does not silently become
  `L1`.
- **A `sealed` flag with no rendering path.** Sealed items appear as
  `"1 sealed item — open with purpose"` and nothing else; never in a packet,
  never in a prompt, never in an export, never in the chronology table body.
- **Kill `_related_intersections`' keyword join** or restrict it to explicitly
  linked rows. An unclassified free-text join across matters is a rung-escalation
  engine.
- **A specific 42 CFR Part 2 flag** with an export refusal, per
  `legal_obligations_us.md` implications table row 5.

## F-16 · A device that travels with the child

**PLAUSIBLE** — reasoning; nothing in the tree addresses it and there is no code
to trace.

A tablet or laptop that moves between households is a normal artifact of shared
custody. Law Gazelle assumes one operator, one machine, one uid. If the app or
its data ever sits on a device that crosses between homes:

- the sidecar and the synced `cases/` copy travel with it (F-1: nothing gates
  them);
- so does the Desktop `Nest/` directory (F-2);
- and a `legal_commit_*.json` on that Desktop announces itself to the other
  household.

There is nothing to fix in code here beyond F-1 and F-2, because the failure is
that the *device* crossed, not that the software misbehaved. **The mitigation is
documentation: never install this on a device that leaves the household, and
never on a device a child uses.** Blunt, and correct.

The adjacent case *is* code-shaped and worth naming: the app has **no
client/matter isolation** in the sidecar — the key is
`(source_db, item_type, item_id)` (`gazelle_state.py:24-31`), with no
`client_id`. `legal_obligations_us.md` §3 flags this for D2. It is also the
reason two adults in one household cannot each keep their own matter safely on
one machine, which is a real intra-household configuration (each parent's own
workers' comp claim, say) and one the app would silently merge.

## F-17 · What must not be easy: surveillance of the other household

**Reasoning.** Inter-household. This is the design question in the brief, and it
deserves a straight answer.

**The uncomfortable truth: content cannot distinguish them.** A dated, sourced,
verbatim-quoted chronology of the other parent's conduct is *simultaneously* the
correct output of evidence work and the exact artifact a controlling
ex-partner would build. `chronology_builder` cannot tell which one it is
producing, and neither can any classifier over the text. The difference is not
in the data. It is in **provenance, scope, and purpose** — three things the
schema does not record.

So the design question is not "how do we detect misuse" (we cannot) but **"what
does the tool make effortless, and what does it make deliberate."** Today:

**What is effortless, and shouldn't be.**
- Adding an unbounded number of observations about the other parent — an atom or
  evidence row has no required source, no required purpose, no link to an issue,
  and `_parse_evidence_ids` (BUG-10) will quietly drop the source link anyway.
- Generating a full behavioural chronology with one keystroke, with no scoping to
  the matter at issue.
- Accumulating forever (`retention: permanent local`).

**What is deliberate, and rightly so — the controls that already exist and
work.**
- The canonical store is **read-only to the app** (`case_store.sync_cases` copies
  *in*, nothing writes *out*). The app cannot fabricate a record. This is real
  and load-bearing.
- **Human fact verification** — `[VERIFY]` / `[FACT NEEDED]` markers survive into
  every template (`document_store.py:161-201`) and the `SYSTEM_PROMPT`
  (`intelligence.py:27-28`) instructs the model not to fill them. `_fact_blocked`
  is broken (BUG-5) but the *shape* is right.
- **The app never authors facts.** `MISSION.md:22-23`, and it is true in code —
  `draft_context` assembles, it does not assert.
- **Local inference.** No third party learns anything about either household.

**What the app should do to make the difference legible.**

1. **Require a source for every observation about a third party.** An evidence
   row with no `content_hash`, no `event_date`, and no document behind it should
   render as *unsupported* everywhere it appears, not merely as
   `"No linked evidence"` in one screen. A tool that demands provenance for every
   claim about another person is *structurally* a documentation tool; a tool that
   accepts free-text observations is structurally a surveillance log. This single
   requirement is most of the distinction.
2. **Scope by issue, not by "everything open."** `draft_context`'s
   fifty-most-recent-atoms fallback (`document_store.py:104-107`) is the
   surveillance-shaped default. Require an issue or a deadline.
3. **Show the user the shape of what they are building** (F-5): "62 items about
   [other parent], 41 without a linked source." Reflection is a control.
4. **Say it in `MISSION.md`.** The "what it will never do" list
   (`MISSION.md:58-63`) is the right place, and it is currently silent on the
   surveillance boundary. It should say: *this tool documents a matter; it does
   not monitor a person, and it will not accept observations that are not tied to
   a source and an issue.* That is a commitment the code can then be held to —
   and, per `legal_obligations_us.md` §1's DoNotPay lesson, a self-imposed claim
   the FTC theory would hold the operator to, which is a feature.
5. **Archive `personas.py` with the note C-6 already specifies.** Independent of
   the UPL exposure both other documents identify, its voice — *"you know every
   form, every deadline, every statute… next steps: what to file, where, by when"*
   — is the register of a tool that acts *on* a matter rather than organizing it,
   and reads, to a reviewer, like the wrong kind of product. It is 36 lines
   imported by nothing and it is the most quotable file in the repository.

---

# C — Concrete engineering implications

Ordered by harm reduction per unit of work. "Rung/surface" is the highest the
item touches.

| # | Change | File / line | Rung · surface | Sense | Effort |
|---|---|---|---|---|---|
| 1 | Default `NEST_SOURCE` to the vault, not the Desktop | `dev.sh:17` | `L4` · S4 | intra+inter | 1 line |
| 2 | Stop copying note bodies into the activity summary | `gazelle_state.py:415-418` | `L5` · S1 | intra | 1 line |
| 3 | Flip `build_context_bundle(include_courtlistener=)` to `False` | `tool_context.py:284` | `L4` · S4 | inter | 1 line |
| 4 | Drop the activity block from the LLM context bundle | `tool_context.py:149-162` | `L5` · S2 | both | ~10 lines |
| 5 | Refuse a Nest/export path under `~/Desktop`, `~/Documents`, `~/Downloads`, or a cloud-sync dir | `gazelle_paths.py` | `L4` · S4 | intra | ~15 lines |
| 6 | `argparse` + non-empty-destination refusal in the seeder; no `rmtree(ignore_errors=True)` on operator paths | `scripts/seed_demo.py:30,227`; `demo.sh:19` | evidence integrity | intra | ~15 lines |
| 7 | Replace the citation regex with a reporter grammar; extract from `legal_ref`/`plan_citations` fields, never packet prose | `tool_context.py:29-31, 215, 255` | `L4` · S4 | inter | ~40 lines |
| 8 | Pin `OLLAMA_BASE_URL` to loopback; refuse non-loopback without a displayed override | `llm_client.py:24` | `L5` · S2/S4 | both | ~15 lines |
| 9 | Cover screen (`Ctrl-L`) + idle timeout using the existing `set_interval` | `app.py:148-169, 217` | `L5` · S1 | intra | ~60 lines |
| 10 | `_cli_fallback` prints counts, not item content; `dev.sh` path banner behind `--verbose` | `app.py:1188-1243`; `dev.sh:70-80` | `L3` · S1 | intra | ~30 lines |
| 11 | Internal viewer for `.md`/`.txt` instead of `xdg-open`; warn when `xdg-open` is unavoidable | `app.py:634,770,779,788` | `L4` · S1 | intra | ~40 lines |
| 12 | Visible "clear AI results" action wired to `clear_ai_cache` | `gazelle_state.py:217`; `app.py` binding | `L5` · S1 | both | ~20 lines |
| 13 | Snooze: validate dates, `clear_snooze`, render snoozed rows muted rather than hidden, reason required inside 14 days | `gazelle_state.py:373-397,479-484`; `screens/detail.py:167` | availability | intra | ~80 lines · [extends BUG-4] |
| 14 | Move `authorize()` from the MCP dispatcher into `save_document` / `write_commit_manifest` / sidecar writers, so the TUI passes the same door | `gazelle_gate.py:154`; `gazelle_mcp.py`; `document_store.py:325`; `commit_package.py:114` | all · S3/S4 | both | ~120 lines |
| 15 | `sensitivity` column on atoms/evidence/documents; unclassified fails closed to `L5`; `sealed` items get a count-only render | schema + `case_store.format_detail_text` | `L5` · all | inter | large |
| 16 | Party table (`party_id`, role, `mentions` join) — prerequisite for DSAR export, erasure, retention, and real rung classification | schema | `L4` · all | inter | large |
| 17 | Retention: replace `"permanent local"` with a per-matter horizon; majority-date event on the child record; archive-or-purge prompt on matter close | `safe-app-manifest.json`; schema | `L4` · S4 | inter | large |
| 18 | Require a source and an issue for every third-party observation; render unsourced claims as unsupported everywhere | `case_store.py:57-70`, `document_store.py:104-107` | design boundary | inter | medium · [extends BUG-10] |
| 19 | Encrypt sidecar + synced `cases/` at rest under an app passphrase | `gazelle_state.py:95-102`; `case_store.py` | `L5` · S1 | intra | large |
| 20 | Delete the orphaned `_nest_drafts_dir()`; single path helper for the drafts directory | `document_store.py:52,339,366` | hygiene | intra | 5 lines |
| 21 | Run C-3 (PII scrub) before the E-5 extraction; untrack `.mcp.json` absolute home paths | `apps/law-gazelle/.mcp.json` | `L3` · S4 | both | small |
| 22 | Archive `personas.py` with the C-6 note | `personas.py` | design boundary | both | small |

---

# D — What belongs in documentation, not in code

Several of the largest exposures are social and cannot be closed by software.
Naming them as engineering problems would be a way of not addressing them.

**1. A shared computer cannot be made safe by an application.**
`finish_list.md` E-3 already says it correctly for a different reason: *same uid,
same permissions, and a directory name is not a security boundary.* The
user-facing version, which should appear before first run and in `README.md`:

> If someone else can use this computer under the same login, they can read
> everything in this app, including your private notes — regardless of any
> password this app asks for. If the other party in your matter has access to
> this machine, do not keep your case file on it. A separate operating-system
> account with its own password and full-disk encryption is the minimum; a
> separate device is better.

**2. This is where a safety-planning referral belongs, and it should be an
actual referral.** Any first-run flow that asks "is this machine shared?" and
gets "yes, with the other party" should stop and point to a domestic-violence
safety-planning resource, not to a settings page. Technology safety planning for
people leaving abusive situations is a specialist practice (NNEDV's Safety Net
project is the standard reference in the US) and this project should link out
rather than invent guidance. **This is the single most important sentence in
this document that is not about code.**

**3. There is no backup and no recovery, and that is the design.** Users should
be told plainly: if this machine is lost, stolen, wiped, or taken by the other
party, the record is gone. The app should say what a safe backup looks like — an
encrypted archive on removable media kept somewhere the other party cannot reach,
or with counsel — and should provide the export that makes it possible (see F-13
and implication 17). A local-first tool that never mentions backup has quietly
transferred a serious risk to the user.

**4. Deleting case material during a live matter can be sanctionable.** Users
need one clear paragraph on preservation: *once a matter is active, do not delete
case material, including messages and photos on your phone, even if it is
unflattering; talk to a lawyer or a legal-aid advocate before removing anything.*
This is also the reason the app should not ship a wipe (F-13).

**5. Anything you generate here can end up in front of a judge.** The existing
AI-assistance disclosure (`document_store.py:23-26`) is good and is defeated in
the ordinary case by BUG-9. Beyond that fix, `legal_obligations_us.md` §6 is
right that a blanket string is not a court's certification format, and that this
must be a live-lookup problem. Documentation should say: *check whether your
court requires an AI-use disclosure, and how it must be worded, before you file
anything this tool helped you write.*

**6. This tool documents a matter; it does not monitor a person.** F-17's
boundary belongs in `MISSION.md`'s "what it will never do" list, where a partner
org and its ethics counsel will read it, and in the `homestead-affairs` org
profile that E-10 gates. The self-presentation risk both obligations documents
identify (*In re Reynoso* turning on how a tool described itself) applies with
equal force to the surveillance framing, and in the other direction: a tool that
never says where the line is will be read as not having one.

**7. What the app cannot know.** It does not know whether a record is sealed,
whether a document is under a protective order, whether a Part 2 record is in the
evidence, or what the other party's rights are in the user's jurisdiction. It
should say so, ask, and record the answer — a flag the user sets is worth more
than a classification the app guesses.

---

# E — Open questions

1. **Does the operator get the derived form on their own screen at `L4`?**
   `homestead-rungs.md` leaves this open and calls it the rung decision that most
   affects daily use. This analysis adds a fact that changes the calculus: the
   operator's screen is not private (F-1, F-2). The argument for *derived on S1*
   is much stronger once S1 is understood as a semi-public surface in the
   pre-separation household. **Suggested resolution: derived by default, payload
   behind the same passphrase that unlocks the app.** That makes one control do
   two jobs.
2. **What does the party table look like when the same human is a party in two
   matters?** (The other parent as co-debtor in the bankruptcy *and* as
   `parent_b` in the custody matter — `case_store.py:1070`'s
   `creditors.relationship` already implies this.) Cross-matter identity
   resolution is exactly what `finish_list.md` E-11's Nestor seam does, and its
   ledger currently records resolved canonical values **in cleartext**. Resolving
   a person's identity across two matters is itself an `L4` operation. Unresolved.
3. **What is a "purpose declaration" worth when the operator is the only
   principal?** The rung doc asks this and answers "most of its value is that it
   is ledgerable." Under the intra-household threat model there is a second
   answer: a purpose prompt is a *speed bump the adversary also has to cross*,
   and a record that they did. Whether that is worth the friction to the
   legitimate user is a UX question I cannot resolve from the code.
4. **Should the app support two operators on one machine at all** (each parent
   with their own matter), or refuse? Supporting it needs the `client_id`
   dimension `legal_obligations_us.md` §3 identifies; refusing it needs to be
   said out loud. Currently it neither supports nor refuses — it merges.
5. **What happens to the record at majority — genuinely?** F-14 argues the
   lawful-basis story expires with the matter. Whether the answer is purge,
   archive-to-the-subject, or archive-to-nobody is a policy decision that should
   be made before the schema hardens, not after.
6. **Is the D2/clinic direction compatible with the intra-household threat
   model at all?** A clinic laptop holding forty families' matters, with no
   `client_id`, no gate in the TUI path, and no at-rest encryption is a different
   and larger problem than the one this document analyses. Both obligations
   documents assume D2 arrives; nothing in the code is shaped for it.
7. **Could not be checked:** whether real Nest atom bodies contain the address
   forms F-4's regex matches; what `xdg-open` resolves to on the operator's
   desktop and whether it leaves recovery files; whether `willow_gate`'s
   `check_in` returns a session object on rejection (BUG-12's open branch, and the
   reason F-6's third layer matters more than the first two).

---

*Written 2026-08-04 against `/home/user/safe-app-store` at its current checkout.
No files under the repository were modified. Findings marked CONFIRMED were
traced to a file and line or executed; PLAUSIBLE findings state what could not be
checked.*

ΔΣ=42
