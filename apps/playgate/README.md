# playgate

**Nest Playgate** — a curated kid catalog and a parent gate that closes.

A child picks from a list an adult wrote. A parent grants or refuses, with a
reason either way, into a log that is never rewritten. A grant verifies the
APK's digest and installs it into Waydroid, and records what happened —
including, especially, when it fails.

```sh
python -m playgate serve --subject kid1 --subject kid2
# http://127.0.0.1:8424/kid/   ·   parent inbox at /parent/

python -m playgate lint            # what state is each entry's evidence in
python -m pytest tests/ -q         # 118 assertions, including 11 mutations
```

No third-party store, no ads, and no network beyond the loopback socket that
serves the two UIs to a browser on the same machine.

## Why there is an interruption record on every entry

The full argument is
[`docs/NOBODY_COUNTS_THE_AD_BREAKS.md`](docs/NOBODY_COUNTS_THE_AD_BREAKS.md),
the paper this app was built from. What follows is the short version.

The problem this app answers is not that children play games. It is that a
child looking for one gets routed through surfaces where the play button is
bait and the interruption is the product — and that no free, per-app source
exists to tell a parent how often a given app will stop their kid.

So every catalog entry carries one:

| Field | What it holds |
| --- | --- |
| `provenance` | `assumed`, `fitted`, or `measured`. Required. |
| `count_per_10min` | Stops per ten minutes of ordinary play. |
| `dismissal` | `immediate`, `after_delay`, `unskippable`, `deceptive_close`. |
| `observed_version` / `observed_at` / `observed_by` | What was watched, when, by whom. |

Four unweighted facts and **no composite score anywhere**. A single number
would be built from weights somebody picked, displayed, sorted on, and within
two releases optimised against — at which point it would measure compliance
with the scoring function instead of interruption, the same way time-on-app
stopped measuring enjoyment. The software reports what was observed; the parent
decides what it means.

### `assumed` is a value, not a blank

An app nobody has checked and an app measured at zero interruptions are
opposite facts. A catalog that renders them the same way has started lying
without anyone deciding to. So a missing record is a **load error**, not a
default — `catalog.load()` refuses the entry and names it.

**Every entry in `data/catalog.json` is `assumed`, and a test enforces that.**
Nobody has sat with a child and counted for any of them. Reaching `measured`
takes ten minutes, a child, and someone watching; there is no code path in here
that can produce it.

### Measurements decay on their own

Ad load is a tuning parameter. A count observed on 3.1 says nothing about 3.2,
so `Interruption.effective()` demotes a `measured` record to `fitted` the moment
the installed version stops matching the observed one. It falls to `fitted`
rather than `assumed` because the old count is still evidence about how these
people behave. Nobody has to remember to call it: the catalog view and the
disposition log both route through it.

## What the log holds

Append-only JSONL. Nothing in this app rewrites a line.

- **A reason is required to grant, not only to refuse.** Every app store logs
  installs; none of them logs why.
- **Refusals and expiries are rows.** "No row" means nobody ever asked, which
  is a different fact.
- **Expiry is derived on read, never written**, so an unanswered request cannot
  quietly become an answered one on disk.
- **Each answer snapshots the interruption evidence as it stood at that
  instant.** The catalog will change underneath it. A log holding only the
  current value can confirm the present state but cannot be used to ask whether
  the reasoning was sound.
- **Who asked comes from a roster, not a text box.** The host is started with
  an explicit `--subject` list. A consent log whose subject is a name the
  requester typed records an assertion, not an identity.

## Gates

In the `app-tests` matrix in `store-ci.yml`, so the suite runs on every pull
request.

| Suite | What it holds |
| --- | --- |
| `test_no_egress.py` | The core imports nothing network-shaped; `server.py` may import `urllib.parse` but not `urllib.request`; `serve()` refuses a non-loopback bind; the core pulls in no third-party package. |
| `test_interruption.py` | A missing record is an error, `assumed` may not carry a count, `measured` must be bound to a build and a date, demotion works and does not mutate, combination takes the floor rather than an average. |
| `test_disposition.py` | Reason required both ways, roster enforced, refusals and expiries recorded, no re-answering, history survives the fold. |
| `test_install.py` | Digest verified before adb is reached, an entry with no digest refused, a zero exit without `Success` still a failure, timeouts and `OSError` reported rather than raised. |
| `test_catalog.py` | An entry with no interruption field does not load; the view carries four facts and no score; the shipped catalog is all `assumed`. |
| `test_server.py` | Real loopback socket, real routes: ask, refuse, grant-and-install, and the traversal guard. |
| `test_paths.py` | Only `paths.py` imports the vault resolver; the four core modules choose no location at all; no module hardcodes a home or absolute persistence path; the log and APK dir resolve outside the install directory; env overrides still win; an unconfigured host refuses to install rather than searching itself. |
| `test_mutations.py` | Eleven mechanisms broken on purpose, each required to fail exactly the test that claims to cover it — plus a control run proving an unmutated copy passes. |

## What none of this can see

- **Whether Waydroid actually installs anything.** The adb path is exercised
  against an injected runner, and against a genuinely absent adb on the CI
  runner. It has never run against a real device in CI and cannot.
- **What an APK does at move five.** The digest proves the bytes on disk are
  the bytes an operator recorded. Everything above `fitted` needs a person and
  a clock, which does not scale — and the honest response to that is `assumed`
  on everything nobody has done, not a synthetic estimate wearing a measured
  badge.
- **The open web**, which is where the problem usually starts. This gates
  installed packages; a browser tab has no manifest, no version, and nothing to
  bind a measurement to. This is a supply-side fix: it makes the good path good
  enough to use, so there is less reason to go looking on the bad one.

## Where it writes

Everything resolves through the shared `libs/vault-paths` (installer design
D8) — never a home path, and never the app's own install directory.

| What | Default | Override |
| --- | --- | --- |
| Disposition log | `<vault>/playgate/requests.jsonl` | `PLAYGATE_LOG`, `--log` |
| Installable APKs | `<vault>/playgate/apks` | `PLAYGATE_APK_DIR`, `--apk-root` |
| Seed catalog | `data/catalog.json`, app-relative | `--catalog` |

The catalog is the one deliberately app-relative path: it is shipped content,
read-only at runtime, and replaced wholesale rather than written to. The log is
not — it records what a specific family's children asked for and what their
parents decided, and defaulting it beside the source would put it inside a
checkout, carry it into any copy of the app, and lose it on a reinstall.

`serve` prints both resolved locations at startup, because an operator should
be able to see where that record is actually going without reading this file.

Only `playgate/paths.py` imports the resolver, and `test_paths.py` enforces
that: `vault_root()` is a security boundary, so a second importer is a second
place for it to drift.

## Relation to the earlier prototype

An earlier host lived outside version control on the author's own machine. This
is a **rebuild** against this repo's conventions, not a copy — the two will
diverge, and this is the one under CI. The store copy previously shipped only
`kid/` and `parent/`, whose every `fetch()` went to that out-of-tree host; the
result was two directories that could not run and could not be tested.

License: Apache-2.0.
