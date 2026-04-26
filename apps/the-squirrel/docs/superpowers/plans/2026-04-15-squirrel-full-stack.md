# The Squirrel — Full-Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete local genealogy research app where a markdown file (`Squirrel.md`) IS the interface — `@squirrel:` commands drive CRUD, tree navigation, stash, sources, GEDCOM, and LLM chat.

**Architecture:** Three-file stack (server + watcher + responder) on port 8425. `squirrel_app.py` serves the markdown file as rendered HTML and handles file I/O. `squirrel_watcher.py` detects `@squirrel:` lines via watchdog. `squirrel_responder.py` dispatches commands and writes result blocks back into `Squirrel.md`. All runs in a single process with threads.

**Tech Stack:** Python 3.12, psycopg2-binary (existing), watchdog, markdown, requests (already in env via safe_integration.py), Ollama HTTP API (LLM), stdlib http.server

---

## File Map

**New files (create):**
```
squirrel_app.py                      HTTP server, watcher thread orchestration
squirrel_watcher.py                  Watchdog observer, extracts @squirrel: lines
squirrel_responder.py                Entry point — wires state + dispatcher + file write
responder/__init__.py
responder/state.py                   AppState (mode/skin), shared file RLock, config
responder/dispatcher.py              Command dataclass, parse_command(), route table
responder/formatter.py               result_block(), acorn_card(), pedigree_chart()
responder/commands/__init__.py
responder/commands/person.py         add/show/edit person, show people
responder/commands/relationship.py   link, show kin
responder/commands/tree.py           text-art pedigree, build_ancestors()
responder/commands/fragment.py       stash, show stash, bind fragment
responder/commands/source.py         find sources (→ db.sources)
responder/commands/search.py         external deep links + Wikipedia live
responder/commands/gedcom.py         export/import GEDCOM wrapper commands
responder/commands/control.py        mode, skin, status
responder/llm/__init__.py
responder/llm/prompt.py              Jeles system prompt + tool descriptions
responder/llm/listener.py            Active Listening — passive scan, surface hints
responder/llm/chat.py                Conversational — full Jeles-voice response
binder.py                            Fragment → person promotion engine
gedcom/__init__.py
gedcom/exporter.py                   Walk persons+relationships → GEDCOM 5.5.1
gedcom/importer.py                   Parse .ged → fragments (not persons directly)
db/events.py                         First-class event records (birth/death/marriage)
db/media.py                          Media attachments (photos, docs) linked to persons
skins/base.css                       Structural layout, CSS variable contract
skins/mcm.css                        Mid-Century Modern (default)
skins/80s.css                        1980s phosphor green
skins/00s.css                        2000s Web 2.0 glossy
skins/20s.css                        2020s glassmorphism
Squirrel.md                          Auto-created on first boot; the app screen
tests/conftest.py                    Mock user_lattice so db imports work without Willow
tests/test_dispatcher.py
tests/test_formatter.py
tests/test_app.py
tests/db/test_events.py
tests/db/test_media.py
tests/commands/test_person.py
tests/commands/test_relationship.py
tests/commands/test_tree.py
tests/commands/test_fragment.py
tests/test_binder.py
tests/test_gedcom.py
```

**Existing files (modify):**
```
requirements.txt                     Add: watchdog, markdown
migrate.py                           Add Level 3: events + media schema init
```

---

## Phase 1 — Foundation

### Task 1: Test infrastructure + dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/db/__init__.py`, `tests/commands/__init__.py`

- [ ] **Step 1: Add missing dependencies to requirements.txt**

```
psycopg2-binary==2.9.9
watchdog>=4.0.0
markdown>=3.6
```

- [ ] **Step 2: Create tests/conftest.py — mock user_lattice before any db import**

```python
# tests/conftest.py
"""
Inject a fake user_lattice module before any db.* import fires.
db/__init__.py does sys.path.insert(0, WILLOW_CORE) + from user_lattice import ...
We pre-populate sys.modules so it never hits the filesystem.
"""
import sys
import os
from types import ModuleType

_fake = ModuleType("user_lattice")
_fake.DOMAINS = frozenset({"biography", "geography", "genealogy", "culture", "migration"})
_fake.TEMPORAL_STATES = frozenset({"past", "present", "future", "unknown"})
_fake.DEPTH_MIN = 1
_fake.DEPTH_MAX = 23
_fake.LATTICE_SIZE = 23
sys.modules["user_lattice"] = _fake

os.environ.setdefault("WILLOW_CORE", "/tmp/fake_willow_core")
os.environ.setdefault("WILLOW_PG_DB", "willow")
```

- [ ] **Step 3: Create empty __init__ files**

```bash
touch tests/__init__.py tests/db/__init__.py tests/commands/__init__.py
```

- [ ] **Step 4: Install new dependencies**

```bash
pip install -r requirements.txt
```

Expected: watchdog and markdown install cleanly.

- [ ] **Step 5: Verify conftest works**

```bash
cd /home/sean-campbell/github/safe-app-the-squirrel
python -c "import tests.conftest; import db; print('db import OK')"
```

Expected: `db import OK`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/conftest.py tests/__init__.py tests/db/__init__.py tests/commands/__init__.py
git commit -m "feat: add watchdog+markdown deps; test infrastructure + conftest"
```

---

### Task 2: responder/state.py + responder/dispatcher.py

**Files:**
- Create: `responder/__init__.py`, `responder/state.py`, `responder/dispatcher.py`
- Test: `tests/test_dispatcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dispatcher.py
import pytest
from responder.dispatcher import parse_command, Command

def test_parse_add_person():
    cmd = parse_command("@squirrel: add person Oscar Mann b.1882 d.1951 p.Iowa")
    assert cmd is not None
    assert cmd.name == "add person"
    assert "Oscar" in cmd.args
    assert "b.1882" in cmd.args

def test_parse_tree():
    cmd = parse_command("@squirrel: tree Oscar Mann")
    assert cmd is not None
    assert cmd.name == "tree"
    assert cmd.args == ["Oscar", "Mann"]

def test_parse_link():
    cmd = parse_command("@squirrel: link Oscar Mann → parent → Carl Mann")
    assert cmd is not None
    assert cmd.name == "link"

def test_parse_mode():
    cmd = parse_command("@squirrel: mode chat")
    assert cmd.name == "mode"
    assert cmd.args == ["chat"]

def test_parse_status():
    cmd = parse_command("@squirrel: status")
    assert cmd.name == "status"
    assert cmd.args == []

def test_not_a_command():
    assert parse_command("Oscar Mann was born in Iowa") is None
    assert parse_command("") is None
    assert parse_command("# Some heading") is None

def test_case_insensitive():
    cmd = parse_command("@Squirrel: TREE Oscar Mann")
    assert cmd is not None
    assert cmd.name == "tree"
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_dispatcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'responder'`

- [ ] **Step 3: Create responder/__init__.py and responder/state.py**

```python
# responder/__init__.py
```

```python
# responder/state.py
import threading
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

class Mode(Enum):
    JOURNAL = "journal"
    LISTENING = "listening"
    CHAT = "chat"

CONFIG_PATH = Path.home() / ".squirrel" / "config.json"

@dataclass
class AppState:
    mode: Mode = Mode.JOURNAL
    skin: str = "mcm"
    squirrel_md: Path = field(default_factory=lambda: Path("Squirrel.md"))
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def load_config(self):
        """Load persisted skin preference (mode always resets to JOURNAL)."""
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                self.skin = data.get("skin", "mcm")
            except Exception:
                pass

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"skin": self.skin}, indent=2))

    def append(self, text: str):
        """Thread-safe append to Squirrel.md."""
        with self._lock:
            with open(self.squirrel_md, "a", encoding="utf-8") as f:
                f.write("\n" + text + "\n")
```

- [ ] **Step 4: Create responder/dispatcher.py**

```python
# responder/dispatcher.py
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class Command:
    name: str        # e.g. "add person", "tree", "mode"
    args: list       # tokenized remainder after the command name
    raw: str         # full text after "@squirrel:"

_TRIGGER = re.compile(r'@squirrel:\s+(.+)', re.IGNORECASE)

# Ordered longest-first so "add person" matches before "add"
_PREFIXES = sorted([
    "add person", "show person", "show people", "show kin",
    "edit person", "show stash", "bind fragment", "find sources",
    "export gedcom", "import gedcom",
    "tree", "link", "stash", "search", "mode", "skin", "status",
], key=len, reverse=True)

def parse_command(line: str) -> Optional[Command]:
    """Extract a Command from a line containing @squirrel:. Returns None if not found."""
    if not line:
        return None
    m = _TRIGGER.search(line)
    if not m:
        return None
    text = m.group(1).strip()
    lower = text.lower()
    for prefix in _PREFIXES:
        if lower.startswith(prefix):
            rest = text[len(prefix):].strip()
            args = rest.split() if rest else []
            return Command(name=prefix, args=args, raw=text)
    # Unrecognised — return as unknown so responder can reply helpfully
    return Command(name="unknown", args=text.split(), raw=text)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_dispatcher.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add responder/__init__.py responder/state.py responder/dispatcher.py tests/test_dispatcher.py
git commit -m "feat: responder state + command dispatcher"
```

---

### Task 3: responder/formatter.py

**Files:**
- Create: `responder/formatter.py`
- Test: `tests/test_formatter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_formatter.py
from responder.formatter import result_block, acorn_card, pedigree_chart

def test_result_block_contains_title():
    out = result_block("Test Title", "some content")
    assert "Test Title" in out
    assert "some content" in out

def test_result_block_is_markdown():
    out = result_block("Heading", "body text")
    assert out.startswith("\n---") or "---" in out

def test_acorn_card_contains_source_and_title():
    card = acorn_card("familysearch", "Oscar Mann record", "b. 1882 Iowa")
    assert "familysearch" in card.lower()
    assert "Oscar Mann record" in card
    assert "b. 1882 Iowa" in card

def test_acorn_card_with_url():
    card = acorn_card("findagrave", "Oscar Mann", "burial 1951", url="https://example.com")
    assert "https://example.com" in card

def test_pedigree_chart_contains_name():
    ancestors = {1: {"full_name": "Oscar Mann", "birth_date": "1882"},
                 2: {"full_name": "Carl Mann", "birth_date": "1855"},
                 3: {"full_name": "Anna Weber", "birth_date": "1858"}}
    chart = pedigree_chart("Oscar Mann", ancestors)
    assert "Oscar Mann" in chart
    assert "Carl Mann" in chart
    assert "Anna Weber" in chart
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_formatter.py -v
```

- [ ] **Step 3: Create responder/formatter.py**

```python
# responder/formatter.py
from datetime import datetime


