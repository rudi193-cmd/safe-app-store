# SAFE App Store — store-wide sweep for minors and vulnerable-adult exposure

> **Provenance.** Store-wide safety sweep, 2026-08-04. **The load-bearing
> findings were independently re-verified against source before this landed**,
> and one was corrected:
>
> - **The vault-leak linter is defeated by a spelling — CONFIRMED, reproduced
>   against `tools/vault_leak_lint.py`'s own `_extract()`.** The *identical*
>   path in two spellings: `Path.home() / ".willow" / "apps" / APP_ID /
>   "cases.db"` extracts as `~/.willow/apps/cases.db` and is classified (a leak
>   by the linter's own rules), while `Path(os.path.expanduser("~")) / ".willow"
>   / ...` extracts as bare `~` — the continuation is lost entirely. Same
>   semantics, opposite verdicts.
> - **No lint reads the manifest's privacy fields — CONFIRMED.** Grep across
>   `tools/` and `tests/` for `privacy_tier`, `data_streams`, `local_processing`
>   returns nothing. Install-time consent rests on declarations nothing checks.
> - **`utety-chat` — CONFIRMED.** Manifest declares `privacy_tier:
>   client_only`, `local_processing: 0.96`. `functions/api/chat.js` fetches
>   `generativelanguage.googleapis.com` (Gemini 2.5 Flash) at `:104` and
>   `api.groq.com` (llama-3.3-70b) at `:115`. Flat contradiction.
> - **`dating-wellbeing` — CONFIRMED WITH A CORRECTION.** `core/scoring.py:52-58`
>   has no lower age bound, and `preferred_age_range` is unbounded caller input
>   — it is set by no UI in the tree. `core/redflags.py:51-54` does rate "mature
>   for age" and "age is just a number" **yellow**, counsel *"Worth examining
>   power dynamics."* **But the sweep omitted that `ui/streamlit_app.py:32` sets
>   `min_value=18`** on the profile age field. So the accurate finding is: the
>   Streamlit entry point gates one field at 18; the core scoring library has no
>   minor check at all and will score one if driven directly; and the red-flag
>   vocabulary treats a grooming rationalisation as "worth examining" rather
>   than a stop. That is serious. It is not "the app scores minors as
>   compatible" without qualification, and the difference should be stated.
>   (App status is `parked` per `docs/app_store_vision_and_gaps.md` §6.)
>
> Findings not listed above carry the sweep's own confidence tags and were not
> independently re-run — including the `playgate`, `the-squirrel`, `nest-seed`
> and `UTETY-Reddit-Bots` findings, each of which deserves the same treatment
> before it is acted on.


**Scope:** `/home/user/safe-app-store`, 34 apps under `apps/`, plus the store's own gates.
**Excluded:** deep threat-model of `apps/law-gazelle` (separate agent). Law Gazelle appears
here only inside cross-app patterns.
**Method:** manifests read for all 34; code traced for the 14 that plausibly touch a minor or
a person in trouble; store gates (`tools/vault_leak_lint.py`, `tools/catalog_lint.py`,
`stores/promote_check.py`, `.github/workflows/store-ci.yml`, `tui.py`) read end to end and,
where claimed, executed.
**Vocabulary:** rungs `L1`–`L5` and surfaces S1–S4 from [`docs/homestead-rungs.md`](../../../../home/user/safe-app-store/docs/homestead-rungs.md).
**Read-only.** Nothing in the repo was modified.

---

## Executive summary — top five by harm

| # | Exposure | Apps | Who is harmed | Conf. |
|---|---|---|---|---|
| **1** | **The sandbox in the store's law does not exist.** `CLAUDE.md` §7 states every playground build "runs under Kart/bwrap with no ambient capability" and §6 that a build "reads and writes only its own lane." `make run app=<n>` is `cd apps/$(APP) && $(PYTHON) app.py` (`Makefile:25`). No sandbox, no lane, no capability drop. Every isolation claim protecting a child's data from a neighbouring app is unenforced. | all 34 | minors + vulnerable adults, every category | **CONFIRMED** |
| **2** | **`dating-wellbeing` scores a minor's profile as compatible and rates grooming language yellow.** `core/scoring.py:52-58` awards `+5` when `profile.age` falls inside `preferred_age_range`, with no lower bound. `core/redflags.py:51-54` classifies "mature for age", "age is just a number" as **yellow** with the counsel *"Worth examining power dynamics and shared life-stage compatibility."* `core/protocols.py:4-5` — the age-gap protocol — returns a single bland sentence. Nothing in the app tests `age < 18`. | dating-wellbeing | a minor being groomed; the tool supplies the rationalisation | **CONFIRMED** |
| **3** | **`utety-chat` declares `client_only` / 96% local and ships every turn to Google and Groq.** `functions/api/chat.js:100-118` POSTs message + full history to `generativelanguage.googleapis.com`, falling back to `api.groq.com`. `web/static/shared.js:6` routes the production client there. Meanwhile `web/chat.html:266-268` renders to the user: *"Conversation saved locally on your machine. Nothing shared without your permission."* The system prompt is client-supplied (`chat.js:78`), so a public site can be driven as an open LLM proxy on the operator's key. | utety-chat | anyone, incl. minors reaching `utety.pages.dev` who installed nothing | **CONFIRMED** |
| **4** | **`playgate`'s parent gate is a UI convention, not an authorization boundary.** Kid UI and parent UI are served from one unauthenticated loopback origin (`playgate/server.py:30, 203-210`). `POST /api/requests/<id>/answer` takes the answering parent's name from the request body (`server.py:143-171`, `disposition.py:119-123`). The child's browser can grant the child's own request and trigger the APK install. `/api/roster` (`server.py:111-113`) hands the roster of children to anything on loopback. | playgate | the child the gate exists to protect; the parent gets a log that reads as if they decided | **CONFIRMED** |
| **5** | **The store's only mandatory data-location gate is defeated by a spelling.** `tools/vault_leak_lint.py` declares `~/.willow/apps/<id>` a LEAK that must FAIL (`classify()`:100-101), but `_extract()` (lines 52-67) only recognises `Path.home() / …`. Six live apps write user data there via `Path(os.path.expanduser("~")) / ".willow" / "apps" / APP_ID` — which extracts as the bare string `~` and is classified `skip`. All six are green in CI. | the-binder, ask-jeles, nasa-archive, field-notes, utety-chat, law-gazelle | everyone whose data those apps hold | **CONFIRMED** (reproduced against the linter's own functions) |

**The one store-level gap that matters most:** the store has **no manifest schema**. `privacy_tier`,
`permissions`, `data_streams` and `local_processing` are never validated — not for presence, not
against a vocabulary, and never against code. See [Store-level gaps](#store-level-gaps).

---

## Inventory — all 34 apps

Rating: **HIGH** = holds/produces data about a minor or a person in legal, medical, financial or
intimate jeopardy, and something is wrong. **MED** = touches such data, controls appear adequate.
**LOW** = no such data.

| App | Rating | Subject | Lands on disk | Net | One line |
|---|---|---|---|---|---|
| `dating-wellbeing` | **HIGH** | both | vault (`utils/dw_paths.py`) | local | Age-scores profiles with no minor floor; grooming vocabulary rated yellow; stores third parties' profiles permanently. |
| `utety-chat` | **HIGH** | minor | vault + `~/.willow/apps/` + Postgres | **Gemini, Groq** | `client_only` is false; UI text is false; public endpoint, client-supplied system prompt. |
| `playgate` | **HIGH** | minor | vault (clean) | loopback | Two principals, one unauthenticated origin. Everything else about this app is right. |
| `the-squirrel` | **HIGH** | minor | `~/.squirrel`, **`~/Desktop`** | local Ollama | GEDCOM export defaults to Desktop with **no living-person suppression**; names + DOBs of living children go into a local LLM prompt. |
| `nest-seed` | **HIGH** | both | vault + operator-chosen | fleet-KB manifest | `bridge.py` egresses the owner's **name** in an atom whose own docstring says "no person names"; `NEST_DIGEST.md` lists everyone found in the dump. |
| `UTETY-Reddit-Bots` | **HIGH** | minor | Devvit Redis (3rd party) | **Reddit** | `PRIVACY.md` says "do not track users, build profiles"; `flair.ts:34-49` keeps a 1-year per-username counter and publishes the tier as public flair. |
| `the-binder` | **MED-HIGH** | both | `~/.willow/apps/the-binder/intake` | local | `contribute()` writes without consulting the consent object; `on_revoke()` reports `data_deleted` and deletes nothing. |
| `marching-arts` | **MED** | minor | vault, SOIL-scoped | none | **Reference implementation.** Birthdate not `is_minor`; guardian authority expires at majority; hash-chained consent log; manifest is the most honest in the store. Deletion half-built, and it says so. |
| `terpsi-chat` | **MED** | minor | in-memory only | none | **Reference implementation.** Adult/minor separate tables; witness required on staff↔minor channels; SMS notices structurally cannot carry content (`notify.py`). Names its own `guardian_links` defect in the manifest. Schema only — nothing device-side has run. |
| `nasa-archive`, `ask-jeles`, `field-notes` | MED | vulnerable adult | `~/.willow/apps/<id>` (lint-invisible) | mixed | Personal notes/queries at a path the store's gate declares a leak and cannot see. |
| `law-gazelle` | *(other agent)* | both | `~/Desktop/Nest`, `~/.willow/apps/` | local | In scope here only as a member of the `APP_DATA` and `expanduser("~")` cohorts. |
| `band-camp-arcade` | LOW-MED | minor | browser localStorage | none | Explicitly *for* children. Data is best-times plus a free-text "complaint" diary. Manifest is exemplary; nothing in it says "children". |
| `jarvis` | LOW-MED | bystanders | IndexedDB/localStorage | **Anthropic + browser vendor** | Manifest is the most honest in the store about its own exposure. Ambient mic captures household members who never consented. |
| `story-timeline` | LOW-MED | — | vault | loopback | Manifest has **no `privacy_tier`, no `data_streams`, no `local_processing`**. Ships as `gated`. |
| `bt-controller` | LOW-MED | — | none | Bluetooth | Same: manifest has none of the three privacy fields. Ships as `building`. |
| `civics-check` | LOW | minor | vault | none | Kid quiz modes; stores scores and spaced-repetition state only. Clean vault paths. Fine. |
| `the-nightstand`, `oakenscrolls-office`, `kitchen-pudding`, `field-acoustics`, `bureau`, `marching-arts-shell`, `njord`, `private-ledger`, `public-ledger`, `source-trail`, `semantic-translator`, `ratatosk`, `vision-board`, `game`, `llmphysics-bot` | LOW | — | vault / localStorage | mostly none | No minor data, no distressed-adult data, or data confined to the operator's own low-stakes records. `game` declares `cloud_llm_free` and has no network code — overstatement, the safe direction. `vision-board` classifies user images via local Ollama only. |
| `llmphysics` | LOW | — | — | — | Archived. Its manifest is named `safe-app-manifest.**js**` — invisible to every tool in the repo. |

---

## Findings

### F1 — The sandbox described in the store's law does not exist
**Rung/surface:** governs all rungs on S3/S4. **Confidence: CONFIRMED.**

`CLAUDE.md` rules 6 and 7 are the store's isolation model:

> "Each `apps/<name>/` build is scoped to **its own SOIL collection**, default-deny reach, and
> **no fleet-store writes**." … "A build runs under Kart/bwrap with no ambient capability."

The runner is `Makefile:24-25`:

```make
run: venv
	cd apps/$(APP) && $(PYTHON) app.py
```

The only `bwrap` in the repository is `tools/seam_install.py:47-57`, which sandboxes the *digesting
of an install artifact*, not the running of an app — and it degrades silently: `_have_bwrap()`
returning `False` proceeds unsandboxed and records `sandboxed_stage: false` in a receipt nothing
gates on.

Corroborating: only **9 of 34** manifests declare `store_scope` at all, and no test, lint or CI step
reads the field. Rule 6 has no enforcement anywhere.

**Who is harmed:** this is the load-bearing assumption under every other app-level control. If
`the-squirrel` can read `~/Desktop/Nest`, or `game` can read playgate's `requests.jsonl`, then the
per-app care taken by `marching-arts` and `terpsi-chat` protects nothing at the boundary that
matters. Minors and vulnerable adults both.

**What should be done:** either build the runner the law describes, or amend the law. The cheap
honest move is the second: change `CLAUDE.md` §7 to say builds run **unsandboxed with the operator's
full authority**, and add the consequence — *do not run a playground build on a machine holding
another person's records.* That is a documentation fix, and it is worth more than a partial sandbox,
because the current text causes readers to stop asking.

The engineering move, if taken: a `make run` that wraps in bwrap with `--ro-bind` on `/`, a
writable bind only on the app's own vault dir, and `--unshare-net` unless the manifest declares a
network permission. Cost: several apps break immediately (`jarvis`, `utety-chat`, `njord`,
`ask-jeles` all need egress; `the-squirrel` writes to `~/Desktop`), which is the point — the breaks
are the inventory of who is currently exceeding their declaration.

---

### F2 — `dating-wellbeing`: a minor scores as compatible, and grooming reads as yellow
**Minor + vulnerable adult · `L4` · S1 (the operator's screen) and the stored pattern DB.
Confidence: CONFIRMED.**

`apps/dating-wellbeing/core/models.py:5` — `age: Optional[int] = None` on `Profile`, unconstrained.

`apps/dating-wellbeing/core/scoring.py:50-60`:

```python
    # Age compatibility bonus (if both parties have ages)
    age_range = user_prefs.get("preferred_age_range")
    profile_age = getattr(profile, "age", None)
    if age_range and profile_age:
        try:
            min_age, max_age = age_range
            if min_age <= profile_age <= max_age:
                score += 5
```

`preferred_age_range` is user-supplied. A profile with `age = 15` and a range of `(14, 20)` earns
`+5` toward `category ∈ {good_enough, strong, exceptional}`. No branch in the app tests `age < 18`.

`apps/dating-wellbeing/core/redflags.py:51-54` puts the canonical grooming script in the **yellow**
band:

```python
    "age_gap_rationalize": FlagDef("yellow", (
        "mature for age", "age is just a number", "don't let age stop us",
        "age doesn't matter when",
    ), "Worth examining power dynamics and shared life-stage compatibility."),
```

and `core/protocols.py:4-5` is the whole of the escalation:

```python
def age_gap_protocol(result):
    return "Age gap noted. Consider context and power dynamics."
```

**Who is harmed, how badly.** Two directions, both bad. If the operator is an adult evaluating a
minor, the app returns a compatibility score and a measured sentence about power dynamics — it
launders the situation. If the operator is themselves a minor using it on an adult's profile, the
same yellow rating tells them the language they are being fed is a nuance to consider. The app's
stated purpose is red-flag detection; on the one flag where the answer is categorical, it
deliberates.

Compounding: the manifest declares `patterns` retention `permanent`, and `data_streams.profiles`
holds screenshots and OCR of **third parties who are not users of the app** and have no path to
know they are in it.

**What should be done:** `age < 18` on either party must be a terminating condition, not an input to
a score — refuse to score, state why, and offer nothing that reads as evaluation. `age_gap_rationalize`
belongs in the `danger` band with an `intervention_level` that names the pattern. Neither is a large
change; both are decisions, and the current code shows the decision was never taken.

**Tension worth naming:** this app is `stalled` in the catalog and 12 files long. The store's easy
answer is "it's a prototype." But a stalled app is still installable through the TUI, still declares
`client_only`, and still presents a green privacy badge. *Stalled is not the same as unreachable,
and the store currently treats them as the same.*

---

### F3 — `utety-chat`: `client_only` is false, and the UI says so in the user's own words
**Minor · `L3`/`L4` composed into S2 and S4 · Confidence: CONFIRMED.**

Manifest declares `privacy_tier: "client_only"`, `local_processing: 0.96`, and **no `network` key**.
`data_streams` names three streams, all local. What the code does:

`functions/api/chat.js:88-118` — the deployed Cloudflare Pages function forwards `message` plus the
entire `history` array to `generativelanguage.googleapis.com/v1beta/.../gemini-2.5-flash`, and on
`429` falls back to `api.groq.com` with `llama-3.3-70b-versatile`. `web/static/shared.js:6` sets
`CHAT_API = '/api/chat'` in production, so this is the default path for anyone using
`https://utety.pages.dev`.

`web/chat.html:266-268` renders, under the input box:

```html
      <div class="chat-consent">
        Conversation saved locally on your machine. Nothing shared without your permission.
      </div>
```

Both halves are false on the hosted path. This is not a manifest oversight; it is a sentence
displayed to a person at the moment they type.

`chat_db.py:133-165` writes every message to Postgres with no expiry and no deletion path (`grep
"DELETE FROM"` across the app returns exactly one hit, in `tui_db.py:66`), against a declared
retention of *"All chat messages deleted when you close the app."*

**Two further properties of the hosted endpoint:**

- `const systemPrompt = persona || '…'` (`chat.js:78`) — the system prompt is entirely client-supplied.
  Any HTTP client can set it. The "professor" characters are a client-side convention; there is no
  server-side persona, no content policy, and no age gate anywhere in `web/`.
- Rate limiting is an **in-process `Map`** (`chat.js:37`, `worker/index.js:9`). Cloudflare Workers
  are per-isolate and ephemeral; the 20/hour cap is notional, not a control.

**Who is harmed.** A minor who finds `utety.pages.dev` — playful faculty personas, a pixel-art
campus — is a data subject who never installed anything, never saw the store's consent modal, and
whose conversation goes to two US LLM vendors under an operator's API key. COPPA's under-13 line and
the UK AADC's "likely to be accessed by children" test (surveyed in
`apps/law-gazelle/docs/legal_obligations_us.md` / `_intl.md`) both plausibly reach this site; the
store's consent model does not reach it **at all**, because nobody installed it. See G5.

