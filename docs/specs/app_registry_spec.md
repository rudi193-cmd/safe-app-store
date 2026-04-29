# App Registry — Postgres Schema + SAP Gate Integration
**Date:** 2026-04-27 | **Status:** Draft | **b17:** SAPS1
**For:** Hanuman / willow-1.9 implementation

## What This Is

Apps in the SAFE ecosystem are independent. Users choose what to install and what to connect.
The app registry is the source of truth for what's installed, what permissions the user granted,
and which cross-app connections are authorized.

This replaces the file-based permission cache (`~/.willow/permissions/<app>.json`) with a
Postgres-first model that persists across machines (when synced) and is queryable by the SAP gate.

---

## Schema

### `sap.installed_apps`

```sql
CREATE TABLE IF NOT EXISTS sap.installed_apps (
    app_id          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '0.0.0',
    installed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent_id        TEXT,                    -- agent identity if app has one (e.g. 'vishwakarma')
    permissions     JSONB NOT NULL DEFAULT '[]'::jsonb,
                                             -- array of granted permission strings
                                             -- e.g. ["store_read","store_write","store_add_edge"]
    b17             TEXT,
    manifest_hash   TEXT                     -- sha256 of safe-app-manifest.json at install time
);
```

### `sap.app_connections`

Cross-app permissions are explicit and directional. The reading app declares intent;
the exposing app declares availability; the user approves the connection.

```sql
CREATE TABLE IF NOT EXISTS sap.app_connections (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_app_id     TEXT NOT NULL REFERENCES sap.installed_apps(app_id) ON DELETE CASCADE,
    to_app_id       TEXT NOT NULL REFERENCES sap.installed_apps(app_id) ON DELETE CASCADE,
    scope_path      TEXT NOT NULL,           -- what from_app can access in to_app's namespace
                                             -- e.g. 'user-{uuid}/story-timeline/atoms/'
    access          TEXT NOT NULL DEFAULT 'read' CHECK (access IN ('read')),
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by      TEXT NOT NULL DEFAULT 'user',
    UNIQUE (from_app_id, to_app_id, scope_path)
);
```

---

## SAP Gate Changes (willow-1.9 core)

The SAP gate (`sap/gate.py` or equivalent) must check `sap.installed_apps` and
`sap.app_connections` on every cross-namespace store access.

### Authorization logic

```python
def authorized_cross_app(requesting_app_id: str, target_collection: str, access: str) -> bool:
    """
    Returns True if requesting_app_id has an approved connection to the collection.
    Checks sap.app_connections — no match = denied.
    """
    # Resolve target app from collection path (e.g. user-*/story-timeline/* -> story-timeline)
    target_app_id = _parse_app_id_from_collection(target_collection)
    if target_app_id == requesting_app_id:
        return True  # own namespace, always allowed

    row = db.fetchone("""
        SELECT id FROM sap.app_connections
        WHERE from_app_id = %s
          AND to_app_id = %s
          AND access = %s
          AND scope_path_matches(%s, scope_path)
    """, (requesting_app_id, target_app_id, access, target_collection))
    return row is not None
```

### `scope_path_matches(collection, pattern)` — Postgres function

```sql
CREATE OR REPLACE FUNCTION sap.scope_path_matches(collection TEXT, pattern TEXT)
RETURNS BOOLEAN AS $$
    -- pattern uses {uuid} as wildcard, e.g. 'user-{uuid}/story-timeline/atoms/'
    SELECT collection LIKE replace(replace(pattern, '{uuid}', '%'), '/', '/');
$$ LANGUAGE SQL IMMUTABLE;
```

---

## Install Flow

When a user runs an app for the first time:

1. App reads its `safe-app-manifest.json`
2. App calls `sap.register(app_id, permissions, manifest_hash)` — upserts into `installed_apps`
3. For each entry in `reads_from`: app calls `sap.request_connection(from=self, to=target_app, scope, purpose)`
4. SAP presents consent prompt to user (terminal or UI)
5. On approval: inserts into `app_connections`
6. On denial: app degrades gracefully (no connection row written)

---

## Connection Request Prompt (terminal)

```
The Binder wants to read your Story Timeline writing summaries.
  Purpose: "Surface connections between filing patterns and narrative work"
  Scope: user-{uuid}/story-timeline/atoms/ (read-only)

Allow? [y/N]
```

---

## What Each App Needs (implementation checklist)

- [ ] willow-1.9: create `sap` schema, `installed_apps` + `app_connections` tables (migration)
- [ ] willow-1.9: implement `sap.register()`, `sap.request_connection()`, `sap.authorized_cross_app()`
- [ ] SAP gate: check `app_connections` on cross-namespace store calls
- [ ] Each app: call `sap.register()` on first run (already done for story-timeline via `safe_integration.py`)
- [ ] story-timeline: declare `reads_from: {}` in manifest (done ✓)
- [ ] The Binder: when built, declare `reads_from: {"story-timeline": {...}}` if cross-app read wanted

## Update to Cross-App SAP Spec

`docs/specs/cross_app_sap_spec.md` described `~/.willow/permissions/<app>.json` as the cache.
**Superseded:** Postgres `sap.app_connections` is the source of truth. The file cache is removed.
The approval prompt is now gated on a Postgres write, not a file write.

---

## Notes

- `agent_id` in `installed_apps` enables agent-to-app binding. If Vishwakarma (agent) manages
  story-timeline (app), the row would have `agent_id = 'vishwakarma'`. This lets the system
  know which agent is responsible for a given app's namespace.
- The `scope_path` in `app_connections` uses `{uuid}` as a literal placeholder — the gate
  substitutes the current user's UUID at authorization time.
- No wildcards beyond `{uuid}` — apps cannot declare open-ended cross-app read access.

ΔΣ=42