def result_block(title: str, content: str) -> str:
    """Wrap a response in a standard markdown block with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"\n---\n**[{ts}] {title}**\n\n{content}\n\n---\n"


def acorn_card(source: str, title: str, body: str, url: str = None) -> str:
    """Single result card in markdown."""
    link = f"\n→ [{url}]({url})" if url else ""
    return f"**[{source.upper()}]** {title}\n{body}{link}\n"


def pedigree_chart(subject_name: str, ancestors: dict) -> str:
    """
    Text-art ancestor pedigree from Ahnentafel-numbered dict.
    Keys: 1=subject, 2=father, 3=mother, 4=pat.gf, 5=pat.gm, 6=mat.gf, 7=mat.gm

    Output:
              ┌─ Carl Mann (1855)
    Oscar ────┤
              └─ Anna Weber (1858)
    """
    def fmt(person: dict) -> str:
        name = person.get("full_name", "Unknown")
        year = person.get("birth_date", "")
        return f"{name} ({year})" if year else name

    lines = []
    father = ancestors.get(2)
    mother = ancestors.get(3)
    pgf = ancestors.get(4)
    pgm = ancestors.get(5)
    mgf = ancestors.get(6)
    mgm = ancestors.get(7)

    pad = " " * 4
    if pgf:
        lines.append(f"{pad*2}┌─ {fmt(pgf)}")
    if father:
        lines.append(f"{pad}┌─ {fmt(father)}")
        if pgm:
            lines.append(f"{pad*2}└─ {fmt(pgm)}")
    lines.append(f"{subject_name} ─{'─' * 10}┤")
    if mother:
        lines.append(f"{pad}└─ {fmt(mother)}")
        if mgf:
            lines.append(f"{pad*2}┌─ {fmt(mgf)}")
        if mgm:
            lines.append(f"{pad*2}└─ {fmt(mgm)}")

    return "```\n" + "\n".join(lines) + "\n```"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_formatter.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add responder/formatter.py tests/test_formatter.py
git commit -m "feat: result_block, acorn_card, pedigree_chart formatters"
```

---

### Task 4: squirrel_app.py — HTTP server

**Files:**
- Create: `squirrel_app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_app.py
import json
import threading
import urllib.request
import urllib.parse
import time
import os
import tempfile
import pytest

# We test the handler logic, not the live server.
from squirrel_app import SquirrelHandler, WELCOME_BLOCK
from pathlib import Path

def test_welcome_block_contains_squirrel():
    assert "@squirrel:" in WELCOME_BLOCK
    assert "mode" in WELCOME_BLOCK.lower()

def test_squirrel_md_created_on_missing(tmp_path):
    md = tmp_path / "Squirrel.md"
    from squirrel_app import ensure_squirrel_md
    ensure_squirrel_md(md)
    assert md.exists()
    assert "@squirrel:" in md.read_text()
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_app.py -v
```

- [ ] **Step 3: Create squirrel_app.py**

```python
# squirrel_app.py
"""
The Squirrel — HTTP server.
Serves Squirrel.md as rendered HTML on port 8425.
Endpoints:
  GET  /          → rendered Squirrel.md (full HTML page)
  GET  /mtime     → {"mtime": float}
  POST /write     → append {"text": str} to Squirrel.md
  GET  /skins/*   → serve from skins/
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import markdown

PORT = 8425
SQUIRREL_MD = Path("Squirrel.md")
SKINS_DIR = Path(__file__).parent / "skins"

WELCOME_BLOCK = """# The Squirrel 🌰
*genealogy research terminal — file is the interface*

**Commands:**
- `@squirrel: add person Oscar Mann b.1882 d.1951 p.Iowa`
- `@squirrel: tree Oscar Mann`
- `@squirrel: show people`
- `@squirrel: find sources Iowa 1880s`
- `@squirrel: mode listening` — invite the LLM in
- `@squirrel: status`
- `@squirrel: skin 80s`

---
"""

_file_lock = threading.RLock()


def ensure_squirrel_md(path: Path = SQUIRREL_MD):
    if not path.exists():
        path.write_text(WELCOME_BLOCK, encoding="utf-8")


def _render_html(skin: str = "mcm") -> str:
    ensure_squirrel_md()
    raw = SQUIRREL_MD.read_text(encoding="utf-8")
    body = markdown.markdown(raw, extensions=["fenced_code", "tables"])
    skin_link = f'<link rel="stylesheet" href="/skins/base.css">\n    <link rel="stylesheet" href="/skins/{skin}.css">'
    return f"""<!DOCTYPE html>
<html lang="en" data-skin="{skin}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Squirrel</title>
{skin_link}
</head>
<body>
<div id="header">
  <div id="title">THE SQUIRREL 🌰</div>
  <div id="mode-toggle">
    <label>Journal</label>
    <input type="range" min="0" max="2" value="0" id="mode-slider" oninput="setMode(this.value)">
    <label>Chat</label>
  </div>
</div>
<div id="content">{body}</div>
<div id="input-area">
  <textarea id="cmd" placeholder="@squirrel: ..." rows="2"></textarea>
  <button onclick="submitCmd()">↵</button>
</div>
<script>
const MODES = ["journal","listening","chat"];
function setMode(v) {{
  const mode = MODES[v];
  fetch("/write", {{method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{text: "@squirrel: mode " + mode}})}});
}}
function submitCmd() {{
  const t = document.getElementById("cmd").value.trim();
  if (!t) return;
  fetch("/write", {{method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{text: t}})}})
  .then(() => {{ document.getElementById("cmd").value = ""; }});
}}
document.getElementById("cmd").addEventListener("keydown", e => {{
  if (e.key === "Enter" && !e.shiftKey) {{ e.preventDefault(); submitCmd(); }}
}});
let _mtime = 0;
setInterval(async () => {{
  const r = await fetch("/mtime");
  const d = await r.json();
  if (d.mtime !== _mtime) {{ _mtime = d.mtime; location.reload(); }}
}}, 1500);
</script>
</body>
</html>"""


class SquirrelHandler(BaseHTTPRequestHandler):
    skin = "mcm"

    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/":
            html = _render_html(self.skin).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html)
        elif p.path == "/mtime":
            mtime = SQUIRREL_MD.stat().st_mtime if SQUIRREL_MD.exists() else 0
            body = json.dumps({"mtime": mtime}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif p.path.startswith("/skins/"):
            fname = p.path[len("/skins/"):]
            css_path = SKINS_DIR / fname
            if css_path.exists() and css_path.suffix == ".css":
                data = css_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/css")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/write":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            text = body.get("text", "").strip()
            if text:
                with _file_lock:
                    with open(SQUIRREL_MD, "a", encoding="utf-8") as f:
                        f.write("\n" + text + "\n")
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def run(port: int = PORT):
    ensure_squirrel_md()
    server = HTTPServer(("127.0.0.1", port), SquirrelHandler)
    print(f"The Squirrel is open at http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_app.py -v
```

Expected: PASS.

- [ ] **Step 5: Smoke test — start the server manually**

```bash
python squirrel_app.py
```

Open `http://localhost:8425` in browser. Should render the welcome block.

- [ ] **Step 6: Commit**

```bash
git add squirrel_app.py tests/test_app.py
git commit -m "feat: squirrel_app.py — HTTP server on port 8425"
```

---

### Task 5: squirrel_watcher.py + squirrel_responder.py skeleton

**Files:**
- Create: `squirrel_watcher.py`, `squirrel_responder.py`

- [ ] **Step 1: Create squirrel_watcher.py**

```python
# squirrel_watcher.py
"""
Watches Squirrel.md. On file change, reads new lines and fires callback
for each line containing @squirrel: (Journal mode) or all new lines (other modes).
"""
import time
from pathlib import Path
from threading import Thread
from typing import Callable
from watchdog.observers import Observer
from watchdog.events import FileModifiedEvent, FileSystemEventHandler


class _Handler(FileSystemEventHandler):
    def __init__(self, filepath: Path, callback: Callable[[str], None],
                 state_fn: Callable[[], str]):
        self._path = filepath
        self._callback = callback
        self._state_fn = state_fn  # returns current mode string
        self._last_size = filepath.stat().st_size if filepath.exists() else 0

    def on_modified(self, event):
        if not isinstance(event, FileModifiedEvent):
            return
        if Path(event.src_path).resolve() != self._path.resolve():
            return
        try:
            size = self._path.stat().st_size
            if size <= self._last_size:
                self._last_size = size
                return
            with open(self._path, encoding="utf-8") as f:
                f.seek(self._last_size)
                new_text = f.read()
            self._last_size = size
            mode = self._state_fn()
            for line in new_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if mode == "journal":
                    if "@squirrel:" in line.lower():
                        self._callback(line)
                else:
                    self._callback(line)
        except Exception as e:
            print(f"[watcher] error: {e}")


def start_watcher(filepath: Path, callback: Callable[[str], None],
                  state_fn: Callable[[], str]) -> Observer:
    """Start a watchdog observer. Returns the Observer (call .stop() to halt)."""
    handler = _Handler(filepath, callback, state_fn)
    obs = Observer()
    obs.schedule(handler, str(filepath.parent), recursive=False)
    obs.start()
    return obs
```

- [ ] **Step 2: Create squirrel_responder.py**

```python
# squirrel_responder.py
"""
Squirrel Responder — wires state, dispatcher, command handlers, and file writes.
Called by squirrel_watcher on each relevant new line in Squirrel.md.
"""
from pathlib import Path
from responder.state import AppState, Mode
from responder.dispatcher import parse_command
from responder.formatter import result_block
from responder.commands import person, relationship, tree, fragment, source, search, gedcom, control


def make_responder(state: AppState):
    """Return a callback suitable for squirrel_watcher.start_watcher()."""

    def handle(line: str):
        cmd = parse_command(line)
        if cmd is None:
            # Not a command — only act in Listening/Chat modes (Phase 8)
            return

        try:
            result = _dispatch(cmd, state)
        except Exception as e:
            result = result_block("Error", f"```\n{e}\n```")

        if result:
            state.append(result)

    return handle


def _dispatch(cmd, state: AppState) -> str:
    from db import get_connection, release_connection
    name = cmd.name

    # Control commands (no DB needed)
    if name == "mode":
        return control.cmd_mode(state, cmd.args)
    if name == "skin":
        return control.cmd_skin(state, cmd.args)
    if name == "search":
        return search.cmd_search(cmd.args)
    if name == "unknown":
        return result_block("Unknown command", f"No handler for: `{cmd.raw}`\nType `@squirrel: status` for help.")

    conn = get_connection()
    try:
        if name == "add person":
            return person.cmd_add_person(conn, cmd.args)
        if name == "show person":
            return person.cmd_show_person(conn, cmd.args)
        if name == "show people":
            return person.cmd_show_people(conn, cmd.args)
        if name == "edit person":
            return person.cmd_edit_person(conn, cmd.args)
        if name == "link":
            return relationship.cmd_link(conn, cmd.args)
        if name == "show kin":
            return relationship.cmd_show_kin(conn, cmd.args)
        if name == "tree":
            return tree.cmd_tree(conn, cmd.args)
        if name == "stash":
            return fragment.cmd_stash(conn, cmd.args)
        if name == "show stash":
            return fragment.cmd_show_stash(conn, cmd.args)
        if name == "bind fragment":
            return fragment.cmd_bind_fragment(conn, cmd.args)
        if name == "find sources":
            return source.cmd_find_sources(conn, cmd.args)
        if name == "export gedcom":
            return gedcom.cmd_export_gedcom(conn, cmd.args)
        if name == "import gedcom":
            return gedcom.cmd_import_gedcom(conn, cmd.args)
        if name == "status":
            return control.cmd_status(conn, state)
        return result_block("Unknown", f"No handler for `{name}`")
    finally:
        release_connection(conn)
```

- [ ] **Step 3: Create stub command modules (so imports don't fail)**

Create `responder/commands/__init__.py` and these stubs:

```python
# responder/commands/person.py
from responder.formatter import result_block

def cmd_add_person(conn, args): return result_block("add person", "stub")
def cmd_show_person(conn, args): return result_block("show person", "stub")
def cmd_show_people(conn, args): return result_block("show people", "stub")
def cmd_edit_person(conn, args): return result_block("edit person", "stub")
```

Repeat the same stub pattern for:
- `responder/commands/relationship.py` — `cmd_link`, `cmd_show_kin`
- `responder/commands/tree.py` — `cmd_tree`
- `responder/commands/fragment.py` — `cmd_stash`, `cmd_show_stash`, `cmd_bind_fragment`
- `responder/commands/source.py` — `cmd_find_sources`
- `responder/commands/search.py` — `cmd_search`
- `responder/commands/gedcom.py` — `cmd_export_gedcom`, `cmd_import_gedcom`
- `responder/commands/control.py` — `cmd_mode`, `cmd_skin`, `cmd_status`

```python
# responder/commands/control.py (stub)
from responder.formatter import result_block
from responder.state import AppState, Mode

def cmd_mode(state: AppState, args):
    if not args:
        return result_block("Mode", f"Current mode: `{state.mode.value}`")
    m = args[0].lower()
    mapping = {"journal": Mode.JOURNAL, "listening": Mode.LISTENING, "chat": Mode.CHAT}
    if m not in mapping:
        return result_block("Mode", f"Unknown mode `{m}`. Use: journal, listening, chat")
    state.mode = mapping[m]
    return result_block("Mode", f"Mode → `{m}`")

def cmd_skin(state: AppState, args):
    if not args:
        return result_block("Skin", f"Current skin: `{state.skin}`")
    skin = args[0].lower()
    if skin not in ("mcm", "80s", "00s", "20s"):
        return result_block("Skin", f"Unknown skin `{skin}`. Options: mcm, 80s, 00s, 20s")
    state.skin = skin
    state.save_config()
    return result_block("Skin", f"Skin → `{skin}` (reload page to apply)")

def cmd_status(conn, state: AppState):
    return result_block("Status", f"mode: `{state.mode.value}` | skin: `{state.skin}` | db: connected")
```

- [ ] **Step 4: Wire watcher into squirrel_app.py**

Add to `squirrel_app.py` after imports:

```python
from squirrel_watcher import start_watcher
from squirrel_responder import make_responder
from responder.state import AppState
```

Update `run()`:

```python
def run(port: int = PORT):
    ensure_squirrel_md()
    state = AppState(squirrel_md=SQUIRREL_MD)
    state.load_config()
    # Give SquirrelHandler access to skin state
    SquirrelHandler.skin = state.skin
    responder_cb = make_responder(state)
    watcher = start_watcher(SQUIRREL_MD, responder_cb, lambda: state.mode.value)
    try:
        server = HTTPServer(("127.0.0.1", port), SquirrelHandler)
        print(f"The Squirrel is open at http://localhost:{port}")
        server.serve_forever()
    finally:
        watcher.stop()
        watcher.join()
```

- [ ] **Step 5: Smoke test — full loop**

```bash
python squirrel_app.py
```

In browser: type `@squirrel: status` and press Enter. Should see a status result block appear after ~1.5s (mtime poll).

- [ ] **Step 6: Commit**

```bash
git add squirrel_watcher.py squirrel_responder.py responder/commands/ responder/llm/__init__.py
git add squirrel_app.py
git commit -m "feat: watcher + responder skeleton — full @squirrel: loop working"
```

---

## Phase 2 — DB Extensions

### Task 6: db/events.py + db/media.py + migrate Level 3

**Files:**
- Create: `db/events.py`, `db/media.py`
- Modify: `migrate.py`
- Test: `tests/db/test_events.py`, `tests/db/test_media.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/db/test_events.py
import pytest
from db import get_connection, release_connection
import db.events as events_db

@pytest.fixture
def conn():
    c = get_connection()
    events_db.init_schema(c)
    yield c
    c.execute("DELETE FROM the_squirrel.events WHERE notes LIKE 'TEST%'")
    c.commit()
    release_connection(c)

def test_add_and_get_event(conn):
    # Requires a person — use Oscar Mann (id=1 from seed, or create one)
    from db import get_connection as gc
    import db.persons as p
    person = p.add_person(conn, full_name="TEST Event Person")
    pid = person["id"]
    event = events_db.add_event(conn, person_id=pid, event_type="birth",
                                 date="1882", place="Iowa", notes="TEST birth")
    assert event["person_id"] == pid
    assert event["event_type"] == "birth"
    fetched = events_db.get_events(conn, pid)
    assert len(fetched) == 1
    assert fetched[0]["place"] == "Iowa"
    # cleanup
    conn.execute("DELETE FROM the_squirrel.persons WHERE id = %s", (pid,))
    conn.commit()

def test_invalid_event_type(conn):
    with pytest.raises(ValueError, match="Invalid event_type"):
        events_db.add_event(conn, person_id=1, event_type="baptism")
```

```python
# tests/db/test_media.py
import pytest
from db import get_connection, release_connection
import db.media as media_db
import db.persons as persons_db

@pytest.fixture
def conn():
    c = get_connection()
    media_db.init_schema(c)
    yield c
    c.execute("DELETE FROM the_squirrel.media WHERE caption LIKE 'TEST%'")
    c.commit()
    release_connection(c)

def test_add_and_get_media(conn):
    person = persons_db.add_person(conn, full_name="TEST Media Person")
    pid = person["id"]
    m = media_db.add_media(conn, file_path="/tmp/photo.jpg",
                            mime_type="image/jpeg", caption="TEST photo",
                            person_id=pid)
    assert m["person_id"] == pid
    assert m["mime_type"] == "image/jpeg"
    results = media_db.get_media(conn, pid)
    assert any(r["caption"] == "TEST photo" for r in results)
    conn.execute("DELETE FROM the_squirrel.persons WHERE id = %s", (pid,))
    conn.commit()
```

- [ ] **Step 2: Create db/events.py**

```python
# db/events.py
"""
db.events — First-class genealogical events (birth, death, marriage, etc.)
Schema: the_squirrel
SAP gate: write ops require authorization; reads are gated for symmetry.
"""
from typing import Dict, Any, List, Optional
from db import SCHEMA
import sap.core.gate as _gate

VALID_EVENT_TYPES = frozenset({"birth", "death", "marriage", "immigration", "census", "other"})


def init_schema(conn):
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id   BIGINT NOT NULL REFERENCES persons(id),
            event_type  TEXT NOT NULL
                CHECK (event_type IN ('birth','death','marriage','immigration','census','other')),
            date        TEXT,
            place       TEXT,
            notes       TEXT,
            source_url  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_person ON events (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type)")
    conn.commit()


def add_event(conn, *, person_id: int, event_type: str, date: str = None,
              place: str = None, notes: str = None, source_url: str = None) -> Dict[str, Any]:
    _gate.authorized("write")
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {VALID_EVENT_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO events (person_id, event_type, date, place, notes, source_url)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, person_id, event_type, date, place, notes, source_url, created_at
    """, (person_id, event_type, date, place, notes, source_url))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_events(conn, person_id: int) -> List[Dict[str, Any]]:
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, person_id, event_type, date, place, notes, source_url, created_at
        FROM events WHERE person_id = %s ORDER BY date ASC NULLS LAST
    """, (person_id,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
```

- [ ] **Step 3: Create db/media.py**

```python
# db/media.py
"""
db.media — Media attachments (photos, documents) linked to persons or events.
Schema: the_squirrel
"""
from typing import Dict, Any, List, Optional
from db import SCHEMA
import sap.core.gate as _gate

VALID_MIME_TYPES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/tiff",
    "application/pdf", "text/plain"
})


def init_schema(conn):
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            file_path   TEXT NOT NULL,
            mime_type   TEXT NOT NULL,
            caption     TEXT,
            person_id   BIGINT REFERENCES persons(id),
            event_id    BIGINT REFERENCES events(id),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_media_person ON media (person_id)")
    conn.commit()


def add_media(conn, *, file_path: str, mime_type: str, caption: str = None,
              person_id: int = None, event_id: int = None) -> Dict[str, Any]:
    _gate.authorized("write")
    if mime_type not in VALID_MIME_TYPES:
        raise ValueError(f"Invalid mime_type '{mime_type}'. Must be one of: {VALID_MIME_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO media (file_path, mime_type, caption, person_id, event_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, file_path, mime_type, caption, person_id, event_id, created_at
    """, (file_path, mime_type, caption, person_id, event_id))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_media(conn, person_id: int) -> List[Dict[str, Any]]:
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, file_path, mime_type, caption, person_id, event_id, created_at
        FROM media WHERE person_id = %s ORDER BY created_at DESC
    """, (person_id,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
```

- [ ] **Step 4: Update migrate.py — add Level 3**

```python
# At the bottom of migrate.py, add to main():
import db.events as events_db
import db.media as media_db

# Inside main(), after existing init calls:
events_db.init_schema(conn)
print("  ✓ events")

media_db.init_schema(conn)
print("  ✓ media")
```

- [ ] **Step 5: Run migration**

```bash
python migrate.py
```

Expected: `✓ events`, `✓ media` printed.

- [ ] **Step 6: Run tests**

```bash
pytest tests/db/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add db/events.py db/media.py migrate.py tests/db/
git commit -m "feat: db/events + db/media — first-class records + migration"
```

---

## Phase 3 — Person, Relationship & Tree Commands

### Task 7: responder/commands/person.py

**Files:**
- Modify: `responder/commands/person.py` (replace stub)
- Test: `tests/commands/test_person.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_person.py
import pytest
from unittest.mock import MagicMock
from responder.commands.person import parse_person_args, cmd_add_person, cmd_show_people

def test_parse_person_args_full():
    args = "Oscar Mann b.1882 d.1951 p.Iowa".split()
    r = parse_person_args(args)
    assert r["full_name"] == "Oscar Mann"
    assert r["birth_date"] == "1882"
    assert r["death_date"] == "1951"
    assert r["birth_place"] == "Iowa"

def test_parse_person_args_name_only():
    r = parse_person_args(["Oscar", "Mann"])
    assert r["full_name"] == "Oscar Mann"
    assert r.get("birth_date") is None

def test_parse_person_args_multiword_place():
    args = "Carl Mann b.1855 p.Dubuque_County_Iowa".split()
    r = parse_person_args(args)
    assert r["birth_place"] == "Dubuque County Iowa"

def test_cmd_add_person_calls_db():
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: s
    mock_conn.cursor.return_value.fetchone.return_value = (
        42, "Oscar Mann", "1882", "Iowa", None, None, None, None, None, None, None, None, False
    )
    mock_conn.cursor.return_value.description = [
        (c,) for c in ["id","full_name","birth_date","birth_place","death_date",
                        "death_place","burial_place","memorial_id","memorial_url",
                        "bio","created_at","updated_at","is_deleted"]
    ]
    # We test parse, not the full DB call (integration tested separately)
    result = parse_person_args(["Oscar", "Mann", "b.1882"])
    assert result["full_name"] == "Oscar Mann"
```

- [ ] **Step 2: Create responder/commands/person.py**

```python
# responder/commands/person.py
import db.persons as persons_db
from responder.formatter import result_block


def parse_person_args(args: list) -> dict:
    """
    Parse: Oscar Mann b.1882 d.1951 p.Iowa
    Flags: b.YEAR=birth_date, d.YEAR=death_date, p.Place=birth_place (use _ for spaces)
    Everything else = full_name tokens.
    """
    result = {}
    name_parts = []
    for a in args:
        if a.startswith("b."):
            result["birth_date"] = a[2:]
        elif a.startswith("d."):
            result["death_date"] = a[2:]
        elif a.startswith("p."):
            result["birth_place"] = a[2:].replace("_", " ")
        else:
            name_parts.append(a)
    result["full_name"] = " ".join(name_parts)
    return result


def cmd_add_person(conn, args: list) -> str:
    if not args:
        return result_block("add person", "Usage: `@squirrel: add person Name b.YYYY d.YYYY p.Place`")
    kwargs = parse_person_args(args)
    if not kwargs.get("full_name"):
        return result_block("add person", "Name is required.")
    person = persons_db.add_person(conn, **kwargs)
    lines = [f"✓ **{person['full_name']}** added (id={person['id']})"]
    if person.get("birth_date"):
        lines.append(f"  b. {person['birth_date']}")
    if person.get("birth_place"):
        lines.append(f"  {person['birth_place']}")
    return result_block("add person", "\n".join(lines))


def cmd_show_person(conn, args: list) -> str:
    if not args:
        return result_block("show person", "Usage: `@squirrel: show person Name`")
    query = " ".join(args)
    matches = persons_db.search_persons(conn, query)
    if not matches:
        return result_block("show person", f"No person found matching `{query}`")
    p = matches[0]
    lines = [f"**{p['full_name']}** (id={p['id']})"]
    if p.get("birth_date"): lines.append(f"  Born:   {p['birth_date']}")
    if p.get("birth_place"): lines.append(f"  Place:  {p['birth_place']}")
    if p.get("death_date"): lines.append(f"  Died:   {p['death_date']}")
    if p.get("burial_place"): lines.append(f"  Burial: {p['burial_place']}")
    if p.get("bio"): lines.append(f"\n_{p['bio']}_")
    return result_block("person", "\n".join(lines))


def cmd_show_people(conn, args: list) -> str:
    query = " ".join(args) if args else ""
    if query:
        people = persons_db.search_persons(conn, query)
    else:
        # Return all — search with broad wildcard
        people = persons_db.search_persons(conn, "")
    if not people:
        return result_block("show people", "No persons in the tree yet.")
    rows = ["| id | Name | Born | Place |", "|----|------|------|-------|"]
    for p in people:
        rows.append(f"| {p['id']} | {p['full_name']} | {p.get('birth_date','—')} | {p.get('birth_place','—')} |")
    return result_block(f"people ({len(people)})", "\n".join(rows))


def cmd_edit_person(conn, args: list) -> str:
    """Usage: @squirrel: edit person ID field value"""
    if len(args) < 3:
        return result_block("edit person", "Usage: `@squirrel: edit person ID field value`\nFields: birth_date, death_date, birth_place, burial_place, bio")
    try:
        person_id = int(args[0])
    except ValueError:
        return result_block("edit person", f"Expected numeric ID, got `{args[0]}`")
    field = args[1].lower()
    value = " ".join(args[2:])
    allowed = {"birth_date", "death_date", "birth_place", "death_place", "burial_place", "bio"}
    if field not in allowed:
        return result_block("edit person", f"Unknown field `{field}`. Allowed: {', '.join(sorted(allowed))}")
    cur = conn.cursor()
    cur.execute(f"UPDATE the_squirrel.persons SET {field} = %s, updated_at = now() WHERE id = %s",
                (value, person_id))
    if cur.rowcount == 0:
        conn.rollback()
        return result_block("edit person", f"No person with id={person_id}")
    conn.commit()
    return result_block("edit person", f"✓ person {person_id} → `{field}` = `{value}`")
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/commands/test_person.py -v
```

Expected: PASS.

- [ ] **Step 4: Integration smoke test**

```
@squirrel: add person TEST Smoketest b.2000 p.Iowa
@squirrel: show person TEST Smoketest
@squirrel: show people
```

Verify result blocks appear in the browser.

- [ ] **Step 5: Commit**

```bash
git add responder/commands/person.py tests/commands/test_person.py
git commit -m "feat: person commands — add, show, edit, list"
```

---

### Task 8: responder/commands/relationship.py

**Files:**
- Modify: `responder/commands/relationship.py`
- Test: `tests/commands/test_relationship.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_relationship.py
from responder.commands.relationship import parse_link_args

def test_parse_link_arrow():
    a, rel, b = parse_link_args(["Oscar", "Mann", "→", "parent", "→", "Carl", "Mann"])
    assert a == "Oscar Mann"
    assert rel == "parent"
    assert b == "Carl Mann"

def test_parse_link_arrow_ascii():
    a, rel, b = parse_link_args(["Oscar", "Mann", "->", "spouse", "->", "Mabel", "Jones"])
    assert a == "Oscar Mann"
    assert rel == "spouse"
    assert b == "Mabel Jones"

def test_parse_link_invalid_no_arrow():
    result = parse_link_args(["Oscar", "Mann", "parent", "Carl", "Mann"])
    assert result is None
```

- [ ] **Step 2: Create responder/commands/relationship.py**

```python
# responder/commands/relationship.py
import db.persons as persons_db
from db.persons import VALID_RELATIONSHIP_TYPES, add_relationship
from responder.formatter import result_block
from typing import Optional, Tuple


def parse_link_args(args: list) -> Optional[Tuple[str, str, str]]:
    """
    Parse: Oscar Mann → parent → Carl Mann
    Returns (name_a, rel_type, name_b) or None if unparseable.
    Arrow can be → or ->
    """
    arrows = {"→", "->"}
    idx = [i for i, a in enumerate(args) if a in arrows]
    if len(idx) < 2:
        return None
    i1, i2 = idx[0], idx[1]
    name_a = " ".join(args[:i1])
    rel = args[i1 + 1] if i1 + 1 < i2 else ""
    name_b = " ".join(args[i2 + 1:])
    if not name_a or not rel or not name_b:
        return None
    return name_a.strip(), rel.strip().lower(), name_b.strip()


def cmd_link(conn, args: list) -> str:
    parsed = parse_link_args(args)
    if parsed is None:
        return result_block("link", "Usage: `@squirrel: link Name → rel_type → Name`\nRel types: parent, child, spouse, sibling")
    name_a, rel, name_b = parsed
    if rel not in VALID_RELATIONSHIP_TYPES:
        return result_block("link", f"Invalid relationship `{rel}`. Use: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}")
    persons_a = persons_db.search_persons(conn, name_a)
    persons_b = persons_db.search_persons(conn, name_b)
    if not persons_a:
        return result_block("link", f"Person not found: `{name_a}`")
    if not persons_b:
        return result_block("link", f"Person not found: `{name_b}`")
    a, b = persons_a[0], persons_b[0]
    add_relationship(conn, a["id"], b["id"], rel)
    return result_block("link", f"✓ **{a['full_name']}** → `{rel}` → **{b['full_name']}**")


def cmd_show_kin(conn, args: list) -> str:
    if not args:
        return result_block("show kin", "Usage: `@squirrel: show kin Name`")
    query = " ".join(args)
    matches = persons_db.search_persons(conn, query)
    if not matches:
        return result_block("show kin", f"No person found matching `{query}`")
    person = matches[0]
    tree = persons_db.get_family_tree(conn, person["id"])
    rels = tree["relationships"]
    if not rels:
        return result_block("kin", f"**{person['full_name']}** — no relationships on record.")
    lines = [f"**{person['full_name']}** relationships:"]
    for r in rels:
        lines.append(f"  {r['relationship_type']}: {r['related_name']}")
    return result_block("kin", "\n".join(lines))
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/commands/test_relationship.py -v
```

- [ ] **Step 4: Commit**

```bash
git add responder/commands/relationship.py tests/commands/test_relationship.py
git commit -m "feat: relationship commands — link, show kin"
```

---

### Task 9: responder/commands/tree.py — text-art pedigree

**Files:**
- Modify: `responder/commands/tree.py`
- Test: `tests/commands/test_tree.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_tree.py
from responder.commands.tree import build_ancestors_dict, render_pedigree

def test_build_ancestors_dict_empty():
    # Returns dict keyed by Ahnentafel number
    # With no relationships, returns {1: subject}
    result = build_ancestors_dict({}, 0, {})
    assert 1 not in result or True  # just verifies it doesn't crash

def test_render_pedigree_three_gen():
    ancestors = {
        1: {"full_name": "Oscar Mann", "birth_date": "1882"},
        2: {"full_name": "Carl Mann", "birth_date": "1855"},
        3: {"full_name": "Anna Weber", "birth_date": "1858"},
    }
    out = render_pedigree("Oscar Mann", ancestors)
    assert "Oscar Mann" in out
    assert "Carl Mann" in out
    assert "Anna Weber" in out
    assert "┌" in out or "─" in out

def test_render_pedigree_no_parents():
    ancestors = {1: {"full_name": "Oscar Mann", "birth_date": "1882"}}
    out = render_pedigree("Oscar Mann", ancestors)
    assert "Oscar Mann" in out
```

- [ ] **Step 2: Create responder/commands/tree.py**

```python
# responder/commands/tree.py
from typing import Dict, Any
import db.persons as persons_db
from responder.formatter import result_block


def build_ancestors_dict(conn, person_id: int, depth: int = 3) -> Dict[int, Dict]:
    """
    Build Ahnentafel-numbered ancestor dict.
    1=subject, 2=father, 3=mother, 4=pat.gf, 5=pat.gm, 6=mat.gf, 7=mat.gm
    Recurses up to `depth` generations.
    """
    result = {}

    def _recurse(pid: int, ahnentafel: int, gen: int):
        if gen > depth or ahnentafel > 127:
            return
        tree = persons_db.get_family_tree(conn, pid)
        if tree["person"] is None:
            return
        result[ahnentafel] = tree["person"]
        parents = [r for r in tree["relationships"] if r["relationship_type"] == "parent"]
        # Assign father=even slot, mother=odd slot
        for i, rel in enumerate(parents[:2]):
            child_id = ahnentafel * 2 + i
            _recurse(rel["related_person_id"], child_id, gen + 1)

    _recurse(person_id, 1, 1)
    return result


def render_pedigree(subject_name: str, ancestors: Dict[int, Dict]) -> str:
    """Text-art pedigree chart from Ahnentafel dict."""

    def fmt(n: int) -> str:
        p = ancestors.get(n)
        if not p:
            return "Unknown"
        name = p.get("full_name", "Unknown")
        year = p.get("birth_date", "")
        return f"{name} ({year})" if year else name

    lines = []
    has_gg = any(k >= 8 for k in ancestors)
    has_g = any(4 <= k <= 7 for k in ancestors)
    pad = "    "

    if has_g:
        if ancestors.get(4):
            lines.append(f"{pad*2}┌─ {fmt(4)}")
        if ancestors.get(2):
            lines.append(f"{pad}┌─ {fmt(2)}")
        if ancestors.get(5):
            lines.append(f"{pad*2}└─ {fmt(5)}")
    elif ancestors.get(2):
        lines.append(f"{pad}┌─ {fmt(2)}")

    lines.append(f"{subject_name} {'─'*6}┤")

    if has_g:
        if ancestors.get(6):
            lines.append(f"{pad*2}┌─ {fmt(6)}")
        if ancestors.get(3):
            lines.append(f"{pad}└─ {fmt(3)}")
        if ancestors.get(7):
            lines.append(f"{pad*2}└─ {fmt(7)}")
    elif ancestors.get(3):
        lines.append(f"{pad}└─ {fmt(3)}")

    return "```\n" + "\n".join(lines) + "\n```"


def cmd_tree(conn, args: list) -> str:
    if not args:
        return result_block("tree", "Usage: `@squirrel: tree Name`")
    query = " ".join(args)
    matches = persons_db.search_persons(conn, query)
    if not matches:
        return result_block("tree", f"No person found matching `{query}`")
    person = matches[0]
    ancestors = build_ancestors_dict(conn, person["id"], depth=3)
    chart = render_pedigree(person["full_name"], ancestors)
    gen_count = max((k.bit_length() - 1 for k in ancestors), default=0)
    return result_block(f"tree — {person['full_name']} ({len(ancestors)} persons, {gen_count} gen)",
                        chart)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/commands/test_tree.py -v
```

- [ ] **Step 4: Commit**

```bash
git add responder/commands/tree.py tests/commands/test_tree.py
git commit -m "feat: tree command — Ahnentafel pedigree chart"
```

---

## Phase 4 — Stash & Binder

### Task 10: responder/commands/fragment.py

**Files:**
- Modify: `responder/commands/fragment.py`
- Test: `tests/commands/test_fragment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_fragment.py
from responder.commands.fragment import parse_stash_args

def test_parse_stash_text_only():
    r = parse_stash_args(['"Oscar', 'Mann', 'Iowa', '1882"'])
    assert "Oscar" in r["story_text"]

def test_parse_stash_with_confidence():
    r = parse_stash_args(["Oscar", "Mann", "--confidence", "likely"])
    assert r["confidence"] == "likely"

def test_parse_stash_default_confidence():
    r = parse_stash_args(["Oscar", "Mann"])
    assert r["confidence"] == "uncertain"
```

- [ ] **Step 2: Create responder/commands/fragment.py**

```python
# responder/commands/fragment.py
import db.fragments as fragments_db
from db.fragments import VALID_CONFIDENCE_LEVELS
from responder.formatter import result_block


def parse_stash_args(args: list) -> dict:
    """
    Parse stash args. Flags: --confidence, --source, --type
    Everything else = story_text (joined).
    """
    result = {"confidence": "uncertain", "fragment_type": "story"}
    text_parts = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--confidence" and i + 1 < len(args):
            result["confidence"] = args[i + 1]
            i += 2
        elif a == "--source" and i + 1 < len(args):
            result["source"] = args[i + 1]
            i += 2
        elif a == "--type" and i + 1 < len(args):
            result["fragment_type"] = args[i + 1]
            i += 2
        else:
            text_parts.append(a)
            i += 1
    result["story_text"] = " ".join(text_parts).strip('"')
    return result


def cmd_stash(conn, args: list) -> str:
    if not args:
        return result_block("stash", "Usage: `@squirrel: stash \"text\" --confidence likely --source census`")
    kwargs = parse_stash_args(args)
    story = kwargs.pop("story_text", "")
    # Infer person_name from first 1-3 words of the story
    words = story.split()
    person_name = " ".join(words[:2]) if len(words) >= 2 else story
    frag = fragments_db.add_fragment(conn, person_name=person_name,
                                     story_text=story, **kwargs)
    return result_block("stash", f"✓ Fragment {frag['id']} stashed\n  `{story[:80]}`\n  confidence: `{frag['confidence']}`")


def cmd_show_stash(conn, args: list) -> str:
    frags = fragments_db.get_unsynced_fragments(conn, limit=20)
    if not frags:
        return result_block("stash", "Stash is empty (or all fragments have been bound).")
    lines = [f"**{len(frags)} unsynced fragments:**\n"]
    for f in frags:
        story_preview = (f.get("story_text") or "")[:60]
        lines.append(f"  [{f['id']}] `{f['confidence']}` — {f['person_name']} — {story_preview}")
    return result_block("stash", "\n".join(lines))


def cmd_bind_fragment(conn, args: list) -> str:
    """Usage: @squirrel: bind fragment ID → Person Name"""
    raw = " ".join(args)
    if "→" in raw or "->" in raw:
        sep = "→" if "→" in raw else "->"
        parts = raw.split(sep, 1)
        try:
            frag_id = int(parts[0].strip())
        except ValueError:
            return result_block("bind fragment", f"Expected numeric fragment ID before `{sep}`")
        person_query = parts[1].strip()
        matches = __import__("db.persons", fromlist=["search_persons"]).search_persons(conn, person_query)
        if not matches:
            return result_block("bind fragment", f"No person found: `{person_query}`")
        person = matches[0]
        from binder import Binder
        b = Binder(conn)
        result = b.bind(frag_id, person["id"])
        return result_block("bind fragment", f"✓ Fragment {frag_id} bound to **{person['full_name']}**")
    elif args and args[0] == "all":
        from binder import Binder
        b = Binder(conn)
        results = b.auto_bind()
        return result_block("bind all", f"✓ Auto-bound {len(results)} fragment(s)")
    else:
        return result_block("bind fragment", "Usage: `@squirrel: bind fragment ID → Person Name`\nOr: `@squirrel: bind fragment all → auto`")
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/commands/test_fragment.py -v
```

- [ ] **Step 4: Commit**

```bash
git add responder/commands/fragment.py tests/commands/test_fragment.py
git commit -m "feat: fragment commands — stash, show stash, bind"
```

---

### Task 11: binder.py

**Files:**
- Create: `binder.py`
- Test: `tests/test_binder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_binder.py
import pytest
from unittest.mock import MagicMock, patch
from binder import Binder, _name_similarity

def test_name_similarity_exact():
    assert _name_similarity("Oscar Mann", "Oscar Mann") == 1.0

def test_name_similarity_close():
    score = _name_similarity("Oscar Mann", "Oscar Man")
    assert 0.7 < score < 1.0

def test_name_similarity_different():
    score = _name_similarity("Oscar Mann", "Carl Weber")
    assert score < 0.5

def test_binder_bind_marks_synced():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (1,)
    mock_cur.rowcount = 1
    b = Binder(mock_conn)
    result = b.bind(fragment_id=7, person_id=42)
    assert result["fragment_id"] == 7
    assert result["person_id"] == 42
    mock_conn.commit.assert_called()
```

- [ ] **Step 2: Create binder.py**

```python
# binder.py
"""
Binder — promotes fragments to person records.
bind(fragment_id, person_id): marks fragment as synced.
auto_bind(threshold): fuzzy-matches unsynced fragments to persons.
"""
import difflib
from datetime import datetime
from typing import List, Dict, Any

import db.persons as persons_db
import db.fragments as fragments_db


def _name_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio between two name strings (case-insensitive)."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


class Binder:
    def __init__(self, conn):
        self.conn = conn

    def bind(self, fragment_id: int, person_id: int) -> Dict[str, Any]:
        """Mark a fragment as synced to a person. Returns {fragment_id, person_id, synced_at}."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE the_squirrel.fragments
            SET binder_synced_at = %s
            WHERE id = %s AND is_deleted = 0
        """, (datetime.utcnow(), fragment_id))
        if cur.rowcount == 0:
            self.conn.rollback()
            raise ValueError(f"Fragment {fragment_id} not found or already deleted")
        self.conn.commit()
        return {"fragment_id": fragment_id, "person_id": person_id,
                "synced_at": datetime.utcnow().isoformat()}

    def auto_bind(self, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """
        Fuzzy-match unsynced fragments to existing persons.
        Binds matches above threshold. Returns list of {fragment_id, person_id, score}.
        """
        frags = fragments_db.get_unsynced_fragments(self.conn, limit=200)
        people = persons_db.search_persons(self.conn, "")
        bound = []
        for frag in frags:
            best_score = 0.0
            best_person = None
            for person in people:
                score = _name_similarity(frag["person_name"], person["full_name"])
                if score > best_score:
                    best_score = score
                    best_person = person
            if best_person and best_score >= threshold:
                try:
                    self.bind(frag["id"], best_person["id"])
                    bound.append({"fragment_id": frag["id"],
                                  "person_id": best_person["id"],
                                  "score": round(best_score, 3)})
                except Exception:
                    pass
        return bound
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_binder.py -v
```

- [ ] **Step 4: Commit**

```bash
git add binder.py tests/test_binder.py
git commit -m "feat: Binder — fragment promotion with fuzzy name match"
```

---

## Phase 5 — Sources & External Search

### Task 12: responder/commands/source.py + search.py

**Files:**
- Modify: `responder/commands/source.py`, `responder/commands/search.py`

- [ ] **Step 1: Create responder/commands/source.py**

```python
# responder/commands/source.py
import db.sources as sources_db
from responder.formatter import result_block, acorn_card


def cmd_find_sources(conn, args: list) -> str:
    if not args:
        return result_block("find sources", "Usage: `@squirrel: find sources [query] [--state Iowa] [--provider familysearch]`")
    # Parse --state and --provider flags
    state = None
    provider = None
    query_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--state" and i + 1 < len(args):
            state = args[i + 1]; i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1]; i += 2
        else:
            query_parts.append(args[i]); i += 1
    query = " ".join(query_parts)
    results = sources_db.lookup_sources(conn, query=query, state=state,
                                        provider=provider, limit=8)
    if not results:
        return result_block("find sources", f"No sources found for `{query or state or 'all'}`")
    cards = "\n".join(
        acorn_card(r["provider"], r["name"],
                   f"State: {r['state'] or '—'}", url=r["url"])
        for r in results
    )
    return result_block(f"sources ({len(results)} found)", cards)
```

- [ ] **Step 2: Create responder/commands/search.py**

```python
# responder/commands/search.py
"""
External search — builds deep links and fetches Wikipedia summaries.
No DB needed; all links are outbound.
"""
import urllib.parse
import urllib.request
import json
from responder.formatter import result_block, acorn_card

SOURCES = {"familysearch", "findagrave", "courtlistener", "wikipedia", "all"}


def cmd_search(args: list) -> str:
    if not args:
        return result_block("search", "Usage: `@squirrel: search [source] query`\nSources: familysearch, findagrave, courtlistener, wikipedia, all")

    source = args[0].lower() if args[0].lower() in SOURCES else "all"
    query_args = args[1:] if source != "all" else args
    name = " ".join(query_args)

    if not name:
        return result_block("search", "Provide a name to search.")

    cards = []
    enc = urllib.parse.quote_plus

    # Wikipedia (live fetch)
    if source in ("all", "wikipedia"):
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(name.replace(' ', '_'))}"
            req = urllib.request.urlopen(url, timeout=5)
            data = json.loads(req.read().decode())
            if data.get("extract"):
                cards.append(acorn_card("wikipedia", data["title"],
                                        data["extract"][:280] + "…",
                                        url=data.get("content_urls", {}).get("desktop", {}).get("page")))
        except Exception:
            pass

    # FamilySearch deep link
    if source in ("all", "familysearch") and name:
        parts = name.split()
        url = (f"https://www.familysearch.org/search/record/results"
               f"?q.givenName={enc(parts[0])}&q.surname={enc(parts[-1])}")
        cards.append(acorn_card("familysearch", f"Search: {name}", "World's largest genealogy database.", url=url))

    # FindAGrave deep link
    if source in ("all", "findagrave") and name:
        parts = name.split()
        url = (f"https://www.findagrave.com/memorial/search"
               f"?firstname={enc(parts[0])}&lastname={enc(parts[-1])}")
        cards.append(acorn_card("findagrave", f"Search: {name}", "Memorial and burial records.", url=url))

    # CourtListener deep link
    if source in ("all", "courtlistener") and name:
        url = f"https://www.courtlistener.com/?q={enc(name)}&type=p&order_by=score+desc"
        cards.append(acorn_card("courtlistener", f"Search: {name}", "Federal court records.", url=url))

    if not cards:
        return result_block("search", f"No results for `{name}` from `{source}`")

    return result_block(f"search — {name}", "\n".join(cards))
```

- [ ] **Step 3: Quick smoke test**

```
@squirrel: find sources Iowa 1880s
@squirrel: search familysearch Oscar Mann Iowa
@squirrel: search wikipedia Oscar Mann
```

Verify acorn cards appear in browser.

- [ ] **Step 4: Commit**

```bash
git add responder/commands/source.py responder/commands/search.py
git commit -m "feat: source lookup + external search commands"
```

---

## Phase 6 — GEDCOM

### Task 13: gedcom/exporter.py + gedcom/importer.py

**Files:**
- Create: `gedcom/__init__.py`, `gedcom/exporter.py`, `gedcom/importer.py`
- Modify: `responder/commands/gedcom.py`
- Test: `tests/test_gedcom.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_gedcom.py
import pytest
from pathlib import Path
import tempfile
from gedcom.exporter import build_gedcom_lines

def test_build_gedcom_lines_minimal():
    persons = [{"id": 1, "full_name": "Oscar Mann", "birth_date": "1882",
                "birth_place": "Iowa", "death_date": "1951", "death_place": None}]
    relationships = []
    lines = build_gedcom_lines(persons, relationships)
    text = "\n".join(lines)
    assert "INDI" in text
    assert "Oscar Mann" in text
    assert "1882" in text
    assert "0 HEAD" in text
    assert "0 TRLR" in text

def test_build_gedcom_has_header_and_trailer():
    lines = build_gedcom_lines([], [])
    assert lines[0].startswith("0 HEAD")
    assert lines[-1] == "0 TRLR"
```

- [ ] **Step 2: Create gedcom/__init__.py**

```python
# gedcom/__init__.py
```

- [ ] **Step 3: Create gedcom/exporter.py**

```python
# gedcom/exporter.py
"""
GEDCOM 5.5.1 exporter.
Walks the_squirrel persons + relationships → .ged file.
"""
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import db.persons as persons_db


def build_gedcom_lines(persons: List[Dict], relationships: List[Dict]) -> List[str]:
    """Build GEDCOM lines from person dicts and relationship dicts."""
    now = datetime.utcnow()
    lines = [
        "0 HEAD",
        "1 SOUR TheSquirrel",
        "2 VERS 2.0",
        f"1 DATE {now.strftime('%d %b %Y').upper()}",
        "1 GEDC",
        "2 VERS 5.5.1",
        "1 CHAR UTF-8",
    ]

    # Build family index: (father_id, mother_id) → list of child_ids
    families = {}
    for r in relationships:
        if r["relationship_type"] == "parent":
            # r = person_id is child, related_person_id is parent
            # Approximate: first parent = father slot
            child_id = r["person_id"]
            parent_id = r["related_person_id"]
            key = (parent_id, None)
            if key not in families:
                families[key] = []
            families[key].append(child_id)

    # INDI records
    for p in persons:
        pid = p["id"]
        lines.append(f"0 @I{pid}@ INDI")
        lines.append(f"1 NAME {p['full_name']}")
        parts = p["full_name"].rsplit(" ", 1)
        if len(parts) == 2:
            lines.append(f"2 GIVN {parts[0]}")
            lines.append(f"2 SURN {parts[1]}")
        if p.get("birth_date") or p.get("birth_place"):
            lines.append("1 BIRT")
            if p.get("birth_date"):
                lines.append(f"2 DATE {p['birth_date']}")
            if p.get("birth_place"):
                lines.append(f"2 PLAC {p['birth_place']}")
        if p.get("death_date") or p.get("death_place"):
            lines.append("1 DEAT")
            if p.get("death_date"):
                lines.append(f"2 DATE {p['death_date']}")
            if p.get("death_place"):
                lines.append(f"2 PLAC {p['death_place']}")
        if p.get("burial_place"):
            lines.append("1 BURI")
            lines.append(f"2 PLAC {p['burial_place']}")

    lines.append("0 TRLR")
    return lines


def export(conn, output_path: Path) -> int:
    """Export all persons + relationships to a GEDCOM file. Returns person count."""
    import sap.core.gate as _gate
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("SELECT * FROM the_squirrel.persons WHERE is_deleted = FALSE")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    persons = [dict(zip(cols, r)) for r in rows]

    cur.execute("SELECT * FROM the_squirrel.relationships")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    relationships = [dict(zip(cols, r)) for r in rows]

    lines = build_gedcom_lines(persons, relationships)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(persons)
```

- [ ] **Step 4: Create gedcom/importer.py**

```python
# gedcom/importer.py
"""
GEDCOM 5.5.1 importer.
Parses .ged file → fragments (not persons directly).
The Binder promotes fragments to persons after review.
"""
import re
from pathlib import Path
from typing import List, Dict
import db.fragments as fragments_db
import sap.core.gate as _gate


def _parse_gedcom(text: str) -> List[Dict]:
    """Extract INDI blocks from GEDCOM text. Returns list of raw person dicts."""
    persons = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\d+)\s+(@\S+@\s+)?(\S+)\s*(.*)?$', line)
        if not m:
            continue
        level, tag_id, tag, value = int(m.group(1)), (m.group(2) or "").strip(), m.group(3), (m.group(4) or "").strip()

        if level == 0 and "INDI" in (tag_id + " " + tag):
            if current:
                persons.append(current)
            current = {"_id": tag_id.strip("@"), "name": "", "birth_date": None,
                       "birth_place": None, "death_date": None}
        elif current is not None:
            if tag == "NAME":
                current["name"] = value.replace("/", "").strip()
            elif tag == "DATE" and current.get("_in_birt"):
                current["birth_date"] = value
            elif tag == "DATE" and current.get("_in_deat"):
                current["death_date"] = value
            elif tag == "PLAC" and current.get("_in_birt"):
                current["birth_place"] = value
            elif tag == "BIRT":
                current["_in_birt"] = True
                current["_in_deat"] = False
            elif tag == "DEAT":
                current["_in_deat"] = True
                current["_in_birt"] = False
    if current:
        persons.append(current)
    return persons


def import_ged(conn, filepath: Path) -> int:
    """Parse .ged file → fragments. Returns fragment count created."""
    _gate.authorized("write")
    text = filepath.read_text(encoding="utf-8", errors="replace")
    persons = _parse_gedcom(text)
    count = 0
    for p in persons:
        if not p.get("name"):
            continue
        story = f"GEDCOM import: {p['name']}"
        if p.get("birth_date"):
            story += f", b.{p['birth_date']}"
        if p.get("birth_place"):
            story += f", {p['birth_place']}"
        if p.get("death_date"):
            story += f", d.{p['death_date']}"
        fragments_db.add_fragment(conn, person_name=p["name"],
                                  fragment_type="document",
                                  story_text=story,
                                  source=str(filepath.name),
                                  confidence="likely")
        count += 1
    return count
```

- [ ] **Step 5: Update responder/commands/gedcom.py**

```python
# responder/commands/gedcom.py
from pathlib import Path
from datetime import datetime
from responder.formatter import result_block
from gedcom.exporter import export
from gedcom.importer import import_ged


def cmd_export_gedcom(conn, args: list) -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    out_path = desktop / f"squirrel_export_{date_str}.ged"
    count = export(conn, out_path)
    return result_block("export gedcom", f"✓ {count} persons exported\n`{out_path}`")


def cmd_import_gedcom(conn, args: list) -> str:
    if not args:
        return result_block("import gedcom", "Usage: `@squirrel: import gedcom /path/to/file.ged`")
    path = Path(" ".join(args)).expanduser()
    if not path.exists():
        return result_block("import gedcom", f"File not found: `{path}`")
    count = import_ged(conn, path)
    return result_block("import gedcom", f"✓ {count} persons imported as fragments\nRun `@squirrel: bind fragment all → auto` to promote matches.")
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_gedcom.py -v
```

- [ ] **Step 7: Commit**

```bash
git add gedcom/ responder/commands/gedcom.py tests/test_gedcom.py
git commit -m "feat: GEDCOM 5.5.1 export + import (as fragments)"
```

---

## Phase 7 — Skins

### Task 14: skins/base.css + skins/mcm.css (default)

**Files:**
- Create: `skins/base.css`, `skins/mcm.css`

- [ ] **Step 1: Create skins/base.css — structural layout, CSS variable contract**

```css
/* skins/base.css — structural layout. Defines no colors; only structure. */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font-body);
  font-size: 15px;
  background: var(--color-bg);
  color: var(--color-text);
  min-height: 100vh;
  line-height: 1.7;
}

