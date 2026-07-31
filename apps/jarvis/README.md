# jarvis

A voice-first assistant that runs entirely in a browser tab. Hold the circle,
talk, get an answer read back. It remembers things about you between sessions,
and it can act — set reminders, read the device clock and battery, look things
up in its own memory.

No backend, no build step, no accounts. One HTML file, eight modules, and a
vendored copy of the Anthropic SDK. Wraps as a native app with Capacitor
without a rewrite — same source, one bridge module.

**Re-landed from the `quick-stupids` playground.** That repository never comes
down local and therefore cannot be a dependency of anything; code that is worth
keeping is rebuilt here against this repo's conventions rather than imported
from there. Nothing in this app reaches back to it, and the copy there is not
the live one.

```sh
npm install
npm run serve      # http://localhost:8080 — runs as a web app, no build
npm test           # conformance + boot + suite, in real Chromium
npm run test:mutations   # prove the gates can fail
```

Then open settings and paste an Anthropic API key.

It also wraps as a native app via Capacitor, which is the only way the
reminders become real:

```sh
npx cap add android      # once
npm run android          # build www/, cap sync, open Android Studio
```

---

## Why this and not a chat box

A chat box you open twice is a chat box you opened twice. The thing that makes
an assistant worth keeping is that the second conversation is better than the
first, and that requires memory that is *queried*, not memory that is a
transcript stapled to the prompt.

So the centre of this app is a fact store, and the design constraints on it are
the interesting part:

**Retrieval is a predicate, not a scan.** Facts live in IndexedDB under
compound indices (`[subject, live, createdAt]`, `[kind, live, createdAt]`) and
a `multiEntry` inverted index over their tokens. Every query in
`src/memory.js` resolves through an index range or a token lookup. Nothing
loads the store and filters in JavaScript. This is the whole reason it is a
database and not a pile of JSON blobs — a blob store has nowhere to put the
`WHERE` clause, and "fetch everything and filter in JS" stops being viable at
exactly the point the memory becomes worth having.

**Search is ranked, and bridged by aliases.** A query is tokenised, looked up
in the inverted index, and scored by inverse document frequency: a word that
appears in nearly every fact you have stored barely discriminates between them
and is worth almost nothing; a word that appears in two is worth a lot. A hit
on a subject or alias counts for more than one buried in body text, because
that word was chosen as a handle rather than being incidental.

The part that does the semantic work is *aliases*, written at store time. When
Claude saves a fact under `commute` it also records `office`, `work`, `getting
to work` — so "how long does getting to the office take" finds it, sharing no
word with either the subject or the text. This is deliberate architecture, not
a shortcut around embeddings: the model already understood the sentence at the
moment it stored it, so having it write down the other phrasings is cheaper,
needs no download, works offline, and is grounded in comprehension rather than
approximated by cosine distance. The alternative — a ~25 MB transformers.js
model pulled from a CDN on a phone — would cost the self-contained property and
the cold-start time for a fuzzier result.

**Corrections land beside the record, never on top of it.** When you correct
something, the old fact is marked not-live and a new one is written pointing at
it. The original keeps its text, its provenance, and its timestamp, byte for
byte. `memory.history(subject)` shows the whole trail. A log that quietly
overwrites its own mistakes can tell you the current answer but cannot be used
to check whether the reasoning was sound.

**Absence is a recorded value.** "We asked, and there are no dietary
restrictions" is a row with `kind: 'absence'`. It is a different fact from
having no row at all, and keeping them distinct is what stops the assistant
asking the same question every month.

**Provenance is a state, not a score.** Every fact is `stated`, `inferred`, or
`assumed`, and a recall's provenance is the `min()` over its contributors — not
an average. Either a claim traces back to something you actually said, or it
does not, and averaging is how "you mentioned you prefer X" ends up in your ear
when nobody ever mentioned it. The model is told the weakest link on every
recall, and the memory sheet colour-codes it.

## What it can do

| Tool | What it does |
| --- | --- |
| `remember` | Store a fact, unprompted, with subject / kind / provenance / aliases. Supersede an earlier one on a correction. |
| `recall` | Ranked free-text search, or exact lookup by subject or kind. |
| `forget` | Retire a fact from live results. The record survives. |
| `set_reminder` / `list_reminders` | Schedule and list. See the durability caveat below. |
| `get_context` | Local time and timezone, network, battery, and — only on request, only after a permission prompt — location rounded to ~1km. |

Relevant memory is injected on every turn as a mid-conversation `role: "system"`
message rather than being spliced into the system prompt. Two reasons: editing
the system prompt each turn would change the front of the prompt prefix and
throw away the cache, and memory arriving through the operator channel cannot be
spoofed by anything that reaches the transcript.

