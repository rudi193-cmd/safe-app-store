# SAFE App Store

Local-first apps built on the SAFE framework. No ports. No servers. No subscriptions. Yours to keep, yours to delete.

> SAFE = Session-Authorized, Fully Explicit  
> App Store = browse, install, run — without giving anyone your data

## Apps

| App | Status | Description |
|-----|--------|-------------|
| [story-timeline](apps/story-timeline/) | beta | Literary knowledge base for books, authors, notes, projects, and their connections |
| [utety-chat](apps/utety-chat/) | stable | Chat with UTETY faculty personas |
| [ask-jeles](apps/ask-jeles/) | coming soon | Local-first search with verified sources when you need the world |
| [private-ledger](apps/private-ledger/) | beta | Local-first private financial ledger |
| [field-notes](apps/field-notes/) | beta | Plain-text field notes and observations |
| [law-gazelle](apps/law-gazelle/) | coming soon | Legal case management and document analysis |
| [civics-check](apps/civics-check/) | beta | America's 250th civics fair — naturalization test, pavilion quizzes, offline Python TUI |

See [`.willow/store/catalog.json`](.willow/store/catalog.json) for the full
catalog — the root [`catalog.json`](catalog.json) is a pointer to it, not a
copy (`docs/store_refit_plan.md` P3).

## Run any app

```bash
make run app=story-timeline
```

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