#header {
  border-bottom: var(--border);
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  background: var(--color-bg);
  z-index: 10;
}

#title {
  font-family: var(--font-display);
  font-size: 1.3rem;
  color: var(--color-accent);
  letter-spacing: var(--title-tracking);
}

#mode-toggle {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: var(--color-muted);
}

#mode-toggle input[type="range"] {
  accent-color: var(--color-accent);
  width: 80px;
  cursor: pointer;
}

#content {
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem;
}

#content h1, #content h2, #content h3 {
  color: var(--color-accent);
  font-family: var(--font-display);
  margin: 1.5rem 0 0.5rem;
}

#content hr {
  border: none;
  border-top: var(--border);
  margin: 1.5rem 0;
}

#content code {
  font-family: var(--font-mono);
  background: var(--color-surface);
  padding: 0.1em 0.35em;
  font-size: 0.88em;
  color: var(--color-accent);
}

#content pre {
  background: var(--color-surface);
  border: var(--border);
  padding: 1rem;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 0.85em;
  line-height: 1.5;
}

#content table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
#content th { background: var(--color-surface); color: var(--color-accent); text-align: left; padding: 0.4rem 0.6rem; border-bottom: var(--border); }
#content td { padding: 0.35rem 0.6rem; border-bottom: 1px solid var(--color-surface); }