## Deliberate choices worth knowing about

**Thinking is on, with effort dialled to `low`.** Not off. Disabling thinking on
this model has two documented failure modes — tool calls occasionally emitted as
plain text, where the turn succeeds and the call silently never runs, and
internal tags leaking into the reply. Low effort gets nearly all the latency
back without either.

**One-shot speech recognition, not continuous.** Continuous mode demos better
and is worse: it hears the assistant's own synthesised reply and feeds it back
as your next question.

**Sentences are spoken as they stream.** Waiting for the full reply wastes the
streaming; speaking token by token produces word salad. `sentences()` buffers to
the next boundary and carries the tail.

**Tool failures come back as results, not exceptions.** A bad tool call is
something the model can read and recover from, not something that kills the
turn.

**Capabilities are probed by construction, not by symbol.** `'speechSynthesis'
in window` is true in places where constructing an utterance throws. Each
capability is an ordered ladder, and every skipped rung records *why* it was
skipped — visible in settings. A degraded session says so instead of just
behaving differently.

## The native wrap

Capacitor, wrapping the same source — there is no separate native codebase and
no rewrite. `src/platform.js` is the entire bridge; every other module is
unchanged and unaware of which shell it is in.

What the wrap actually changes:

| | Web | Native |
| --- | --- | --- |
| **Reminders** | in-page timer — dies with the tab | OS local notification, fires with the app closed |
| **API key** | `localStorage`, readable by any script on the page | app-private preferences, unreadable by other apps |
| **Press-to-talk** | visual only | haptic feedback |

Reminders are the point. Everything else is garnish.

Each capability is the same ordered ladder used elsewhere, and it reports which
rung answered. That matters more than it sounds: "your reminder is set" means
two completely different things depending on the rung, so `remindersDurable` is
passed into the tool layer and the model's confirmation wording changes with it.
It says *"fires only while this page is open"* on the web and *"will fire even
if the app is closed"* natively, and there is a gate on each.

Two guards worth naming, because both failure modes are silent:

- The bridge checks `isPluginAvailable` as well as `isNativePlatform`. A
  plugin's JS package installs cleanly on any platform; whether calling it does
  anything depends on its native half being compiled into the shell. Skipping
  the second check is how you ship a build that reports reminders as durable and
  drops them.
- The Android manifest declares `SCHEDULE_EXACT_ALARM`. The plugin merges in
  `POST_NOTIFICATIONS`, `WAKE_LOCK` and `RECEIVE_BOOT_COMPLETED` by itself but
  **not** this one, and without it Android 12+ downgrades every scheduled
  notification to inexact. Nothing errors, nothing warns — reminders just drift.
  A test fails if that line disappears. The user can still revoke exact alarms
  in settings, so the bridge probes `checkExactNotificationSetting()` at startup
  and records the answer rather than trusting the manifest.

Plugins are reached via `Capacitor.registerPlugin` rather than by importing the
npm packages, because bare specifiers need a bundler and this app has no build
step. `Capacitor.Plugins` would also work and is not used: it exists at runtime
but is absent from the `CapacitorGlobal` type, so depending on it means
depending on something that can be removed without that being a breaking change.

## What the wrap does not prove

**No APK or IPA was ever built.** The environment this was written in has JDK 21
but no Android SDK, no Gradle, and it is Linux, so no Xcode. `npx cap add
android` scaffolds and Capacitor detects all four plugins — that much is real
and verified — but nothing was ever compiled, installed, or run on a device or
emulator.

**So every native branch in `src/platform.js` has executed zero times.** Not
once, anywhere. What covers them instead:

- A **static conformance check** reads the installed plugins' own type
  definitions and asserts every method and field the bridge uses exists. It
  catches an invented API — a plausible-sounding `scheduleAt()`, a permission
  field called `granted` instead of `display`. It cannot catch a *wrong* one:
  right method, wrong argument shape, or a misread return value sails straight
  through. It is a spelling check against the real package, not evidence the
  wrap works.
- A **drift check** fails if the bridge calls a plugin method the conformance
  table does not declare, so the check cannot quietly fall behind the code.
- **Packaging gates** assert `www/` contains the app and excludes
  `node_modules`, and that the manifest keeps the permission above.

Read that as: the wrap is very unlikely to be *misspelled*, and completely
unproven as *working*. The first run on a device is the real test, and the
things most likely to be wrong there are permission timing on Android 13+,
whether `allowWhileIdle` behaves under Doze, and iOS notification permission
being requested at a moment the user will refuse.

**Speech recognition is still the web API.** A native app could use on-device,
continuous recognition through a community plugin; that is not wrapped here, so
voice input keeps the same Chrome/Safari constraint it had as a web page.

