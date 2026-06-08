# Story Timeline

> Writer tool for readers and writers. Local. Free. Willow-integrated.

Track your reading shelf, author research, project notes, and the connections between them — then wire commonplace material into named story timelines with provenance.

## What it does

- **Books tab** — reading shelf with Read / Reading / To Read / DNF counts, top tags, search
- **Authors tab** — author nodes linked from imports or created manually
- **Notes tab** — research notes, quotes, ideas (commonplace source material)
- **Writing tab** — protocol writing projects, named timelines, and promoted timeline entries
- **All Nodes tab** — every library entity type: book, author, note, project, theme, character, place, event
- **Import** — Goodreads, StoryGraph, or LibraryThing CSV (`i` in TUI); creates author nodes + `written_by` edges
- **Link** — searchable node picker + relation label (no UUID paste)
- **Story protocol** — promote notes/books/ideas into timeline entries on named timelines (CLI)
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

## Story protocol CLI

Promote commonplace material into named timelines (multiple timelines per writing project):

```bash
# Create a writing project and timeline
python3 promote.py create-project --title "My Novel"
python3 promote.py create-timeline --project <project_id> --name "World chronology"

# Promote a note or book into a timeline entry (provenance + edges)
python3 promote.py promote <source_node_id> --timeline <timeline_id>
python3 promote.py promote <source_node_id> --project <project_id> --timeline-name "World chronology"

# Inspect
python3 promote.py list-projects
python3 promote.py list-timelines --project <project_id>
python3 promote.py list-entries --timeline <timeline_id>
```

## Keys

| Key | Action |
|-----|--------|
| `a` | Add node (template picker for book / author / note / project / …) |
| `e` | Edit selected node |
| `d` | Delete selected node |
| `l` | Link selected node to another (search + relation) |
| `p` | Promote selected note/book into a timeline |
| `j` | Research selected note/book with Jeles (cited sources) |
| `s` | Suggest promotion via local SLM + Jeles/KB context |
| `v` | View node detail (Markdown review rendering, provenance) |
| `i` | Import CSV (Goodreads / StoryGraph / LibraryThing) |
| `/` | Focus search (Books tab) |
| `r` | Refresh |
| `q` | Quit (writes session composite to Willow) |

## Data

- **Nodes:** `~/.willow/store/story-timeline/timeline.db` — local SQLite (books, notes, library projects, protocol records)
- **Edges:** `user-{uuid}/story-timeline/_graph/edges` — Willow SOIL graph (requires `~/.willow/user_identity.json`)
- **Protocol collections:** `commonplace/`, `timelines/`, `timeline_entries/`, `atoms/` (provenance, session composite)

### Protocol record types

| Type | Role |
|------|------|
| `commonplace_item` | Captured idea, quote, or research note |
| `writing_project` | Container for a story, essay, world, or draft |
| `timeline` | Named timeline under a project (world, draft, process) |
| `timeline_entry` | Scene, beat, milestone, or fact on a timeline |
| `provenance` | Atom linking an entry back to its source material |

`project` remains a normal library/commonplace node. `writing_project` is only the protocol container used by the Writing tab and promotion flow.

### Standard relations

`derived_from`, `belongs_to_project`, `appears_on_timeline`, `inspired_by`, `supports_scene`, `contradicts_or_tensions_with`

Override DB path for tests: `STORY_TIMELINE_DB=/tmp/timeline.db`

## Intelligence (Jeles + SLM)

Proposal-first assistance — nothing becomes canon until you accept.

| Key | Action |
|-----|--------|
| `j` | Jeles research on selected note/book (cited sources saved locally) |
| `s` | Suggest promotion — gathers Jeles + KB + local SLM, shows review modal |

Requires Willow MCP (`WILLOW_ROOT` + unified MCP) and optional Ollama for `infer_7b`.
When MCP is offline, suggestions fall back to a local heuristic.