**What should be done:** (a) correct the manifest to `privacy_tier: "mixed"`, `local_processing: 0.0`
for the hosted path, and add a `network` string naming Google and Groq — `jarvis` shows exactly how
to write this; (b) replace the `chat-consent` line with the truth; (c) move the persona server-side
and reject client-supplied system prompts; (d) decide, and write down, whether the public site is
intended for minors, because that answer changes what (a)–(c) have to be.

---

### F4 — `playgate`: the gate is a URL apart
**Minor · `L3` · S1 · Confidence: CONFIRMED.**

Everything about this app's *data* handling is right: vault-rooted paths with a comment explaining
why (`playgate/paths.py:12-15`), append-only log, a reason required to grant as well as refuse
(`disposition.py:124-128`), evidence snapshotted at decision time, expiry derived rather than
written, a fixed roster instead of a text box. It is the most carefully reasoned small app in the
store.

The gap is the principal boundary. `server.py:30` serves `/kid/` and `/parent/` from one
`ThreadingHTTPServer` on `127.0.0.1:8424`, and there is no authentication of any kind — no token, no
separate port, no header check. `do_POST` routes `/api/requests/<id>/answer` to `_answer()`
(`server.py:143`), which passes `by=body.get("by", "")` straight into `Log.answer()`. The only
validation is `if not by.strip()` (`disposition.py:122-123`) — a non-empty string.