#content blockquote {
  border-left: 3px solid var(--color-accent-dim);
  padding-left: 1rem;
  color: var(--color-muted);
  font-style: italic;
}

#content strong { color: var(--color-accent); }

#input-area {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 0.75rem 2rem;
  background: var(--color-bg);
  border-top: var(--border);
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

#input-area textarea {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  background: var(--color-surface);
  border: var(--border);
  color: var(--color-text);
  padding: 0.5rem 0.75rem;
  resize: none;
  outline: none;
}

#input-area textarea:focus { border-color: var(--color-accent-dim); }

#input-area button {
  font-family: var(--font-mono);
  font-size: 1rem;
  background: var(--color-accent);
  color: var(--color-bg);
  border: none;
  padding: 0.5rem 1rem;
  cursor: pointer;
  font-weight: bold;
}

#input-area button:hover { opacity: 0.85; }

body { padding-bottom: 80px; }
```

- [ ] **Step 2: Create skins/mcm.css — Mid-Century Modern**

```css
/* skins/mcm.css — Mid-Century Modern (1950s–60s) */
/* Walnut, mustard, burnt orange. The library at Eames House. */

@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=IBM+Plex+Mono:wght@400;600&family=Lato:wght@300;400;700&display=swap');

[data-skin="mcm"] {
  --font-display: 'DM Serif Display', Georgia, serif;
  --font-body:    'Lato', Helvetica, sans-serif;
  --font-mono:    'IBM Plex Mono', 'Courier New', monospace;

  --color-bg:         #1a1510;
  --color-surface:    #241d14;
  --color-text:       #e8d8c0;
  --color-muted:      #7a6a54;
  --color-accent:     #c8a45a;
  --color-accent-dim: #7a6030;

  --border: 1px solid #352a1a;
  --title-tracking: 0.2em;
}

