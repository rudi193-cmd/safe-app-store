# Fleet paths — SAFE App Store & Law Gazelle

> **KB atom:** `1D1FD1F4` · **SOIL:** `saps1/paths-2026-06-21` · **Updated:** 2026-06-21

Agents: search KB for `safe-app-store symlink law-gazelle Nest APP_DATA`.

## Git checkout (one tree, two names)

| Path | Role |
|------|------|
| `~/github/safe-app-store-public` | Canonical git checkout (Cursor workspace) |
| `~/github/safe-app-store` | **Symlink** → `safe-app-store-public` |
| `~/github/safe-app-store.old` | Retired duplicate clone (optional delete) |

Fleet configs that reference `~/github/safe-app-store` still resolve correctly via the symlink.

**Willow store:** root `.mcp.json` sets `WILLOW_STORE_ROOT` to `safe-app-store-public/.willow/store`. App-level `.mcp.json` files may still say `safe-app-store` — equivalent through the symlink.

## Store console TUI (WIP)

| Item | Location |
|------|----------|
| Branch | `feat/store-console-tui` |
| Files | `tui.py`, `store_mcp.py`, `dev_tui.sh`, `VISION.md`, `_shot.py` |
| Run | `cd ~/github/safe-app-store && ./dev_tui.sh` |
| Runtime | `data/` at repo root (gitignored — logs, consent, screenshots) |
| Design spec | `docs/specs/store_console_design_spec.md` (SCDS1) |

## Law Gazelle — personal data (never in git)

Code lives in `apps/law-gazelle/`. **Case PII is outside the repo:**

| Layer | Path | Contents |
|-------|------|----------|
| **L1 Nest** | `~/Desktop/Nest/` | Canonical SQLite (`coparent.db`, `bankruptcy.db`, `workers_comp.db`), letters, drafts |
| **L2 sync** | `~/.willow/apps/law-gazelle/cases/` | Nest mirror + synced letter artifacts |
| **L3 sidecar** | `~/.willow/apps/law-gazelle/gazelle_state.db` | Resolutions, notes, fact verification, AI cache |

**Do not delete** Nest or `~/.willow/apps/law-gazelle/` when retiring git clones.

MCP: `gazelle_sync`, `gazelle_*` tools. Env: `NEST_SOURCE`, `APP_DATA` (defaults above).
