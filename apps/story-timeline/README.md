# Story Timeline

> Literary knowledge base for readers and writers. Local. Free. Willow-integrated.

Track your reading shelf, author research, project notes, and the connections between them — all in one open node graph.

## What it does

- **Books tab** — reading shelf with Read / Reading / To Read / DNF counts, top tags, search
- **Authors tab** — author nodes linked from imports or created manually
- **Notes tab** — research notes, quotes, ideas
- **All Nodes tab** — every entity type: book, author, note, project, theme, character, place, event
- **Import** — Goodreads, StoryGraph, or LibraryThing CSV (`i` in TUI); creates author nodes + `written_by` edges
- **Link** — searchable node picker + relation label (no UUID paste)
- **Willow edges** — graph relationships persist in SOIL when user identity is provisioned

## Run

```bash
pip install -r requirements.txt
python3 app.py
```

Browser mirror (same codebase):

```bash
textual serve app.py
```

CLI import (without TUI):

```bash
python3 import_csv.py ~/Downloads/goodreads_library_export.csv --authors
```

## Keys

| Key | Action |
|-----|--------|
| `a` | Add node (template picker for book / author / note / project / …) |
| `e` | Edit selected node |
| `d` | Delete selected node |
| `l` | Link selected node to another (search + relation) |
| `v` | View node detail (Markdown review rendering) |
| `i` | Import CSV (Goodreads / StoryGraph / LibraryThing) |
| `/` | Focus search (Books tab) |
| `r` | Refresh |
| `q` | Quit (writes session composite to Willow) |

## Data

- **Nodes:** `~/.willow/store/story-timeline/timeline.db` — local SQLite
- **Edges:** `user-{uuid}/story-timeline/_graph/edges` — Willow SOIL (requires `~/.willow/user_identity.json`)

Override DB path for tests: `STORY_TIMELINE_DB=/tmp/timeline.db`
