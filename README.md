# SAFE App Store

Local-first apps built on the SAFE framework. No ports. No servers. No subscriptions. Yours to keep, yours to delete.

> SAFE = Session-Authorized, Fully Explicit  
> App Store = browse, install, run — without giving anyone your data

## Apps

41 apps in the catalog: 14 `gated`, 18 `building`, 6 `stalled`, 3 `archived`
(`make list` prints the live count and won't drift from this table the way
prose does). The `gated` ones below have a real, CI-verified test suite —
not a claim that they're feature-complete or polished:

| App | Description |
|-----|-------------|
| [ask-jeles](apps/ask-jeles/) | SAFE search engine — local stacks first, verified sources when you need the world |
| [band-camp-arcade](apps/band-camp-arcade/) | Five small local browser toys for marching band kids — no accounts, no network calls |
| [bureau](apps/bureau/) | A Bureaucracy homage at UTETY — a closed requirement graph and a deadlock proved by fixpoint |
| [civics-check](apps/civics-check/) | America's 250th civics quiz — naturalization test, timeline sort, quote matching, offline |
| [field-acoustics](apps/field-acoustics/) | Design-time acoustic model for marching drill — what the audience hears when the form turns |
| [jarvis](apps/jarvis/) | Voice-first browser assistant with an indexed, provenance-tracked fact store |
| [law-gazelle](apps/law-gazelle/) | Legal case management and document analysis |
| [marching-arts](apps/marching-arts/) | Authorization core for a marching-program platform — sealed grants, one compiled SQL predicate |
| [private-ledger](apps/private-ledger/) | Local-first private financial ledger — no cloud, no subscriptions |
| [source-trail](apps/source-trail/) | Track and audit data sources |
| [story-timeline](apps/story-timeline/) | Track events, characters, and locations across a narrative timeline |
| [terpsi-chat](apps/terpsi-chat/) | Schema and gates for messaging between under-18s in a youth-arts org |
| [the-squirrel](apps/the-squirrel/) | Genealogy companion — local-first, your tree stays in your tree |
| [utety-chat](apps/utety-chat/) | Chat with 11 AI faculty members, including Gerald (a headless rotisserie chicken) |

`building`, `stalled`, and `archived` apps (field-notes, njord, ratatosk,
the-forge, and 23 more) aren't listed here — they're real work, just not yet
past the CI-verified bar. See
[`.willow/store/catalog.json`](.willow/store/catalog.json) for the full
catalog — the root [`catalog.json`](catalog.json) is a pointer to it, not a
copy (`docs/store_refit_plan.md` P3) — or run `make list`. `docs/store_refit_plan.md`'s
status-vocabulary migration note has the full five-word enum
(`seeded · building · gated · stalled · archived`) and what each means.

## How the store works

Two tiers, and the difference isn't "tested" vs. "untested" — it's who's
answerable for the code:

- **Playground** — where every app above actually lives right now:
  `apps/<app>/`. Contested by default (`CLAUDE.md` §5), not yet a standing
  app. The house's only record of it is a **keeping record** at
  `stores/<major>/stored/<app_id>.json` — `majors`, `relation` (if it spans
  more than one craft), `location`, `maker`, `lane`, and `state` (the same
  five-word enum used for catalog `status`, above). The record is not a second
  copy of the code: **the code is not duplicated, the record is what
  `stores/` stores.**
- **Promoted** — a full SAFE app, in its own repo, held to the bar in
  `stores/promote_check.py`: every gate passing *and* verified by a hand
  other than the author's (proposing and ratifying never rest in the same
  hand). A promotion writes a record at
  `stores/<major>/promoted/<app_id>.json` — the verdict, every individual
  gate result, who verified it, and when. Nothing in `apps/` has cleared this
  bar yet.

`stores/` is organized **per major** — one home per craft: `python`, `node`,
`rust`, `go`, `cpp`, `obsidian`, `browser`. See
[`stores/README.md`](stores/README.md) for what each covers. A build that
spans more than one craft names all of them plus the `relation` holding them
together, so two implementations of one thing are never mistaken for an
unrelated pair (or the reverse).

Full reasoning, the migration history, and every open question:
[`docs/store_refit_plan.md`](docs/store_refit_plan.md).

## Run any app

```bash
make run app=story-timeline
```

`make run` does `cd apps/<app> && python app.py` — it works for any app whose
entry point is a top-level `app.py` (most of them). A few declare a different
`entry_point` in their manifest (e.g. `utety-chat`, `private-ledger`); check
`safe-app-manifest.json` for those and run them accordingly.

For local development with the existing dev environment:

```bash
cd apps/story-timeline
../../.venv-dev/bin/python3 app.py
```

## Add an app to the store

1. Create `apps/<your-app>/` with `app.py`, `requirements.txt`, `safe-app-manifest.json` — this is the playground (`CLAUDE.md` §5), a contested tier, not yet a standing app.
2. Add a catalog entry: `id`, `name`, `description`, `status`, `path`, `tags` in [`.willow/store/catalog.json`](.willow/store/catalog.json). Don't hand-write `tier`, `majors`, or `state` — those are generated from step 3 and `catalog_lint.py --strict` will reject them if they disagree with it.
3. Add a keeping record at `stores/<major>/stored/<your-app>.json` (`docs/store_refit_plan.md` P1) — `app_id`, `majors`, `location`, `maker`, `lane`, `state`. See any existing record under `stores/*/stored/` for the shape.
4. Run `python tools/catalog_lint.py --strict` before pushing — it checks steps 2 and 3 agree with each other and with `apps/`.
5. PR or push

## Architecture

Each app is a self-contained SAFE app — portless, local-first, and explicit about its permissions. Apps keep user data local by default; for example, Story Timeline stores nodes in `~/.willow/store/story-timeline/timeline.db` and only source code/docs belong in this repo.

The store is a monorepo. Each app deploys independently.

ΔΣ=42
