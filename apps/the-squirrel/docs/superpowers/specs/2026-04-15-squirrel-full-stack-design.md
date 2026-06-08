# The Squirrel — Full-Stack Genealogical App Design
**Date:** 2026-04-15
**Status:** Approved (conversational brainstorm with Sean Campbell)

---

## What We're Building

A full-stack local genealogy research app. Not a REST API with a frontend bolted on. Not a static HTML page. The **file IS the interface** — a markdown document (`Squirrel.md`) that the user interacts with by typing `@squirrel:` commands. A Python watcher fires when the file changes, a responder dispatches the command, and the result is written back into the file. The app polls the file's mtime and re-renders.

This is the `journal_app.py` pattern (port 5758) extended with a full genealogy command grammar, three AI modes, and swappable era-aesthetic skins.

---

## Core Architecture: Three-File Stack

```
squirrel_app.py        — HTTP server on port 8425. Serves Squirrel.md as rendered
                          markdown. Handles /mtime polling, /write POST, static assets
                          (skins, fonts). No REST API beyond these.

squirrel_watcher.py    — Watches Squirrel.md via watchdog. On save, reads the new
                          content, extracts the last @squirrel: line (Journal mode) or
                          all new content (Listening/Chat mode), signals the responder.

squirrel_responder.py  — Command dispatcher. Parses @squirrel: lines, routes to the
                          correct handler module, writes result blocks back into
                          Squirrel.md. Also manages mode state.
```

**The file is the ground truth.** The scroll-up history is the audit trail. Commands accumulate. Two runs of `@squirrel: tree Oscar Mann` show what changed between sessions.

---

## Mode System

Boots to **Journal** every time. The user must actively invite the LLM in.

| Mode | Trigger | LLM | Description |
|------|---------|-----|-------------|
| Journal | `@squirrel:` prefix only | Never | Fast, deterministic, offline-capable |
| Active Listening | All new content scanned passively | Light | LLM monitors and surfaces connections without being asked |
| Conversational | All new content is a potential message | Full | Natural language, Jeles voice, narrative responses |

Toggle via slider in the UI header OR `@squirrel: mode [journal|listening|chat]`.
Mode is NOT persisted — resets to Journal on every boot.

---

## Command Grammar

### Person Management
```
@squirrel: add person Oscar Mann b.1882 d.1951 Iowa
@squirrel: show person Oscar Mann
@squirrel: edit person 42 birth_place "Dubuque County, Iowa"
@squirrel: show people [--filter name|date|place]
```

### Relationships
```
@squirrel: link Oscar Mann → parent → Carl Mann
@squirrel: link Oscar Mann → spouse → Mabel Jones
@squirrel: show kin Oscar Mann
```

### Tree Visualization (text-art, inline)
```
@squirrel: tree Oscar Mann
```
Renders a text-art pedigree block back into the file:
```
              ┌─ Carl Mann (1855, Iowa)
Oscar Mann ───┤
              └─ Anna Weber (1858, Prussia)
```

### Fragment Stash (raw observations → Binder)
```
@squirrel: stash "Oscar Mann, b. 1882, Dubuque Co." --source census --confidence likely
@squirrel: show stash [--unsynced]
@squirrel: bind fragment 7 → Oscar Mann
@squirrel: bind all → auto          ← Binder runs fuzzy match, promotes what it can
```

### Source Lookup
```
@squirrel: find sources Iowa 1880s
@squirrel: find sources "Dubuque County" --provider familysearch
```
Queries `db.source_registry` (779 community archives + FTS), renders acorn cards inline.

### External Search (deep links + Wikipedia live)
```
@squirrel: search familysearch Oscar Mann Iowa 1882
@squirrel: search findagrave Oscar Mann
@squirrel: search courtlistener Oscar Mann
@squirrel: search wikipedia Oscar Mann Iowa
```

### GEDCOM
```
@squirrel: export gedcom           ← writes squirrel_export_YYYYMMDD.ged to ~/Desktop
@squirrel: import gedcom ~/family.ged   ← background task, reports fragment count
```

### App Control
```
@squirrel: mode journal|listening|chat
@squirrel: skin mcm|80s|00s|20s
@squirrel: status                  ← N persons, N fragments unsynced, N sources, mode
```

### Conversational (Listening/Chat modes only)
```
Tell me what you know about Oscar Mann's father.
Who in my tree was born in Prussia?
What sources haven't I checked for the Mann line?
```

---

## Data Layer

