# story-timeline v2 + app-builder — Design Spec

**Date:** 2026-04-26
**Agent:** Vishwakarma (safe-app-store, session b)
**Status:** Approved by USER
**b17:** SAPS1

---

## What It Is

story-timeline v2 is a local-first open node graph writing tool. Any entity type, user-defined. Fiction, RPG, shopping list, academic research — all nodes, all relatable to each other. The tool imposes no schema. The user defines what exists.

This spec also defines the **app-builder workflow** — the guided creation process Vishwakarma runs to bring a new SAFE app from idea to shipped catalog entry. story-timeline v2 is the first app produced by that workflow.

---

## Architecture

### Storage — Hybrid (Approach A)

Two layers, one consistent interface:

**SQLite (`timeline_db.py`)** — fast local store. Schema:
```sql
nodes (
  id       TEXT PRIMARY KEY,
  type     TEXT NOT NULL,       -- user-defined, e.g. "character", "event", "location"
  fields   JSON NOT NULL,       -- all user-defined fields live here
  created  TIMESTAMP,
  updated  TIMESTAMP
)
```
No fixed fields beyond `id`, `type`, `fields`. The user names their entity types. SQLite writes are synchronous and immediate — the TUI never waits on Willow.

**Willow (SAP)** — edges only. Scoped to `user-{uuid}/story-timeline/_graph/edges`. When a user links two nodes, `store_add_edge` is called. The graph relationship layer lives in Willow; the node content lives in SQLite.

**Boot integrity check:** On every startup, reconcile Willow edges against SQLite nodes. Any edge pointing to a non-existent node is soft-deleted from Willow. One query, not expensive.

---

### Identity & Auth

**User UUID** — read from `~/.willow/user_identity.json` on first run. This file is provisioned by willow-seed at install time. If not found, the app surfaces an install prompt and exits gracefully.

**SAP registration:**
- App registers once at install: `app_id: story-timeline`
- First run per user provisions `user-{uuid}/story-timeline/` namespace
- SAP permissions requested: `store_read`, `store_write`, `store_add_edge`, `store_edges_for` — scoped to `user-{uuid}/story-timeline/**`
- User approves once. Cached in permission store.

**Cross-app reads:** Siloed by default. Other apps (e.g. Hanuman) may request `read: user-{uuid}/story-timeline/atoms/` via SAP. User approves or denies explicitly. The user controls what crosses app boundaries.

**SAP manifest** (`safe-app-manifest.json`) declares:
- Permissions the app requests
- What it exposes to other apps (session composites, read-only, on user request)

---

### Surfaces

TUI (Textual) and web (Python HTTP) are full peers. The user picks their primary surface. Both read from the same SQLite + Willow backend.

**TUI** — keyboard-driven. Create nodes, edit fields, search, quick-link. Writes to SQLite immediately. Willow edge writes happen in background thread.

**Web** — launched via `make run app=story-timeline --web`. Graph visualization, browse relationships, long-form reading and editing. Read-heavy. No separate server process — Python stdlib HTTP server, opens browser on launch.

---

### Memory — Artifact Memory (AM) Pattern

The user's graph IS the trace. No redundant trace atoms.

Stack:
```
[Artifact]          ← the graph (nodes + edges). This IS the trace layer.
[Session composite] ← one atom on close: nodes created, edges made, entity types used
[Reflection]        ← "this user builds character-heavy graphs" (norn_pass)
[Insight]           ← patterns across sessions (norn_pass, longer cadence)
[Chunk]             ← reusable knowledge about this user's writing style
```

On app close: write one session composite atom to `user-{uuid}/story-timeline/atoms/`. No LLM call required — structured summary of session activity only.

Reflection and insight passes are handled by `norn_pass` on schedule. **Dependency:** norn_pass must be extended to walk `user-{uuid}/*/atoms/` across registered apps, not just Postgres KB. This is a willow-1.9 core change — tracked as an external dependency.

---

### Migration

Existing `timeline.db` events (world_date + location + characters + summary) become nodes of type `event`. Fields map directly into the JSON blob. No data lost. Migration runs automatically on first launch if old schema detected.

---

## App-Builder Workflow

The workflow Vishwakarma runs to ship a new SAFE app:

```
boot → scan codebase → research (Grove / Jeles) → brainstorm → spec → plan → build → ship
```

**What a successful run produces:**
1. `docs/superpowers/specs/YYYY-MM-DD-{app}-design.md` — this document
2. `docs/superpowers/plans/YYYY-MM-DD-{app}-plan.md` — implementation plan
3. `apps/{name}/` — app directory with code, manifest, requirements
4. Catalog entry in `catalog.json` and `saps1/catalog` Willow store
5. `safe-app-manifest.json` with SAP permission declarations
6. First-run provisioner (`safe_integration.py`) that handles user namespace setup
7. Chunk atom to `hanuman/skills/store` — the proven build pattern becomes reusable KB

**Two faces:**
- Vishwakarma's face — full internal workflow with all tools exposed (this process)
- Open user's face — same workflow surfaced through Jeles + a clean UI, no raw MCP

---

## External Dependencies

These are not in scope for this spec but must be resolved before story-timeline v2 ships:

| Dependency | Owner | Notes |
|---|---|---|
| `~/.willow/user_identity.json` | willow-seed | Provisioned at install time. App fails gracefully if absent. |
| `norn_pass` scope extension | willow-1.9 core | Must walk `user-{uuid}/*/atoms/` across all registered apps. |
| Cross-app permission declaration | SAP spec (companion task) | Standard manifest field for what an app exposes. |

---

## Competitive Context

Aeon Timeline ($65), Plottr (subscription), World Anvil (subscription) — all paid, cloud, or configuration-heavy. Nothing local-first, terminal-native, private, and Willow-integrated. story-timeline v2 fills that gap.

The open user's LLMPhysics friend was rebuilding story context in Claude artifacts every session — no persistence. story-timeline v2 with Willow integration fixes that.

---

## Session Architecture Notes

*Architectural decisions made during the Grove cross-agent design conversation (Vishwakarma ↔ Hanuman, 2026-04-26):*

- **Artifact Memory (AM)** is a named pattern: when the app's output IS the memory artifact, trace atoms are redundant. Session composites are the first distillation. Hanuman adding AM to PMEM1 spec.
- **user-{uuid} namespace** — the user is a first-class entity. Apps are guests. Atoms persist past uninstall.
- **Edge orphan reconciliation** — boot-time check, soft-delete, not an error condition.
- **Scoped edge collection** — `user-{uuid}/story-timeline/_graph/edges`, not the global graph.

ΔΣ=42