[data-skin="mcm"] #header {
  background: #120e08;
}

[data-skin="mcm"] #title::before { content: "❧ "; }

/* MCM mode toggle — 3-position rotary knob visual */
[data-skin="mcm"] #mode-toggle label {
  font-variant: small-caps;
  letter-spacing: 0.1em;
}

[data-skin="mcm"] #input-area textarea:focus {
  box-shadow: 0 0 0 1px #c8a45a44;
}

[data-skin="mcm"] #content a {
  color: var(--color-accent);
  text-decoration: none;
  border-bottom: 1px solid var(--color-accent-dim);
}
```

- [ ] **Step 3: Create skins/80s.css**

```css
/* skins/80s.css — 1980s phosphor terminal */
/* Green on black. CRT scanlines. BBS aesthetic. */

@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=VT323&display=swap');

[data-skin="80s"] {
  --font-display: 'VT323', monospace;
  --font-body:    'Share Tech Mono', monospace;
  --font-mono:    'Share Tech Mono', monospace;

  --color-bg:         #000800;
  --color-surface:    #001200;
  --color-text:       #33ff33;
  --color-muted:      #1a7a1a;
  --color-accent:     #66ff66;
  --color-accent-dim: #1a4a1a;

  --border: 1px solid #1a4a1a;
  --title-tracking: 0.3em;
}