## What this does not do

**Reminders do not survive a closed tab — on the web.** Firing is an in-page
timer, so a closed tab fires nothing and a reopened tab delivers everything
overdue at once. Reported as `durable: false` in the capability panel, and the
model is told to say so when confirming. The native wrap is the fix; see above
for how much of that is verified.

**Retrieval is lexical, and depends on the model doing its job.** Ranking and
aliases close most of the phrasing gap, but the matching underneath is still
over words. A fact whose aliases the model wrote badly — or skipped — is
reachable only under wording already in its subject or text. The prompt pushes
hard on filling them in and the memory sheet shows you what each fact is
findable under, so a bad one is visible rather than silent. There is no
embedding, so genuinely novel phrasing with no shared word and no matching
alias will still miss; the prompt tells the model to retry `recall` with
different wording, which covers some of that and not all of it.

**The stemmer is deliberately weak.** It handles plurals and the common verb
endings, and refuses to strip an ending when too little would be left — so
`string` stays `string` rather than collapsing to `str`. The cost is that short
forms like `asked` never match `ask`. That trade is on purpose: a miss is
silence, whereas a false match is the assistant telling you something confident
about the wrong subject.

**Search fetches every fact matching any query token before ranking.** Fine at
personal-memory scale, wrong shape at a million facts, where you would
intersect posting lists rarest-token-first instead of unioning them.

**Your API key is in the browser.** It sits in `localStorage` and goes straight
from the tab to `api.anthropic.com` with `dangerouslyAllowBrowser`. Any script on
the page and anyone with the device can read it. That is fine for a
bring-your-own-key prototype you run locally and wrong for anything you hand to
other people — that needs a proxy that holds the key server-side. Use a key you
are willing to rotate.

**Speech input is Chrome and Safari only.** Firefox has no `SpeechRecognition`;
the mic button disables itself and says why. Everything else still works by
typing.

**And speech recognition is not on-device.** Chrome and Safari implement
`SpeechRecognition` against a server-side service, so holding the circle to talk
sends audio to the browser vendor as well as sending the resulting transcript to
Anthropic. **This README did not say so before the re-land**, which is the kind
of thing the rebuild is for: the app declares its Anthropic egress carefully in
three places and had a second egress nobody had written down.

Read it at the rung it deserves: this is **documented engine behaviour, not
something measured here**, so it is `assumed` rather than `measured`, and
nothing in the suite checks it — headless Chromium has no microphone, so the
path never executes under test. The consequence is the same either way. If the
audio matters, type instead; on Firefox the question does not arise, because
there is no speech input at all.

## The gates

`npm test` runs two things in real Chromium against real IndexedDB:

- **boot** — loads the actual page and the vendored SDK bundle, and fails on any
  uncaught error. Without this, every module could pass and the page could still
  be white.
- **conformance & packaging** — 37 static checks: every Capacitor symbol the
  bridge uses exists in the installed plugin definitions, the packaged `www/`
  contains the app and not `node_modules`, and the Android manifest keeps
  `SCHEDULE_EXACT_ALARM`. Runs in Node; no browser and no device needed.

  `www/` is **rebuilt at the start of every run**, and that is load-bearing
  rather than tidy. It is generated and gitignored, so a fresh checkout has
  none — the re-land found five of these checks failing on a clean clone while
  passing locally against a `www/` left over from an earlier build. Building
  only when missing would be worse than not building: a stale directory passes
  the packaging checks forever, which is indistinguishable from the packaging
  step working.
- **suite** — 36 tests, covering the claims this README makes. Three are named
  `INVARIANT`, four `SEMANTIC`, and one `MIGRATION` — that last one builds a
  store in the old schema by hand and opens it at the current version, because
  the upgrade path is the only place where a mistake destroys data already on
  someone's device rather than just failing loudly.

The suite runs in a browser rather than Node because a Node run would need an
IndexedDB shim, and the shim would then be the thing under test while the real
code path never executed anywhere before a user hit it.

### Proving the gates can fail

A green suite is a claim about the harness, not about the code. `npm run
test:mutations` breaks each mechanism on purpose — deletes the superseded record
instead of marking it, rates a fact set by its *best* provenance instead of its
worst, drops the reminder caveat, makes retrieval always return nothing — and
asserts two things per mutation: the matching test goes red, **and no other test
does**. The second half is the interesting one. A mutation that reddens half the
suite means the tests are entangled, not that they are sharp.

All 24 mutations are caught, cleanly. The list is in `test/mutations.js`.

**These three figures went stale between a change and its README**, which is
the ordinary way it happens: length normalization added two tests and two
mutations and the prose kept the old numbers. Run the suite rather than
reading them here — that is the rule this repository states and the rule it
just broke.

