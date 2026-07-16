# The Squirrel

> *We're not calling your family nuts... but.*

Genealogy companion with a sense of humor. Helps you find, collect, and reconnect
the branches of your family tree — even the ones everyone forgot about on purpose.

Part of the Willow ecosystem. Lives in the tree. Knows where things are buried.

## What it does

- Collect family history fragments (names, dates, stories, photos)
- Surface connections Willow already knows about
- Reunite branches that got lost, hidden, or quietly never mentioned
- Deposit verified findings to The Binder

## Tagline

*We help you put fruit back on the family tree.*

## Run

From the store root:

    make run app=the-squirrel

Or directly:

    cd apps/the-squirrel
    pip install -r requirements.txt
    python3 squirrel_app.py        # opens at http://localhost:8425

Local SQLite out of the box — no database server, no accounts, no cloud.
Optional: a Willow Postgres backend (`SQUIRREL_BACKEND=postgres`), and a
local Ollama for the Jeles chat modes.

---

ΔΣ=42
