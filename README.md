# SAFE App Store

Local-first apps built on the SAFE framework. No ports. No servers. No subscriptions. Yours to keep, yours to delete.

> SAFE = Session-Authorized, Fully Explicit  
> App Store = browse, install, run — without giving anyone your data

## Apps

| App | Status | Description |
|-----|--------|-------------|
| [story-timeline](apps/story-timeline/) | beta | Narrative timeline tracker — free alternative to $70 timeline tools |

## Run any app

```bash
make run app=story-timeline
```

## Add an app to the store

1. Create `apps/<your-app>/` with `app.py`, `requirements.txt`, `safe-app-manifest.json`
2. Add entry to `catalog.json`
3. PR or push

## Architecture

Each app is a self-contained SAFE app — portless, local SQLite, no network required. The store is a monorepo. Each app deploys independently.

ΔΣ=42