### Existing (keep as-is)
- `db/persons.py` — persons, relationships, person_lattice_cells, person_sources
- `db/fragments.py` — fragments, tree_branches, fragment_lattice_cells
- `db/sources.py` — source_registry (779 archives, FTS)
- `sap/core/gate.py` — SAP PII gate

### To Add
- `db/events.py` — birth, death, marriage, immigration as first-class records
  (persons table keeps text fields as denormalized cache; events table is canonical)
- `db/media.py` — photo/document attachments linked to persons or events
  (file_path, mime_type, caption, person_id, event_id)
- `binder.py` — fragment → person promotion engine
  (fuzzy name match + date proximity + confidence threshold)
- `gedcom/exporter.py` — walk persons+relationships tree, emit GEDCOM 5.5.1
- `gedcom/importer.py` — parse .ged file, create fragments (not persons directly)

### Schema migration
- `migrate.py` already exists — add Level 3 migration for events + media tables

---

## Responder Module Structure

```
responder/
  __init__.py
  dispatcher.py       — parse @squirrel: line, route to handler
  formatter.py        — acorn-card markdown renderer, text-art pedigree
  commands/
    person.py
    relationship.py
    tree.py
    fragment.py
    source.py
    search.py
    gedcom.py
    control.py        — mode, skin, status
  llm/
    listener.py       — active listening: scan new content, surface connections
    chat.py           — conversational: full Jeles-voice LLM
    prompt.py         — system prompt (Jeles persona, tool descriptions)
```

---

## Skins

Four era-aesthetic CSS themes. Same HTML structure, swappable via `data-skin` attribute on `<body>`. Each skin defines the same CSS variable set but with era-appropriate values.

| Skin | Era | Palette | Toggle Object | LLM UI |
|------|-----|---------|---------------|--------|
| `mcm` | 1950s–60s | Walnut, mustard, burnt orange | 3-position rotary knob | Rounded-corner tube TV, wood panel |
| `80s` | 1980s | Phosphor green on black, scanlines | Rocker switch bank | VU meter + CRT boot sequence |
| `00s` | 2000s | Aqua, glossy gradient, drop shadow | Segmented glossy button | Chat window with "connecting..." |
| `20s` | 2020s | Dark, frosted glass, pill buttons | Floating pill slider | Frosted panel slides in |

`skins/base.css` — structural layout, shared across all themes
`skins/mcm.css`, `skins/80s.css`, `skins/00s.css`, `skins/20s.css` — era overrides

Default skin: `mcm`. Persisted in a local config file (`~/.squirrel/config.json`), NOT reset on boot (unlike mode).

---

## LLM Backend

- **Default:** Ollama (local, no API key, no data leaves machine)
- **Configurable:** model name in `~/.squirrel/config.json` (`llama3`, `mistral`, etc.)
- **Active Listening:** lightweight prompt — scan new content, return a connection hint or nothing
- **Conversational:** full Jeles system prompt, tool descriptions for db queries
- **Fallback:** if Ollama not running, Journal mode only, warn in status bar

---

## File Layout (additions to existing repo)

```
squirrel_app.py
squirrel_watcher.py
squirrel_responder.py
responder/              (new)
skins/                  (new)
  base.css
  mcm.css
  80s.css
  00s.css
  20s.css
gedcom/                 (new)
  exporter.py
  importer.py
binder.py               (new)
db/
  persons.py            (existing)
  fragments.py          (existing)
  sources.py            (existing)
  events.py             (new)
  media.py              (new)
Squirrel.md             (new — the app screen, boots with welcome block)
~/.squirrel/
  config.json           (skin preference, ollama model)
```

---

## What This Is Not

- Not a cloud app. All data stays on the machine.
- Not a GEDCOM-first app. GEDCOM is import/export only, not the data model.
- Not a REST API. The server has three endpoints: serve the file, GET mtime, POST write.
- Not a collaboration tool. Single-user, local-first.
- Not a photo viewer. Media attachments are file paths + metadata; viewing is link-out.

---

## Success Criteria

1. `python squirrel_app.py` opens the app in the browser at `localhost:8425`
2. `@squirrel: add person Oscar Mann b.1882 Iowa` creates a DB record and confirms inline
3. `@squirrel: tree Oscar Mann` renders a text-art pedigree of his known ancestors
4. `@squirrel: mode chat` + a natural language question gets a Jeles-voice response
5. `@squirrel: export gedcom` produces a valid .ged file on the Desktop
6. `@squirrel: skin 80s` repaints the whole app in phosphor green
7. All of the above work without an internet connection (except external search deep links)