So a child on the machine can open `/parent/`, or `fetch()` the endpoint from the kid page's own
console, grant their own request with `by: "Mum"` and a reason, and `_answer()` proceeds to
`self._install(app)` — a real APK install into Waydroid (`server.py:166-171`). The disposition log
then contains a granted row attributed to a parent who never saw it, and the log is append-only, so
the false attribution is permanent and indistinguishable from a real decision.

`serve()` refuses a non-loopback bind (`server.py:205-209`) with a comment that names the stake:
*"this host serves a child's request queue and a parent's decisions."* The refusal is correct and
addresses a different threat. `tests/test_no_egress.py` covers egress; nothing covers principals.

**Who is harmed:** the child, who is now running an app nobody vetted; and the parent, whose log —
the app's whole product — silently becomes untrustworthy. The harm scales with how much the parent
trusts the record, which this app has worked hard to make high.

**What should be done.** The honest framing is that this app has **two principals on one machine**,
which is the one shape the rest of the store never faces (every other app has a single operator).
Minimum viable: `serve()` mints a random parent token at startup, prints it to the terminal the
parent started it from, requires it as a header on `/parent/*` and on `POST …/answer`, and `_answer()`
records that the token was presented. Kid UI never receives it. Cost: the parent must fetch the
token from a terminal, which is friction on a family tool — and that friction *is* the control.
Weaker alternative: bind the parent UI to a second port and document that the child's device reaches
only the first; that is a network assumption a child on the same machine defeats, and should be
labelled as such rather than counted as mitigation.

