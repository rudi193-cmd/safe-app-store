@markdownai v1.0

# Law Gazelle

**Case command center** for Sean Campbell's active legal matters.

Not a generic legal reference tool. This app reads canonical case databases from Nest and surfaces an urgent queue, milestone tracker, and sidecar state — all in a Textual TUI. It also exposes an MCP surface for LLM legal sessions.

---

## Cases

| Case | ID | Status |
|------|-----|--------|
| Co-Parent / Family Law | D-000-DM-0000-00000 | Active — Example County NM |
| Bankruptcy | Ch. 13 dismissed 2026-05-12 → Ch. 7 | Organizing |
| Workers' Comp | WCA 00-00000 | Active — NM WCA |

---

## Layer model

```
Nest SQLite (canonical)  →  Law Gazelle (reads only)  →  LLM / TUI
                                    ↓
                          gazelle_state.db (sidecar writes only)
```

Nest stays canonical. Law Gazelle never writes to Nest.

---

## Run

```bash
cd apps/law-gazelle && ./dev.sh
```

| Key | Action |
|-----|--------|
| Enter / v | Detail modal |
| r | Refresh (re-sync from Nest) |
| d | Mark done → sidecar |
| n | Add note → sidecar |
| s | Snooze → sidecar |
| u | Toggle show resolved |
| o | Open artifact (Session tab) |
| q | Quit |

---

## Session-end ritual

At the end of a legal build session, commit the Nest package:

```bash
python3 scripts/commit_package.py --summary "Letter sent; 21 atoms; deadlines May 30 / June 6"
```

This writes `legal_commit_<date>.json` to `~/Desktop/Nest/`. The nest_watcher picks it up and alerts `#heimdallr`.

---

## LLM / MCP surface

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

Typical legal session flow:
```
gazelle_sync()                          # refresh from Nest
gazelle_briefing()                      # orient: urgent + milestones + cross-case
gazelle_detail("coparent", "atom", "ATM-001")  # drill down
gazelle_note("coparent", "atom", "ATM-001", "Called court clerk — confirmed May 30 deadline")
```

Agent write path: sidecar only. Nest untouched.

---

## Deadlines (embedded in data)

| Date | Item |
|------|------|
| 2026-05-30 | Schedule response (letter) |
| 2026-06-06 | All other letter items |
| 2026-07-01 | City job / Ch7 filing / support modification |

---

## What this is not

- Not a generic legal template engine (`src/gazelle_engine.py` — archived)
- Not a Postgres-backed tool (`legal_db.py` — archived)
- Not a LOAM ingest tool — that's downstream of nest_watcher → fleet
