# The Nightstand

Set heavy things down at night. Pick up one bite in the morning.

A local-first load-triage TUI for the evenings when your desk holds too much.
It is not a task manager — it enforces exactly three rules a task manager won't:

1. **At most one thing is ever in your hands.** Picking something up puts
   whatever you were holding back down. There is no "doing five things."
2. **You work the bite, not the thing.** Picking something up asks one
   question: *what's the one bite?* That's all you owe it today.
3. **Nothing is deleted.** Things are done or archived; the record of what you
   carried — and how many times you picked it up — is yours to keep.

Press `1` when you don't know where to start: the nightstand hands you the
**lightest, oldest** thing waiting. Small wins build up.

## Run from source (standalone)

No Willow checkout, Postgres, or network required — everything lives in
`~/.willow/store/the-nightstand/nightstand.db` (override with `NIGHTSTAND_DB`).

    ./dev.sh        # macOS/Linux
    ./dev.ps1       # Windows (PowerShell)

Or from the store root:

    make run app=the-nightstand

## Keys

| Key | Action |
|-----|--------|
| `n` | Set something down — end with `!` if it's heavy, `~` if it's light |
| `1` | Hand me one — the nightstand picks the lightest, oldest thing |
| `Enter` | Pick up the selected thing (asks for the one bite) |
| `d` | Done — the thing in your hands is finished |
| `b` | Set it back down — no shame, progress is kept |
| `a` | Archive the selected thing |
| `v` | Cycle view: nightstand / done / archived |
| `q` | Quit |

## Privacy

Client-only. One SQLite file under the vault root. No LLM, no network, no
telemetry. `local_processing: 1.0`.
