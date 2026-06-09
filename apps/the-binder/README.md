# The Binder

**Your private knowledge engine. NotebookLM — local, offline, yours.**

Drop in notes. Add documents. The Binder finds what goes with what.

---

## What It Does

- **Knowledge atoms** — Drop in anything: notes, paste, URLs, files
- **Connection engine** — Kart (the AI) automatically surfaces what's related
- **The Ledger** — Named entities (people, places, projects) you've confirmed
- **Relationship graph** — Three-layer entity tracking: anonymous → recognized → named

## Architecture

The Binder is a skin on Kart. Kart does the connections. The relationship graph lives in `willow_knowledge.db`.

**Backend:** Willow server (`server.py`) — runs locally on your machine  
**Frontend:** `binder.html` — served from the Willow node  
**Database:** SQLite — `artifacts/{username}/willow_knowledge.db`

## Running It

```bash
# Start Willow node
cd C:\Users\USER\Documents\GitHub\Willow
python server.py

# Open The Binder
# Navigate to http://localhost:8420/binder
```

## SAFE Integration

- All knowledge stays local (SQLite, your machine)
- Session consent model: the graph is permanent (you built it), session context is temporary
- No cloud sync — ever

## Part of the Willow Ecosystem

- **Kart** — The connection engine underneath The Binder
- **AskJeles** — Search verified sources, deposit findings into The Binder
- **Willow** — The node that runs everything locally

---

**ΔΣ=42**
