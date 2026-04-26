# Story Timeline

> "I'm building you a quick and dirty" — Professor Oakenscroll, r/LLMPhysics #general-chat

Free narrative timeline tracker. No $70 subscription. Runs local.

## What it does

- Track events across a story's timeline (in-world dates, not real dates)
- Filter by story or character
- Export to Markdown for sharing

## Run

```bash
pip install -r requirements.txt
python3 app.py
```

## Keys

| Key | Action |
|-----|--------|
| `a` | Add event |
| `d` | Delete selected event |
| `e` | Export timeline to Markdown (saves to Desktop) |
| `r` | Refresh |
| `q` | Quit |

## Data

Stored at `~/.willow/store/story-timeline/timeline.db` — local SQLite, yours to keep.