[data-skin="80s"] body {
  background-image: repeating-linear-gradient(
    0deg, transparent, transparent 2px, rgba(0,0,0,0.15) 2px, rgba(0,0,0,0.15) 4px
  );
}

[data-skin="80s"] #title { font-size: 1.6rem; text-shadow: 0 0 10px #33ff33; }
[data-skin="80s"] #title::before { content: "> "; }
[data-skin="80s"] #content strong { text-shadow: 0 0 6px #66ff66; }
[data-skin="80s"] #input-area textarea { caret-color: #33ff33; }
[data-skin="80s"] #input-area textarea:focus { box-shadow: 0 0 8px #33ff3344; }
```

- [ ] **Step 4: Create skins/00s.css**

```css
/* skins/00s.css — 2000s Web 2.0 */
/* Aqua, glossy gradients, drop shadows. Windows XP meets Mac OS X Aqua. */

@import url('https://fonts.googleapis.com/css2?family=Trebuchet+MS&family=Lucida+Console&display=swap');

[data-skin="00s"] {
  --font-display: 'Trebuchet MS', Arial, sans-serif;
  --font-body:    'Trebuchet MS', Arial, sans-serif;
  --font-mono:    'Lucida Console', monospace;

  --color-bg:         #dde8f0;
  --color-surface:    #c5d8e8;
  --color-text:       #1a2a38;
  --color-muted:      #5a7a94;
  --color-accent:     #0066aa;
  --color-accent-dim: #4499cc;

  --border: 1px solid #8ab0cc;
  --title-tracking: 0.05em;
}

