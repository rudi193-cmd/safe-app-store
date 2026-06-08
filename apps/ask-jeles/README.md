# Ask Jeles

Ask Jeles is a local-first search companion for the SAFE App Store. Jeles is a butler-librarian: search your local Willow/Binder knowledge first, then the open web, maps, and Special Collections when the query calls for it.

This is a public-preview app, not a polished hosted service. It is designed to run locally, keep the user in control, and make privacy/consent visible.

## What It Does

Ask Jeles gives you a terminal UI for:

- Searching local KB atoms first, then open web or institutional sources depending on the query.
- Opening results directly in your browser.
- Asking Jeles to synthesize the current result set.
- Building a subject-matter trivia quiz from the topic behind the search.
- Saving search notes to local Willow/Binder intake.
- Optionally capturing small learning-event summaries for later pedagogical review.

Search is intentionally not "Special Collections only." General searches can use the open web; research-style queries add institutional sources; navigational queries can hand off to maps/web.

## Install

Ask Jeles targets Python 3.10+ and works best in a virtual environment. The offline demo does not require Willow, MCP, or API keys.

### Linux / macOS

From this directory:

```bash
./dev.sh
```

For a no-network walkthrough with seeded results:

```bash
./dev.sh --demo
```

### Windows PowerShell

From this directory:

```powershell
.\dev.ps1
```

For the offline demo:

```powershell
.\dev.ps1 --demo
```

If PowerShell blocks local scripts, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Manual venv

This works on Linux, macOS, Windows, and WSL:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
ask-jeles --demo
```

Or, without installing the console script:

```bash
python -m askjeles.crown
```

Standalone trivia still exists:

```bash
python -m askjeles.crown --trivia
```

FastAPI verification/web endpoints:

```bash
python -m askjeles.crown --serve
```

### Optional Willow / MCP

Ask Jeles runs without Willow in demo mode and can still use open web search when dependencies are installed. If you have Willow locally, set `WILLOW_ROOT`:

```bash
export WILLOW_ROOT="$HOME/github/willow-2.0"
```

PowerShell:

```powershell
$env:WILLOW_ROOT = "$env:USERPROFILE\github\willow-2.0"
```

Generic MCP discovery is optional. The MCP drawer (`m`) discovers `.mcp.json` files but does not start any server until you connect one for the current session.

## Quick Demo

`--demo` loads an offline `Vespa scooters` topic deck. It is meant for screenshots, posts, and public-preview walkthroughs without depending on live search or API keys.

Try this sequence:

1. Run `./dev.sh --demo`.
2. Press `a` to show the built-in demo synthesis.
3. Press `Ctrl+T` to open the topic trivia overlay.
4. Press `Ctrl+L` to enable session learning, then run trivia again to capture a learning event.
5. Press `m` to open the MCP drawer and show discovered servers without auto-starting them.

The demo links use `example.invalid` and are placeholders; the point is to show Jeles' desk, overlay behavior, topic quiz, consent language, and MCP discovery.

## TUI Keys

| Key | Action |
| --- | --- |
| `Enter` / `o` | Open selected result |
| `a` | Ask Jeles to synthesize the current result set |
| `v` / `Ctrl+V` | Verify the selected result against trusted public sources |
| `Ctrl+T` | Open a topic quiz overlay from the current search |
| `m` | Open MCP drawer — discover servers, connect for session, confirm tool calls |
| `Ctrl+L` | Toggle session-only learning capture |
| `Ctrl+S` | Save current search/answer to local Willow/Binder intake |
| `Ctrl+N` | Clear and start a new search |
| `Ctrl+Q` | Quit |

Trivia, previews, and future overlays should return to the same desk state: query, hits, selected result, and hero state should remain intact.

## Topic Trivia

The trivia overlay is built from the search topic, not from the websites themselves. Jeles first distills noisy results into a short subject-matter brief, strips obvious website/listing/ecommerce artifacts, and then asks multiple-choice questions about the topic.

For example, a search for `Vespa scooters` should produce questions about scooters, Italian design, Piaggio, city mobility, or bodywork, not `vespa.com`, dealers, prices, or used listings.

If no LLM route is available, a rough fallback quiz is generated from the scrubbed topic brief.

## Learning Events And Consent

Learning capture is off by default every time the app starts.

Press `Ctrl+L` to enable it for the current TUI session. Press `Ctrl+L` again to turn it off. Consent is not persisted across launches.

When enabled, Jeles records small JSON summaries only:

- `search`: query class, sources used, hit count, top source labels
- `synthesis`: citation count and answer length, not the full answer
- `trivia`: score, total questions, answered count, completion, duration, accuracy

Local JSONL files are written to:

```text
~/.willow/jeles_learning_events/YYYY-MM-DD.jsonl
```

The same event is also staged through `safe_integration.contribute()` as `jeles_learning_event` for future Willow ingestion:

```text
~/.willow/apps/ask-jeles/intake/
```

These events are intended to become pedagogical atoms later, but only from explicit session consent.

## MCP Adapters

Ask Jeles can discover MCP servers from local `.mcp.json` files without auto-starting them.

Discovery searches:

- `apps/ask-jeles/.mcp.json`
- repo root `.mcp.json`
- sibling apps under `apps/*/.mcp.json`
- optional `~/.mcp.json` and `~/.cursor/mcp.json`

Policy in v1:

- **Discover only by default** — no servers are started until you connect one for the current session.
- **m** opens the MCP drawer.
- Select a server, press **Connect**, inspect tools/resources.
- Arbitrary tool calls require **Run tool** then **Confirm**.
- Tool kind labels (`search`, `read`, `write`, `unknown`) are advisory, not security boundaries.
- Generic MCP results are not merged into normal search ranking yet.

Willow-specific MCP (`mem_jeles_*`, `kb_search`) remains in the existing built-in client and is unchanged.

## Privacy Notes

- Queries are processed locally where possible.
- Learning events do not store full snippets, full answers, or page bodies by default.
- Saved searches are explicit user actions via `Ctrl+S`.
- Learning capture is explicit session consent via `Ctrl+L`.
- MCP/Willow integration uses local dev-fallback auth in development.

## Web/API Surface

The local FastAPI mode exposes verification and safe web endpoints from `askjeles.serve`.

Useful endpoint:

```text
GET/POST /api/safe/web
```

By default it returns trusted web results. With `trusted_only=false`, navigational queries can include broader web/map handoffs.

## Development Notes

Key modules:

- `askjeles/crown.py`: Textual TUI and main CLI entrypoint
- `askjeles/search.py`: search routing and result merging
- `askjeles/kb_search.py`: local Willow/Binder KB search
- `askjeles/trivia.py`: topic-brief quiz generation
- `askjeles/mcp_client.py`: built-in Willow MCP wrappers
- `askjeles/mcp_registry.py`: discover `.mcp.json` servers
- `askjeles/mcp_generic.py`: session-scoped generic MCP connections
- `askjeles/mcp_adapters.py`: advisory tool classification stubs
- `askjeles/overlays.py`: Textual modal overlays (trivia, MCP drawer)
- `askjeles/learning_events.py`: session-consented JSON learning events
- `askjeles/serve.py`: FastAPI verification/web API

Quick checks:

```bash
python -m py_compile $(rg --files . -g '*.py')
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

`deltaS=42`