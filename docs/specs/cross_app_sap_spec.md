# Cross-App SAP Permission Spec
**Date:** 2026-04-27 | **Status:** Draft | **b17:** SAPS1

## Problem

Apps write to their own namespace (`user-{uuid}/<app>/`) by default. Cross-app reads require
explicit user approval — but no standard format exists for declaring what an app wants to read
or what it will expose.

## Spec

Every SAP manifest may include two optional top-level fields: `exposes` and `reads_from`.

### `exposes` — what this app makes available to others

```json
"exposes": {
  "<atom_type>": {
    "path": "user-{uuid}/<app>/<path>/",
    "access": "read",
    "requires_user_approval": true,
    "description": "Human-readable description of what this data is"
  }
}
```

- `access` is always `"read"` — apps expose data read-only
- `requires_user_approval: true` is mandatory — no silent cross-app reads
- `path` uses `{uuid}` as a placeholder; the runtime substitutes the current user's UUID

### `reads_from` — what this app wants to read from others

```json
"reads_from": {
  "<app_id>": {
    "atom_type": "<type>",
    "path": "user-{uuid}/<app>/<path>/",
    "purpose": "Why this app needs this data (shown to user at approval prompt)",
    "optional": true
  }
}
```

- `optional: true` means the app degrades gracefully if permission is denied
- `optional: false` means the app declares a hard dependency (unusual; avoid if possible)
- `purpose` is the string shown to the user at the approval prompt — write it in plain language

### Approval flow

1. On first access, the requesting app calls `sap.request_cross_app_read(app_id, atom_type)`
2. SAP gate presents the `purpose` string to the user
3. User approves or denies; decision is cached in `~/.willow/permissions/<requesting_app>.json`
4. Subsequent calls check the cache — no repeated prompts

### Runtime enforcement

- SAP gate rejects any `store_get` / `store_list` / `store_search` call where the collection
  path falls outside the requesting app's declared `sap_scope` **and** no cached approval exists
- Approved cross-app reads are scoped exactly to the declared `path` — no wildcards beyond what
  was approved

## story-timeline v2 manifest example

```json
"exposes": {
  "session_composite": {
    "path": "user-{uuid}/story-timeline/atoms/",
    "access": "read",
    "requires_user_approval": true,
    "description": "Session composite atoms — writing activity summary (nodes created, edges made, entity types used)"
  }
},
"reads_from": {}
```

story-timeline initially reads from no other app. A future integration (e.g. Hanuman reading
session composites for context) would add an entry to `reads_from` in Hanuman's manifest, not
here — the reader declares intent, the exposer declares availability.

## Dependencies

- willow-seed: implement SAP gate enforcement of `reads_from` / `exposes`
- willow-1.9: store `~/.willow/permissions/<app>.json` approval cache
- All apps: add `exposes` and `reads_from` fields to manifests (empty `{}` is valid)

ΔΣ=42