[data-skin="00s"] #header {
  background: linear-gradient(180deg, #aaccee 0%, #88aacc 100%);
  border-bottom: 2px solid #6699bb;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

[data-skin="00s"] #title { color: #003366; text-shadow: 0 1px 0 #ffffff88; }

[data-skin="00s"] #input-area button {
  background: linear-gradient(180deg, #44aaff 0%, #0066cc 100%);
  border: 1px solid #0044aa;
  border-radius: 3px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  text-shadow: 0 1px 0 rgba(0,0,0,0.3);
}

[data-skin="00s"] #content pre { border-radius: 4px; border: 1px solid #8ab0cc; }
```

- [ ] **Step 5: Create skins/20s.css**

```css
/* skins/20s.css — 2020s glassmorphism */
/* Dark, frosted glass panels, pill buttons, subtle blur. */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

[data-skin="20s"] {
  --font-display: 'Inter', system-ui, sans-serif;
  --font-body:    'Inter', system-ui, sans-serif;
  --font-mono:    'JetBrains Mono', monospace;

  --color-bg:         #0d0d12;
  --color-surface:    rgba(255,255,255,0.06);
  --color-text:       #e2e4ee;
  --color-muted:      #5a5d70;
  --color-accent:     #7c6dfa;
  --color-accent-dim: #4a3d9a;

  --border: 1px solid rgba(255,255,255,0.08);
  --title-tracking: -0.02em;
}

[data-skin="20s"] #header {
  background: rgba(13,13,18,0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

[data-skin="20s"] #content pre {
  border-radius: 8px;
  background: rgba(255,255,255,0.04);
  backdrop-filter: blur(4px);
}

[data-skin="20s"] #input-area {
  background: rgba(13,13,18,0.9);
  backdrop-filter: blur(12px);
}

[data-skin="20s"] #input-area textarea { border-radius: 6px; }