---

### F5 — `the-squirrel`: living children exported to the Desktop, and named to a model
**Minor · `L3`→`L4` · S2 and S4 · Confidence: CONFIRMED.**

Two separate paths.

**S4 — export.** `responder/commands/gedcom.py:14`:

```python
    export_dir = Path(os.environ.get("SQUIRREL_EXPORT_DIR", Path.home() / "Desktop"))
```

`gedcom/exporter.py` has no living-person suppression: `grep -n "living\|RESN\|PRIV"` returns only
`death_date`/`death_place` handling at lines 75-77. Every person in the tree — including living
children, with `full_name`, `birth_date`, `birth_place` and family linkage — is written in plaintext
GEDCOM 5.5.1 to `~/Desktop/squirrel_export_<date>.ged`. Redacting living individuals on export is
the long-standing default in genealogy tooling; here it is absent, and the destination is the most
screen-shared, most cloud-backed, most casually-attached directory on a machine.

The export **is** gated (`_gate.authorized("export")`, and the gate is genuinely fail-closed —
`sap/core/gate.py:36-39` documents that no actor context means `PermissionDenied` and a missing
willow-gate means the same). The gate governs *who may export*. Nothing governs *what the export
contains* or *where it lands*.

**S2 — the model prompt.** `responder/llm/chat.py:29-41` builds the Ollama context:

```python
        line = f"- {p['full_name']} (id={p['id']})"
        if p.get("birth_date"):  line += f", b.{p['birth_date']}"
        if p.get("birth_place"): line += f", {p['birth_place']}"
```

Under `docs/homestead-rungs.md`, "Child's name, DOB, school" is `L4` (line 147), and `L4` **never
reaches a model prompt as a payload** — an explicitly named hard stop (line 218). A genealogy tree
routinely contains living minors. There is no living/deceased filter and no rung check on this path.
It is local Ollama, so it does not egress — but S2 is a surface by the store's own model, and this
is the store's clearest instance of a rung the docs define and the code has never been made to obey.

**What should be done:** default `SQUIRREL_EXPORT_DIR` under the vault, not the Desktop; suppress
persons with no `death_date` and a `birth_date` inside a living window (or no `birth_date` at all)
behind an explicit `--include-living` flag that names the count it is about to include; and in
`_build_context`, serve the derived form (`"a person in the tree matching that name"`) unless the
person is deceased.

---

### F6 — `nest-seed`: the "PII-safe" bridge egresses the operator's name
**Vulnerable adult (household incl. children) · `L3` mis-scored as `L2` · S4 · Confidence: CONFIRMED.**

`apps/nest-seed/bridge.py:48-52` states the contract:

> "No fragment content, filenames, **person names**, or secret values are included — only counts,
> curated category names, and redacted secret *kinds*."

Lines 64, 74, 76, 82-84, 93-94 then build the atoms:

```python
    owner = _owner(conn)                       # SELECT owner FROM nest_meta
    ...
        "title": f"Nest structure: {owner}",
        "summary": (f"{owner}'s local Nest holds {src_total} sources / ...
        "tags": ["nest", "structure", "personal-data", safe_owner],
        "keywords": ["nest", "nest-seed", "bridge", owner],
```

`owner` is a person's name — `README.md:64` shows the invocation `--owner "Your Name"`. The
docstring's exclusion list is contradicted four lines below it.

