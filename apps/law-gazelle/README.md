@markdownai

# Law Gazelle

**Local-first case command center** for private legal matter data.

Law Gazelle reads operator-provided case databases from Nest and surfaces an urgent queue, milestone tracker, document context, and sidecar state in a Textual TUI. It also exposes an MCP surface for local LLM legal sessions.

This public repository contains app code, tests, and synthetic examples only. Real case databases, exports, drafts, correspondence, and generated manifests must stay outside git.

### Privacy Gate

Keep private matter data in local-only locations:

| Location | Contents |
|----------|----------|
| `~/Desktop/Nest` | Canonical private case DBs, exports, drafts, and correspondence |
| `~/.willow/apps/law-gazelle/` | Local app state (`gazelle_state.db`, activity, AI cache) |
| `apps/law-gazelle/private/` | Optional local-only case files (gitignored) |

Before publishing, run a PII/secret scan and confirm repo history contains only code, tests, docs, and demo/synthetic data.

---

## Demo Matter Types

| Matter | Demo ID | Status |
|--------|---------|--------|
| Co-parent / family law | D-000-DM-0000-00000 | Synthetic demo |
| Bankruptcy | BK-0000-DEMO | Synthetic demo |
| Workers' comp | WCA 00-00000 | Synthetic demo |

---

## Layer Model

```text
Nest SQLite (canonical private data) -> Law Gazelle (reads only) -> LLM / TUI
                                           |
                                           v
                               gazelle_state.db (sidecar writes only)
```

Nest stays canonical. Law Gazelle only writes sidecar state, explicit drafts, and commit manifests.

---

## Run

```bash
cd apps/law-gazelle && ./dev.sh
```

| Key | Action |
|-----|--------|
| Enter / v | Detail modal |
| r | Refresh (re-sync from Nest) |
| d | Mark done -> sidecar |
| n | Add note -> sidecar |
| s | Snooze -> sidecar |
| u | Toggle show resolved |
| o | Open artifact (Session tab) |
| q | Quit |

---

## Session-End Ritual

At the end of a legal build session, commit the local Nest package:

```bash
python3 scripts/commit_package.py --summary "Session summary; case DBs/export/drafts ready for watcher"
```

This writes `legal_commit_<date>.json` to `~/Desktop/Nest/`. The Nest watcher can pick it up and alert the fleet.

---

## LLM / MCP Surface

Add `law-gazelle` to your `.mcp.json`:

```json
{
  "mcpServers": {
    "law-gazelle": {
      "command": "python3",
      "args": ["/path/to/law-gazelle/gazelle_mcp.py"]
    }
  }
}
```

Tools: `gazelle_sync`, `gazelle_briefing`, `gazelle_urgent`, `gazelle_detail`, `gazelle_note`, `gazelle_resolve`

Typical session flow:

```text
gazelle_sync()
gazelle_briefing()
gazelle_detail("coparent", "atom", "ATM-001")
gazelle_note("coparent", "atom", "ATM-001", "Confirmed deadline against source document")
```

Agent write path: sidecar only. Nest remains canonical.

---

## Deadlines

Deadlines are read from local case data, especially `coparent_db_export.json` `_meta.response_deadlines`. The public repo should not hardcode real deadlines or legal timeline facts.

---

## What This Is Not

- Not a generic legal template engine (`src/gazelle_engine.py` is archived)
- Not a Postgres-backed tool (`legal_db.py` is archived)
- Not a LOAM ingest tool; indexing and promotion happen downstream of the Nest watcher