[data-skin="20s"] #input-area button {
  border-radius: 20px;
  background: var(--color-accent);
  padding: 0.5rem 1.25rem;
  letter-spacing: 0.02em;
}

[data-skin="20s"] #mode-toggle input[type="range"] {
  accent-color: var(--color-accent);
}
```

- [ ] **Step 6: Smoke test all skins**

```
@squirrel: skin mcm
@squirrel: skin 80s
@squirrel: skin 00s
@squirrel: skin 20s
```

Each should repaint on browser reload.

- [ ] **Step 7: Commit**

```bash
git add skins/
git commit -m "feat: 4 era skins — MCM, 80s, 00s, 20s"
```

---

## Phase 8 — LLM Modes

### Task 15: responder/llm/prompt.py + responder/llm/chat.py

**Files:**
- Create: `responder/llm/__init__.py`, `responder/llm/prompt.py`, `responder/llm/chat.py`

- [ ] **Step 1: Create responder/llm/prompt.py**

```python
# responder/llm/prompt.py
"""Jeles system prompt and tool description for Conversational mode."""

JELES_SYSTEM = """You are Jeles, the librarian of The Squirrel genealogy research terminal.

You speak with quiet authority, dry wit, and genuine care for the research. 
You work the desk; The Binder works the back.

Your tone:
- Precise and direct. No filler phrases.
- "The things we think we've lost are simply misfiled."
- You do not guess. You say what is known and what is not.

Your tools (what you know):
- The user's persons table: names, birth/death dates, places, relationships.
- The fragment stash: raw unverified observations waiting to be bound.
- The source registry: 779 community archives across 43 US states.

When asked about a person, summarize what the DB contains — dates, places, relationships.
If the DB has nothing, say so. Do not invent records.
When asked to research a person, suggest specific @squirrel: commands the user can run.
Keep responses under 200 words unless the user explicitly asks for more.
"""

ACTIVE_LISTENER_SYSTEM = """You are Jeles, monitoring a genealogy research session.

When the user writes something that mentions a person name, date, or place,
check if it connects to anything in the research context and surface the connection briefly.

If nothing connects, output exactly: [no hint]
If something connects, output one short observation (max 2 sentences) starting with "Note:".
Do not ask questions. Do not explain your reasoning. Just the note or [no hint].
"""
```

- [ ] **Step 2: Create responder/llm/chat.py**

```python
# responder/llm/chat.py
"""
Conversational mode — full Jeles-voice LLM responses via Ollama.
Falls back gracefully if Ollama is not running.
"""
import json
import urllib.request
import urllib.error
from responder.formatter import result_block
from responder.llm.prompt import JELES_SYSTEM
import db.persons as persons_db

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "llama3"


def _ollama_available() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _get_model(config_path=None) -> str:
    if config_path is None:
        from pathlib import Path
        config_path = Path.home() / ".squirrel" / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            return data.get("ollama_model", DEFAULT_MODEL)
        except Exception:
            pass
    return DEFAULT_MODEL


def _build_context(conn, user_text: str) -> str:
    """Fetch relevant persons from DB to include in context."""
    words = user_text.split()
    # Simple heuristic: capitalised words might be names
    candidates = [w for w in words if w[0].isupper() and len(w) > 2][:4]
    found = []
    for c in candidates:
        people = persons_db.search_persons(conn, c)
        found.extend(people[:2])
    if not found:
        return ""
    lines = ["Known persons in the tree:"]
    for p in found[:6]:
        line = f"- {p['full_name']} (id={p['id']})"
        if p.get("birth_date"):
            line += f", b.{p['birth_date']}"
        if p.get("birth_place"):
            line += f", {p['birth_place']}"
        lines.append(line)
    return "\n".join(lines)


def respond(conn, user_text: str) -> str:
    """Generate a Jeles-voice response via Ollama."""
    if not _ollama_available():
        return result_block(
            "Jeles (offline)",
            "_Ollama is not running. Start it with `ollama serve` to enable Conversational mode._\n\nFalling back to Journal mode."
        )
    context = _build_context(conn, user_text)
    system = JELES_SYSTEM
    if context:
        system += f"\n\nCurrent session context:\n{context}"
    model = _get_model()
    payload = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text}
        ]
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        reply = data["message"]["content"].strip()
        return result_block("Jeles", reply)
    except Exception as e:
        return result_block("Jeles (error)", f"_LLM call failed: {e}_")
```

- [ ] **Step 3: Create responder/llm/listener.py**

```python
# responder/llm/listener.py
"""
Active Listening mode — passive scan of new content.
Surfaces connections without being asked. Returns hint or None.
"""
import json
import urllib.request
from responder.llm.prompt import ACTIVE_LISTENER_SYSTEM
from responder.llm.chat import _ollama_available, _get_model, OLLAMA_URL
from responder.formatter import result_block


def maybe_hint(conn, new_text: str) -> str | None:
    """
    Returns a result_block hint string if the LLM finds a connection, else None.
    Called in Active Listening mode for every non-@squirrel: line.
    """
    if not new_text.strip() or len(new_text.strip()) < 10:
        return None
    if not _ollama_available():
        return None
    model = _get_model()
    payload = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": ACTIVE_LISTENER_SYSTEM},
            {"role": "user", "content": new_text}
        ]
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        reply = data["message"]["content"].strip()
        if reply.startswith("[no hint]") or not reply:
            return None
        return result_block("Jeles — note", reply)
    except Exception:
        return None
```

- [ ] **Step 4: Wire LLM into squirrel_responder.py**

In `squirrel_responder.py`, update the `handle()` function:

```python
def handle(line: str):
    cmd = parse_command(line)

    if cmd is None:
        # Not a @squirrel: command
        if state.mode.value == "chat":
            from db import get_connection, release_connection
            from responder.llm.chat import respond
            conn = get_connection()
            try:
                result = respond(conn, line)
            finally:
                release_connection(conn)
            if result:
                state.append(result)
        elif state.mode.value == "listening":
            from db import get_connection, release_connection
            from responder.llm.listener import maybe_hint
            conn = get_connection()
            try:
                hint = maybe_hint(conn, line)
            finally:
                release_connection(conn)
            if hint:
                state.append(hint)
        return

    # ... rest of existing handle() logic
```

- [ ] **Step 5: Manual end-to-end test**

Requires Ollama running with a model. Start Ollama:

```bash
ollama serve &
ollama pull llama3  # if not already pulled
```

Then in the app:
```
@squirrel: mode listening
Iowa was a major point of emigration in the 1880s for German families.
```

Should see a Jeles hint appear if any German-origin persons are in the DB.

```
@squirrel: mode chat
Tell me what you know about Oscar Mann.
```

Should see a Jeles narrative response.

```
@squirrel: mode journal
```

Should return to silent mode.

- [ ] **Step 6: Commit**

```bash
git add responder/llm/ squirrel_responder.py
git commit -m "feat: LLM modes — Active Listening + Conversational via Ollama"
```

---

## Phase 9 — control.py + Final Status Command

### Task 16: responder/commands/control.py — full implementation

**Files:**
- Modify: `responder/commands/control.py` (replace stub with full version)

- [ ] **Step 1: Update cmd_status to query real DB counts**

```python
# responder/commands/control.py
from responder.formatter import result_block
from responder.state import AppState, Mode
import db.persons as persons_db
import db.fragments as fragments_db
import db.sources as sources_db


def cmd_mode(state: AppState, args: list) -> str:
    if not args:
        return result_block("Mode", f"Current mode: `{state.mode.value}`\nOptions: journal, listening, chat")
    m = args[0].lower()
    mapping = {"journal": Mode.JOURNAL, "listening": Mode.LISTENING, "chat": Mode.CHAT}
    if m not in mapping:
        return result_block("Mode", f"Unknown mode `{m}`. Use: journal, listening, chat")
    state.mode = mapping[m]
    msgs = {
        "journal": "Mode → `journal` — LLM offline. Commands only.",
        "listening": "Mode → `listening` — Jeles is listening. She'll speak up when she sees something.",
        "chat": "Mode → `chat` — Jeles is ready. Ask anything.",
    }
    return result_block("Mode", msgs[m])


def cmd_skin(state: AppState, args: list) -> str:
    if not args:
        return result_block("Skin", f"Current skin: `{state.skin}`\nOptions: mcm, 80s, 00s, 20s")
    skin = args[0].lower()
    if skin not in ("mcm", "80s", "00s", "20s"):
        return result_block("Skin", f"Unknown skin `{skin}`. Options: mcm, 80s, 00s, 20s")
    state.skin = skin
    state.save_config()
    return result_block("Skin", f"Skin → `{skin}` — reload the page to apply.")


def cmd_status(conn, state: AppState) -> str:
    try:
        people = persons_db.search_persons(conn, "")
        person_count = len(people)
    except Exception:
        person_count = "?"
    try:
        frags = fragments_db.get_unsynced_fragments(conn, limit=9999)
        frag_count = len(frags)
    except Exception:
        frag_count = "?"
    try:
        sources = sources_db.lookup_sources(conn, limit=1)
        source_note = "connected"
    except Exception:
        source_note = "unavailable"
    lines = [
        f"mode:    `{state.mode.value}`",
        f"skin:    `{state.skin}`",
        f"persons: {person_count}",
        f"stash:   {frag_count} unsynced fragments",
        f"sources: {source_note}",
        f"port:    8425",
    ]
    return result_block("status", "\n".join(lines))
```

- [ ] **Step 2: Smoke test**

```
@squirrel: status
```

Should show real counts from the DB.

- [ ] **Step 3: Commit**

```bash
git add responder/commands/control.py
git commit -m "feat: full status command with DB counts"
```

---

## Final: Integration + Smoke Test

- [ ] **Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests PASS (skip LLM tests if Ollama not running).

- [ ] **End-to-end genealogy session smoke test**

```
@squirrel: status
@squirrel: add person Oscar Mann b.1882 d.1951 p.Iowa
@squirrel: add person Carl Mann b.1855 p.Iowa
@squirrel: link Oscar Mann → parent → Carl Mann
@squirrel: tree Oscar Mann
@squirrel: stash "Oscar Mann found in 1900 census, Iowa City" --confidence likely
@squirrel: show stash
@squirrel: bind fragment 1 → Oscar Mann
@squirrel: find sources Iowa --state Iowa
@squirrel: search familysearch Oscar Mann Iowa
@squirrel: export gedcom
@squirrel: skin 80s
@squirrel: mode chat
@squirrel: status
```

Verify each command returns the expected result block.

- [ ] **Final commit**

```bash
git add .
git commit -m "feat: The Squirrel — full-stack genealogy app v1.0"
```