Second problem: the summary carries **operator-authored category labels**. `curate.py` exists so the
operator can rename machine-coined clusters before they bridge out. Those names are free text. The
module's own worked example is *"this operator keeps a large legal/co-parenting archive"* — a named
person plus a custody matter. Under the rung procedure (step 2a), an aggregate is `L2` only after a
re-identification check; here it is not derived at all, it is attributed by construction, and the
re-identification check is delegated to the operator's naming discipline.

Third: `digest.py:49-50` writes `NEST_DIGEST.md` beside the DB containing "the people who show up" —
a Counter over every `Firstname Lastname` in the corpus. For a household dump seeded from school
letters, medical correspondence and custody paperwork, that is a plaintext roster of the household's
children next to the database.

The pipeline's only redaction is credential-shaped (`libs/nest-pipeline/src/nest_pipeline/secrets.py`
— API keys, JWTs). There is no detector for a person, a minor, a health category or an immigration
status anywhere in the pipeline.

**What should be done:** drop `owner` from bridged atoms entirely (a stable opaque `source_id`
already exists — `f"nest:{safe_owner}:structure"` should become a hash); refuse to bridge a category
label that has not passed an allowlist or been explicitly marked publishable by the operator at
bridge time; and either move `NEST_DIGEST.md` under the vault or stop emitting the person Counter.

---

### F7 — `UTETY-Reddit-Bots`: a public engagement profile on accounts that may belong to 13-year-olds
**Minor · `L3` · S4 · Confidence: CONFIRMED.**

`PRIVACY.md` §Summary: *"The Bots do **not** track users, build profiles…"* and §2: *"The Bots do
**not** store: … Usernames, user IDs, or any information about authors beyond the cooldown flag
keyed to their username."*

`hanz-bot/src/lib/flair.ts:29-49` (identical in `oakenscroll-bot`):

```ts
  const key = `hanz:flair:${username}`;
  const count = await context.redis.incrBy(key, 1);
  if (count === 1) {
    await context.redis.expire(key, 60 * 60 * 24 * 365); // 1 year
  }
  const flairText = tierFor(count);
  ...
    await context.reddit.setUserFlair({ subredditName, username, text: flairText });
```

That is a per-username interaction counter with a **one-year** TTL, and the resulting tier
("Student" → "Copenhagen Certified") is written as **public subreddit flair**. It is a persistent
engagement profile, published, attached to a named account, produced by an app whose privacy policy
says it builds no profiles. `spamguard.ts:28-29` adds two more per-username keys.

`logger.ts:4` sets `DEBUG_MODE = true` unconditionally; `flair.ts:49` and `summon.ts:125` then log
usernames and reply text to the Devvit console, which the app developer can read. `PRIVACY.md` §2
says the bots store no telemetry.

Manifest: `privacy_tier: "public"`, `data_streams: []`, `permissions: ["knowledge:read"]` — nothing
indicating per-user state on a third-party platform.

