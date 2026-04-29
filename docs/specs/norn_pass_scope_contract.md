# norn_pass Scope Contract — story-timeline Interface
**Date:** 2026-04-27 | **Status:** Draft for Hanuman / willow-1.9 | **b17:** SAPS1

## Context

story-timeline v2 uses the Artifact Memory (AM) pattern:
- The graph (nodes + edges) IS the trace layer
- On session close, one `session_composite` atom is written to `user-{uuid}/story-timeline/atoms/`
- Reflection and insight passes run via norn_pass on schedule — not in the app

Currently norn_pass walks Postgres KB atoms (`willow_19`). Session composites live in
SOIL store (`user-{uuid}/story-timeline/atoms/`). This contract specifies what norn_pass
needs to do to support the AM pattern.

## Required norn_pass Changes (willow-1.9 core)

### 1. Accept a `collections` scope parameter

```python
norn_pass(collections=["user-*/story-timeline/atoms/"])
```

- `collections` is a list of glob-style SOIL collection paths to include in the pass
- If omitted, norn_pass runs only over Postgres KB atoms (current behavior — no regression)
- Glob patterns: `user-*` matches any user UUID, `*/story-timeline/*` matches any app

### 2. Walk `user-{uuid}/*/atoms/` across all registered apps

When `collections` includes user namespace patterns, norn_pass should:
1. Enumerate all matching SOIL collections via `WillowStore.list_collections(pattern)`
2. For each collection, load records of type `session_composite`
3. Run the existing reflection pass over them (ExpeL-style clustering, N≥3 threshold)
4. Write reflection atoms back to `user-{uuid}/<app>/atoms/reflections/`

### 3. Reflection atom format (what story-timeline produces)

Each `session_composite` written by story-timeline has this shape:

```json
{
  "id": "session-20260427T183000",
  "type": "session_composite",
  "app_id": "story-timeline",
  "user_uuid": "<uuid>",
  "created_at": "<iso>",
  "nodes_created": 5,
  "edges_made": 3,
  "entity_types_used": ["character", "event", "concept"],
  "duration_seconds": 1200
}
```

norn_pass reflection atoms derived from these should be written as:

```json
{
  "id": "reflection-story-timeline-<hash>",
  "type": "reflection",
  "source_app": "story-timeline",
  "user_uuid": "<uuid>",
  "created_at": "<iso>",
  "insight": "<plain language observation, e.g. 'User builds character-heavy graphs'>",
  "evidence_sessions": ["session-20260427T183000", ...]
}
```

## What story-timeline Does NOT Need

- norn_pass does not need to understand SQLite node schema
- norn_pass does not need direct access to `timeline.db`
- The graph itself is not processed — only the session composite atoms

## Scheduling

norn_pass with user namespace scope should run:
- On willow-seed's daily maintenance cron, OR
- Triggered by Kart when a new `session_composite` is written (if Kart event routing is built)

Not on app close — the app writes the composite and exits cleanly.

## Test Gate

Before shipping norn_pass scope extension, this test should pass:

```python
# Given: two session_composite atoms in user-test-uuid/story-timeline/atoms/
# When: norn_pass(collections=["user-*/story-timeline/atoms/"])
# Then: at least one reflection atom appears in user-test-uuid/story-timeline/atoms/reflections/
```

ΔΣ=42