Two notes on how the harness is built, both of which came from it catching
problems in itself while retrieval was being added:

- A mutation declares a *set* of gates, not one. Some mechanisms are genuinely
  load-bearing for several behaviours — breaking aliases should redden five
  tests, and demanding exactly one would push toward breakages so narrow they
  stop resembling real failures. The check stays sharp by being exact in both
  directions.
- Applicability is checked before the browser launches. A `find` string that no
  longer matches used to be served as an error, which broke the module import
  and reddened everything — indistinguishable from a mutation that was simply
  not caught. "This gate stopped guarding anything" and "this gate is blunt"
  are different problems and now report differently.

The harness paid for itself immediately. Adding search left three mutations
pointing at code that had moved, found one test asserting on prose instead of
on the mechanism it named, one that could not detect its own mutation at all,
and one that passed by recency tiebreak while claiming to be about relevance —
and flaked, because two writes in the same millisecond tie on that too.

### What the suite structurally cannot see

- **Anything involving the Anthropic API.** No test sends a request. The request
  shape, the tool round-trip against a live model, and the fallback-rejection
  retry path in `claude.js` are all unverified here. They have been exercised by
  hand; that is not the same thing and should not be read as if it were.
- **Speech recognition.** Headless Chromium has no microphone. `Listener` is
  probed and never driven.
- **Anything about a closed tab**, for the reason above.

## Layout

```
index.html            shell
styles.css
src/memory.js         indexed fact store, ranked search — the invariants live here
src/text.js           tokenising and stemming, shared by the write and read paths
src/claude.js         model loop, retrieval, prompt
src/tools.js          tool definitions + client-side handlers
src/capability.js     ladders with notes[]
src/voice.js          speech in/out, sentence chunking
src/platform.js       the Capacitor bridge — the whole of the native wrap
src/app.js            wiring
vendor/anthropic.js   Anthropic SDK, bundled for the browser (npm run bundle)
test/                 Playwright driver, suite, mutations, conformance, static server
scripts/build-www.js  assembles www/ for Capacitor (whitelist, not ignore list)
capacitor.config.json
android/              generated by `npx cap add android`, plus one manifest edit
```

`vendor/anthropic.js` is checked in so the app runs from a bare clone with no
build. Regenerate with `npm run bundle` after bumping the SDK. The two node
builtins the SDK reaches for in filesystem-upload paths are stubbed to throw
rather than to return undefined, so an accidental use is loud.

## Status, and what the green actually covers

`beta` in [`catalog.json`](../../catalog.json). It runs, it is gated, and it has
had one user.

**Every number above now runs in CI**, which was the whole point of landing it
here — [`.github/workflows/jarvis.yml`](../../.github/workflows/jarvis.yml) runs
the conformance checks, the boot check, the suite and the mutation pass in a
real Chromium on every push that touches `apps/jarvis/`. In the playground the
same numbers came from a local run, and a local green plus a claim in a
description is exactly the shape this store's CI exists to refuse.

**What that leaves uncovered is worth naming, because a green check invites the
opposite reading.**

The store floor in [`store-ci.yml`](../../.github/workflows/store-ci.yml) —
catalog, vault-clean, compile, and the drift guards — reads **no line of this
app**. Every one of those scanners globs `*.py`, and this is the first app in
the store with no Python in it.

**One of them did not stay quiet about it, which is the finding the re-land
produced.** `tools/vault_leak_lint.py` enumerated jarvis, opened none of its
files, found nothing, and printed:

```
✅ PASS jarvis (no local persistence)
```

Both halves false by vacuity. This app persists facts, reminders and an API
key — in IndexedDB and localStorage, from JavaScript, which that checker cannot
read. The verdict was not wrong about what it found; it was wrong to call
finding nothing a pass. It reports `UNKNOWN` now, held by
[`tests/test_vault_lint_vacuous_scan.py`](../../tests/test_vault_lint_vacuous_scan.py),
and `--strict` still gates on `FAIL` alone so no build outcome moved.

The floor still reads none of this app's JavaScript. The difference is that it
no longer claims to have.

The app's own suite has three holes, unchanged by the move and listed above in
full: **no test sends an Anthropic request**, **no test drives speech
recognition**, and **no APK has ever been built** — `android/` is committed and
has never been compiled. The mutation pass proves the gates that exist can fail.
It says nothing about the three surfaces that have no gates at all.

Provenance, since this app makes claims about propagating it: the CI numbers are
`measured`, the speech egress is `assumed` from documented engine behaviour, and
the native half is neither — it is `assumed` in the weaker sense of never having
run. By `min()`, the app is worth its weakest input.