**Who is harmed:** Reddit's floor is 13. A 13-to-17-year-old in one of these subreddits accrues a
visible badge tracking how often they engaged with a bot, cannot see the counter, was told in
writing that no such counter exists, and has no deletion path (`PRIVACY.md` §7: *"there is no user
data to export or delete"* — which is now untrue). Not catastrophic, but it is the exact shape of
harm the policy was written to disclaim, and the disclaimer is the thing a moderator relied on when
installing.

**Also PLAUSIBLE, unverified:** `llmphysics-bot/praw-bot/plugins/mod_digest.py:36-40` reads a
mod-only wiki page and submits its verbatim contents as a **public sticky post**. If moderators use
that page for notes about users — a natural use for a page called "mod digest" — the bot publishes
them. I could not determine who writes that page or what convention governs it.

**What should be done:** correct `PRIVACY.md` to describe the flair counter, or remove the counter.
Set `DEBUG_MODE` from an env var, default off. Declare the Redis keys in `data_streams`.

---

### F8 — The consent apparatus that six apps carry and none of them calls
**Both · Confidence: CONFIRMED.**

Seven apps ship a `SAFESession` class with `on_consent_granted` / `can_access_stream` /
`on_revoke`: `dating-wellbeing`, `the-binder`, `game`, `ask-jeles`, `nasa-archive`, `utety-chat`,
`law-gazelle`. Searching every call site outside the class definitions, exactly **one** app ever
invokes it — `utety-chat/server.py:115,144`. In the other six the object is never instantiated by
any code path; it is decoration that reads, to anyone auditing the app, as data governance.

Two consequences, both live in `the-binder` and mirrored elsewhere:

`safe_integration.py:48-62` — `contribute()` writes a JSON file into
`~/.willow/apps/the-binder/intake/` with no reference to `can_access_stream` and no session at all.
The declared `knowledge_atoms` stream is marked `"required": True` with the prompt *"May I store
your knowledge atoms in the local database?"* — a question the code never asks.

`safe_integration.py:150-154` — revocation:

```python
    def on_revoke(self, stream_id: str) -> Dict:
        if stream_id in self.consents:
            self.consents[stream_id]["granted"] = False
            self.consents[stream_id]["revoked_at"] = ...
        return {"status": "revoked", "stream": stream_id, "action": "data_deleted"}
```

Nothing is deleted. No file removed, no row dropped. An in-memory flag flips on an object that dies
with the process, and the caller is told `data_deleted`. The same literal appears in
`ask-jeles:179`, `nasa-archive:139`, `dating-wellbeing:118`, `utety-chat:216`, and in `game:56,72`
as a boolean.

**Who is harmed:** anyone who revokes. Most acutely a guardian withdrawing a child's data, or an
adult withdrawing after a relationship ends — the two moments when a person most needs erasure to be
real, and the two moments when they are most likely to check only the return value.

**What should be done:** delete the dead class from the six apps that never call it — a nominal
control is worse than none, because it is counted as mitigation in exactly this kind of review. In
the one app that does call it, make `on_revoke` either perform the deletion or return
`{"action": "flag_cleared", "data_deleted": false}`. A store rule follows: **no app may return a
claim of erasure it does not perform**, and that is checkable — grep for `data_deleted` and require
a `DELETE`/`unlink` in the same function.

---

## Store-level gaps

*The highest-value section. Each of these affects all 34 apps at once.*

### G1 — There is no manifest schema

`tools/catalog_lint.py:173-188` is the entire manifest gate:

- the file exists (error for `building`/`gated`/`stalled`, warning for `seeded`);
- it parses as JSON;
- `manifest["app_id"] == directory name`.

That is all. `privacy_tier`, `permissions`, `data_streams`, `local_processing` are **never read** by
any lint, test or CI step. `stores/promote_check.py:203` checks that the three key *names* are
present at promotion time — presence, not correctness — and no app has ever been promoted, so even
that has never run on a real candidate.

Observable consequences, all currently green in CI:

- `story-timeline` (status `gated`) and `bt-controller` (status `building`) have manifests with **no
  `privacy_tier`, no `data_streams`, no `local_processing`.**
- `apps/llmphysics/safe-app-manifest.**js**` — wrong extension, invisible to every tool. (Archived,
  so harmless today; it would pass unnoticed if un-archived.)
- The tier vocabulary is uncontrolled: `client_only`, `mixed`, `public`, `local`, `local_first` —
  five spellings, no enum. `tui.py:182` colours the badge with
  `p_color = "green" if tier in ("client_only", "local") else "yellow"`, so **`njord` (genuinely
  local-first) shows yellow and `utety-chat` (ships to Google) shows green**, decided by a
  free-text string nothing validates.
- `local_processing` is a float nothing derives or checks. Nine apps declare `0.96`. `jarvis`'s
  manifest note says the quiet part: *"A number that has to be explained in prose is not doing the
  work of a number, and inventing precision here is the failure this store's own apps have elsewhere
  at 0.96."*

**Recommendation.** Add `tools/manifest_lint.py` to the `gates` job, requiring: `privacy_tier` from a
closed enum; `data_streams` present (possibly empty, but the key required); every `permissions`
entry drawn from a registry — which also fixes `tui.py:51-70`, where `microphone`, `network_egress`,
`bluetooth`, `cloud_llm_free`, `pattern_storage`, `image_ocr`, `family_history:read` and a dozen
others have no human label and render as raw identifiers on the consent screen. **Cost:** three apps
break on day one and every future app pays a small tax. That is the store-easy-to-ship versus
store-safe-to-ship tension in its cheapest possible form, and this is the side to take it on.

### G2 — The store models no data subject other than the operator, so minors are invisible at install

Confirmed by search: no `minors`, `audience`, `age`, `subject`, or equivalent field exists in any
manifest, in the catalog schema (`entry keys: author, canonical, description, id, majors, name,
path, repository, status, tags, tier, version`), or in `promote_check.py`.

The result at the consent modal (`tui.py:148-196`):

- `marching-arts` — birthdates and guardianship records for minors — displays
  `◆ pattern_storage` and `Privacy: client_only · 100% local`.
- `field-notes` — an adult's own scratch notes — displays the same two lines.

They are **indistinguishable at the moment of consent.** `privacy_tier` answers *where does this run*.
It never answers *whose life is in it*.

**Recommendation.** Add a `subjects` array to the manifest — e.g. `["operator"]`, `["household"]`,
`["minors"]`, `["third_parties"]` — required, and surface it as the first line of the consent modal
above permissions. It is a declaration, so it can be wrong; but it is *checkable against the app's
own README and schema in review*, and it creates the vocabulary in which "this app holds children's
records" can be said at all. Today it cannot be said.

**And promote the rung model out of `docs/`.** `docs/homestead-rungs.md` is scoped to one app
(law-gazelle → homestead.keep). Its `L1`–`L5` × S1–S4 crossing table is the only model in this repo
that gets minors' data right — `L4` includes "minors' data" explicitly (line 105), composition is
`max`, absence fails closed, and `L4` never reaches a model prompt. Three findings above (F5, F6, and
law-gazelle's own) are rung violations that the model already names. It should be a store-wide
manifest field: each `data_stream` carries a `rung`, and an unclassified stream fails the build,
exactly as the doc prescribes (line 194: *"An unclassified field is a build failure, not a default"*).

### G3 — The vault-leak linter has a blind spot that six apps sit in

Reproduced directly against the linter's own functions:

```
_extract('_APP_DATA = Path(os.path.expanduser("~")) / ".willow" / "apps" / APP_ID')
  → ['~']                                        → classify → ('skip', 'bare home')

_extract('_APP_DATA = Path.home() / ".willow" / "apps" / APP_ID')
  → ['~/.willow/apps']                           → classify → ('leak', 'per-app data dir
                                                     under ~/.willow/apps (outside vault)')
```

Identical semantics; one FAILs the store's only mandatory data-location gate and one is invisible.
`_extract()` (lines 52-67) handles `Path.home() / …`, `expanduser("~/…")`, `Path("~/…").expanduser()`
and bare `"~/…"` literals — but `Path(os.path.expanduser("~")) / …` yields the segment `"~"` alone,
and the following `/ ".willow" / "apps"` segments are never joined to it.

Six live apps use exactly that idiom: `the-binder:27`, `ask-jeles:28`, `nasa-archive:25`,
`field-notes:23`, `utety-chat:25`, `law-gazelle:23`. All report PASS or WARN.

Two adjacent weaknesses in the same file:

- **`~/Desktop` alone is not a leak.** `classify()` flags `desktop` **and** `nest` together
  (line 102). Plain `~/Desktop` falls through to `("unknown", …)` → WARN, and `--strict` gates on
  FAIL only (line 214). `the-squirrel`'s full genealogy export to the Desktop (F5) is therefore CI-green.
- **The linter reads `*.py` and nothing else** (line 125). `jarvis`, `band-camp-arcade` and
  `marching-arts-shell` return `UNKNOWN`. To the repo's credit this was found and fixed honestly —
  `UNKNOWN` replaced a false `PASS`, and `tests/test_vault_lint_vacuous_scan.py` holds it. But
  `--strict` still gates on FAIL alone, so a JavaScript app that writes a child's data anywhere it
  likes passes the store floor by not being scanned.

**Recommendation.** Extract paths from the AST rather than by line regex, so an equivalent expression
cannot hide behind a different spelling; treat any `~/Desktop/*` write as a leak; and make
`UNKNOWN` fail `--strict` for any app whose manifest declares a persistent `data_stream` — an app
that says it persists and cannot be scanned is not clean.

### G4 — Controls are uniform where they should differ, and absent where they should exist

Reading every HTTP surface in the store: `playgate`, `story-timeline`, `oakenscrolls-office`,
`private-ledger`, `nasa-archive`, `vision-board`, `public-ledger`, `ask-jeles`, `semantic-translator`,
`utety-chat` (dev). **All default to loopback. None has authentication of any kind** — no token, no
password, no header check. `tests/test_no_unauthenticated_bind.py` enforces the loopback default
store-wide (and its docstring records that two apps previously served their full API on `0.0.0.0`
with CORS but no auth), which is a genuinely good gate.

Loopback-only is a principled control for a single-operator household app, which is 33 of the 34.
It is the wrong control for `playgate`, whose entire premise is **two principals on one machine**
(F4). The store's uniformity is a strength that becomes a blind spot at the one app whose threat
model differs — and nothing in the store's rules asks an app to state its principals, so nothing
would have caught it.

Note also that the drift-guard matches the *literal* `host="0.0.0.0"`. A default of
`--host 0.0.0.0` in argparse would pass. Today `ask-jeles/serve.py:171` and
`semantic-translator/cli.py:276` both default to `127.0.0.1` — correct, but by author discipline,
not by the gate.

**Where controls exist but should not be counted as mitigation:**

| Control | App | Status |
|---|---|---|
| `SAFESession` consent | 6 of 7 apps | never invoked — decoration (F8) |
| `on_revoke → data_deleted` | 6 apps | claims erasure, performs none (F8) |
| `_gate.authorized("export")` | the-squirrel | **real and fail-closed** — gates *who*, not *what* or *where* (F5) |
| CORS allowlist | utety-chat | browser-only; direct POST unaffected |
| in-memory rate limit | utety-chat | per-isolate on Workers — notional |
| bwrap in `seam_install` | store | degrades silently to unsandboxed |
| `store_scope` | 9 of 34 manifests | declared, never read by anything |

### G5 — Cloud-facing apps sit outside the consent model entirely

The store's consent mechanism is `tui.py`'s `ConsentModal`: it fires at install, on the operator's
machine, showing that operator the manifest. Three apps have users who never pass through it:

- **`utety-chat`** at `utety.pages.dev` — a stranger, possibly a child, types into a hosted page.
- **`UTETY-Reddit-Bots`** — the bot acts on every commenter in a subreddit where a moderator installed it.
- **`llmphysics-bot`** — same.

For all three, the data subject and the installer are different people, and only the installer sees a
consent screen. For the Reddit bots the installer is a moderator consenting *on behalf of a whole
subreddit* — which is a real authority over the subreddit and no authority at all over a 14-year-old's
username being counted for a year.

**This is not fixable in `tui.py`.** It belongs in the store's rules. Proposed rule:

> An app that can be reached by a person who did not install it must carry a **published privacy
> notice at the point of use** — not only a `PRIVACY.md` in the repo — and its manifest must declare
> `subjects: ["third_parties"]`. Where the reachable population plausibly includes minors (any public
> web page; any Reddit surface, floor 13), the app must additionally name that population in the
> manifest and state what it does not collect about them. The store must not list such an app as
> `gated` until the notice exists and matches the code.

Today `utety-chat` is `gated` in the catalog with a manifest that says `client_only` and a page that
tells the user nothing is shared.

### G6 — `APP_DATA` is a global env var that collapses six apps' vaults into one

`libs/vault-paths/src/vault_paths/__init__.py:31-35`:

```python
def app_dir(app_id: str, env_var: str = "APP_DATA") -> Path:
    env = os.environ.get(env_var)
    return Path(env).expanduser() if env else vault_root() / app_id
```

The override variable is **generic and shared**. Five apps call `app_dir(APP_ID)` and take that
default: `playgate`, `dating-wellbeing`, `ask-jeles`, `civics-check`, `law-gazelle` (plus
`kitchen-pudding` and `story-timeline` via related paths). If `APP_DATA` is set in the environment —
a plausible name for anything to set — **all of them resolve to the same directory**: a child's app
requests, a legal matter's case store, and a dating-profile analyser's pattern DB in one folder,
with a `~/.willow/store` layout that assumed separation.

`njord` gets this right: `paths.py:19` passes `env_var="NJORD_HOME"`.

**Recommendation:** make `env_var` required with no default, or derive it as
`f"{APP_ID.upper().replace('-','_')}_HOME"`. Small change, removes a whole class of cross-app
collision. **Confidence: CONFIRMED** as a code property; I did not test a machine with `APP_DATA`
actually set.

### G7 — Uninstall does not erase

`tui.py:651-672`: uninstall calls `store_mcp.app_uninstall`, discards the app from `_installed`, and
**pops the consent record** — `self._consent.pop(app_id, None)`. Nothing touches the app's vault
directory. So the data survives and the *record that the user consented to it* is the thing that gets
deleted. That is backwards: after uninstall the store holds a child's playgate log, a genealogy DB or
a case store, with no record of who agreed to what.

**Recommendation:** retain the consent record after uninstall (marked `uninstalled_at`), and either
erase the app's vault dir or state plainly in the confirm dialog that data is retained and where.
`ConfirmModal` currently says only `Uninstall <name>?`.

### G8 — Two smaller CI observations

- `store-ci.yml:325` — `test.needs: [gates, app-tests, browser-resolver, browser-mechanisms]`.
  **`bureau-differential` is not in that list**, despite the comment at line 271-273 asserting "Both
  are in `test`'s `needs:`, so neither can be skipped without branch protection noticing." Branch
  protection on `test` would not notice a red `bureau-differential`.
- `app-tests` runs 9 of 34 apps (`store-ci.yml:138-139`). Four more have dedicated workflows. **About
  20 apps have no test job at all** — including `dating-wellbeing`, `the-squirrel` (which *is* in the
  matrix — 9 listed includes it), `nest-seed` and `UTETY-Reddit-Bots`. This is a resourcing reality,
  not a defect, but it means "CI is green" carries much less information than it appears to.

---

## What is right, and worth copying

Naming these matters, because the recommendations above are all "be more like these":

- **`marching-arts`** — stores a **birthdate, not an `is_minor` flag** (`safe-app-manifest.json`,
  `data_streams.people`), with the reason: *"a flag is true until somebody remembers to run the job
  that clears it."* Guardian authority expires at majority in the resolver, not by a cron
  (`consent.py:428-487`). Hash-chained consent log with a count anchor against tail truncation.
  Retention declared **"NOT YET DECIDED"** with three paragraphs on why — after the manifest had
  previously claimed `permanent` and was checked. That is the standard.
- **`terpsi-chat`** — adults and minors in separate tables so a private adult–minor channel *has no
  representable form*; guardian visibility is structure-only by view construction; `notify.py` takes
  a template key and no other argument, so an SMS preview cannot be added without changing a
  signature. It also names its own defective `guardian_links` in the manifest and says do not port it.
- **`jarvis`** — refuses `client_only`, rates `local_processing: 0.0` and explains why the field is
  the wrong instrument, documents that browser speech recognition is server-side, and states that
  `android/` **has never been compiled**. `utety-chat` should be read against this manifest.
- **`playgate`'s** data model, and **`band-camp-arcade`'s** data_streams, which describe a free-text
  field as free text rather than as "a number".

---

## Concrete changes

**Store rules (documentation — the highest-value items here):**

1. Amend `CLAUDE.md` §7 to state the truth about sandboxing, plus the consequence: do not run a
   playground build on a machine holding another person's records. (F1)
2. New rule: **no app may return a claim of erasure it does not perform.** (F8)
3. New rule: an app reachable by non-installers must carry a privacy notice **at the point of use**
   and declare `subjects: ["third_parties"]`; if minors are plausibly in the reachable population,
   say so and say what is not collected. (G5)
4. New rule: an app with **more than one principal** must declare them, and loopback does not count
   as a boundary between principals on one machine. (F4, G4)
5. `stalled` and `seeded` apps are still installable and still show a privacy badge. Either gate
   installation on status or state that status is not a safety signal. (F2)

**Engineering, in value order:**

6. `tools/manifest_lint.py` in the `gates` job: enum'd `privacy_tier`, required `data_streams`,
   `permissions` from a registry (which also fixes the unlabelled permissions in `tui.py:51-70`). (G1)
7. `subjects` field in the manifest; render it as the **first** line of `ConsentModal`. (G2)
8. `rung` per `data_stream`, from `docs/homestead-rungs.md`; unclassified fails the build. (G2)
9. `vault_leak_lint`: AST-based extraction; `~/Desktop/*` writes are leaks; `UNKNOWN` fails
   `--strict` when the manifest declares persistence. (G3)
10. `vault_paths.app_dir`: drop the shared `APP_DATA` default. (G6)
11. `dating-wellbeing`: `age < 18` terminates; `age_gap_rationalize` → `danger`. (F2)
12. `utety-chat`: manifest corrected; the `chat-consent` line corrected; persona server-side. (F3)
13. `playgate`: parent token minted at startup, required on `/parent/*` and on answer. (F4)
14. `the-squirrel`: export defaults under the vault; living-person suppression by default; derived
    form in the Ollama context. (F5)
15. `nest-seed`: `owner` out of bridged atoms; category labels allowlisted before egress. (F6)
16. `UTETY-Reddit-Bots`: `PRIVACY.md` matches `flair.ts`, or `flair.ts` goes; `DEBUG_MODE` off by
    default. (F7)
17. Delete `SAFESession` from the six apps that never call it. (F8)
18. `bureau-differential` into `test.needs`. (G8)

---

## Tensions, named rather than resolved

**Easy to ship versus safe to ship.** The store's floor today is: a manifest exists and its `app_id`
matches the folder. That is why 34 apps exist. Every recommendation in G1/G2 raises the floor and
breaks three apps immediately. I recommend raising it — but the cost is real and lands on a
single-author store where friction may simply mean fewer apps.

**Playful apps for children versus data minimisation.** `band-camp-arcade` and `civics-check` are
delightful *because* they store a best time and a bingo card and ask for nothing. That is the model.
`utety-chat` is the counter-example: the pixel campus and the rotisserie-chicken dean are what make
it reachable by a child, and the same charm is what makes its `client_only` badge dangerous. A
children's app is not made safe by being small; it is made safe by being small **and saying so
where the child is**.

**Local-first versus recoverable.** `playgate`, `marching-arts` and `terpsi-chat` all take
local-first seriously — no export path, no server copy. That means a lost machine is a lost consent
chain and a lost disposition log, and for `marching-arts` the retention note is honest that youth-sector
limitation periods can run to majority-plus-years. Local-first and "the record must survive to the
child's majority" pull opposite ways, and this store has not chosen.

**Manifest honesty is cultural, not enforced.** `marching-arts` and `jarvis` have the best manifests
I have read anywhere, and `utety-chat` has one of the worst — and the store's gates cannot tell them
apart. Every good manifest here exists because its author chose to write it. That is a fragile place
to keep a safety property.

---

## Open questions

1. Is `utety.pages.dev` deployed and reachable now? I read `wrangler.toml`, `functions/` and
   `worker/` but made no network request. If it is live, F3 is live.
2. What is `apps/law-gazelle` doing with `~/.willow/apps/law-gazelle` (it is in the G3 cohort) — the
   other agent will know, and the cross-app question is whether that directory is shared with
   `the-binder`'s intake queue under a set `APP_DATA`.
3. Who writes `llmphysics-bot`'s `mod-digest` wiki page, and does it ever name a user?
4. Does `store_mcp.app_install` (Willow-side, outside this repo) do anything with the manifest, or is
   `tui.py`'s modal the whole of the consent enforcement? I could only see the client side.
5. `marching-arts`' retention question is explicitly open pending counsel, and the manifest is right
   that it is not an engineering call. It is the single most consequential open item for minors in
   this store, and it is blocked on a decision nobody in the repo can make.
6. Are the Reddit bots actually installed in any subreddit today? F7's severity is entirely a
   function of that.

---

*Sweep conducted 2026-08-04. Read-only; no repository file was modified.*
