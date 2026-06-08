# story-timeline v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild story-timeline as an open node graph writing tool — any entity type, user-defined, with Willow-backed edges, TUI and web surfaces, session composites on close, and automatic migration of v1 events.

**Architecture:** SQLite stores nodes (`id`, user-defined `type`, JSON `fields`); `WillowStore` (imported from `willow-1.9/core/willow_store.py`) stores graph edges scoped to `user-{uuid}/story-timeline/_graph/edges`; TUI (Textual) and web (Python stdlib `http.server`) are full peers reading the same backend. On first run, v1 `events` rows are migrated to nodes of type `"event"` automatically.

**Tech Stack:** Python 3.10+, Textual ≥0.47, stdlib (sqlite3, http.server, json, threading, webbrowser), willow-1.9/core/willow_store.py (direct import via `WILLOW_CORE` env var)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `apps/story-timeline/timeline_db.py` | **REWRITE** | SQLite: nodes CRUD, search, type listing |
| `apps/story-timeline/willow_edges.py` | **CREATE** | WillowStore wrapper: add/list/delete edges, orphan reconciliation |
| `apps/story-timeline/safe_integration.py` | **CREATE** | User UUID from `~/.willow/user_identity.json`; write session composite atom |
| `apps/story-timeline/migrate.py` | **CREATE** | Detect v1 `events` table; convert rows to v2 nodes of type `"event"` |
| `apps/story-timeline/app.py` | **REWRITE** | TUI (Textual): NodeList, CreateNode, LinkNodes, NodeDetail screens; boot orchestrator |
| `apps/story-timeline/web.py` | **CREATE** | stdlib HTTP server; JSON API; inline HTML+JS force-graph UI |
| `apps/story-timeline/safe-app-manifest.json` | **MODIFY** | Add SAP permission declarations |
| `apps/story-timeline/requirements.txt` | **UNCHANGED** | `textual>=0.47.0` covers all deps |
| `tests/story-timeline/conftest.py` | **CREATE** | Shared pytest fixtures (tmp DB path, mock UUID) |
| `tests/story-timeline/test_timeline_db.py` | **CREATE** | Node CRUD + search tests |
| `tests/story-timeline/test_willow_edges.py` | **CREATE** | Edge add/list/reconcile tests (real WillowStore in tmp dir) |
| `tests/story-timeline/test_migrate.py` | **CREATE** | V1→V2 migration detection + conversion tests |
| `tests/story-timeline/test_safe_integration.py` | **CREATE** | UUID read + session composite write tests |
| `tests/story-timeline/test_web.py` | **CREATE** | HTTP endpoint tests |

---

## Task 1: Rewrite timeline_db.py — open nodes schema

**Files:**
- Modify: `apps/story-timeline/timeline_db.py`
- Test: `tests/story-timeline/test_timeline_db.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/story-timeline/test_timeline_db.py`:

```python
import json
import pytest
import sys
import os

# Run tests against a temp DB, not the user's real one
@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    # Re-import so DB_PATH picks up the env var
    if "timeline_db" in sys.modules:
        del sys.modules["timeline_db"]
    sys.path.insert(0, str(os.path.dirname(__file__) + "/../../apps/story-timeline"))

import importlib
import timeline_db as db_mod

@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    # Reload module so DB_PATH is fresh
    import importlib
    import timeline_db
    importlib.reload(timeline_db)
    return timeline_db

def test_add_and_get_node(db):
    node_id = db.add_node(type_="character", fields={"name": "Alice", "age": "30"})
    node = db.get_node(node_id)
    assert node["type"] == "character"
    assert json.loads(node["fields"])["name"] == "Alice"

def test_get_nodes_by_type(db):
    db.add_node(type_="character", fields={"name": "Alice"})
    db.add_node(type_="location", fields={"name": "Castle"})
    chars = db.get_nodes(type_="character")
    assert len(chars) == 1
    assert json.loads(chars[0]["fields"])["name"] == "Alice"

def test_get_all_nodes(db):
    db.add_node(type_="character", fields={"name": "Alice"})
    db.add_node(type_="event", fields={"summary": "Battle"})
    all_nodes = db.get_nodes()
    assert len(all_nodes) == 2

def test_update_node(db):
    node_id = db.add_node(type_="character", fields={"name": "Alice"})
    db.update_node(node_id, fields={"name": "Alice Liddell", "age": "10"})
    node = db.get_node(node_id)
    assert json.loads(node["fields"])["name"] == "Alice Liddell"

def test_delete_node(db):
    node_id = db.add_node(type_="character", fields={"name": "Temp"})
    assert db.delete_node(node_id) is True
    assert db.get_node(node_id) is None

def test_search_nodes(db):
    db.add_node(type_="character", fields={"name": "Gandalf", "role": "wizard"})
    db.add_node(type_="character", fields={"name": "Frodo", "role": "hobbit"})
    results = db.search_nodes("wizard")
    assert len(results) == 1
    assert json.loads(results[0]["fields"])["name"] == "Gandalf"

def test_get_types(db):
    db.add_node(type_="character", fields={})
    db.add_node(type_="location", fields={})
    db.add_node(type_="character", fields={})
    types = db.get_types()
    assert set(types) == {"character", "location"}

def test_node_id_is_uuid_format(db):
    import re
    node_id = db.add_node(type_="event", fields={"summary": "Test"})
    assert re.match(r"[0-9a-f-]{36}", node_id)
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_timeline_db.py -v 2>&1 | head -30
```

Expected: import errors or AttributeError — `add_node` not defined.

- [ ] **Step 1.3: Rewrite timeline_db.py**

Replace the entire file with:

```python
"""
timeline_db.py — SQLite backend for story-timeline v2.

Open node graph: any entity type, user-defined fields.
DB_PATH is overridable via STORY_TIMELINE_DB env var for testing.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(
    os.environ.get("STORY_TIMELINE_DB",
    str(Path.home() / ".willow" / "store" / "story-timeline" / "timeline.db"))
)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id       TEXT PRIMARY KEY,
            type     TEXT NOT NULL,
            fields   TEXT NOT NULL DEFAULT '{}',
            created  TEXT DEFAULT (datetime('now')),
            updated  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def add_node(type_: str, fields: dict) -> str:
    node_id = str(uuid.uuid4())
    conn = _conn()
    conn.execute(
        "INSERT INTO nodes (id, type, fields) VALUES (?, ?, ?)",
        (node_id, type_, json.dumps(fields))
    )
    conn.commit()
    conn.close()
    return node_id


def get_node(node_id: str) -> Optional[dict]:
    conn = _conn()
    row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_nodes(type_: Optional[str] = None) -> list[dict]:
    conn = _conn()
    if type_:
        rows = conn.execute(
            "SELECT * FROM nodes WHERE type = ? ORDER BY created ASC", (type_,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM nodes ORDER BY created ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_node(node_id: str, fields: dict) -> bool:
    now = datetime.now().isoformat()
    conn = _conn()
    cur = conn.execute(
        "UPDATE nodes SET fields = ?, updated = ? WHERE id = ?",
        (json.dumps(fields), now, node_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_node(node_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def search_nodes(query: str) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM nodes WHERE lower(fields) LIKE lower(?) OR lower(type) LIKE lower(?)",
        (f"%{query}%", f"%{query}%")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_types() -> list[str]:
    conn = _conn()
    rows = conn.execute(
        "SELECT DISTINCT type FROM nodes ORDER BY type"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_node_ids() -> list[str]:
    conn = _conn()
    rows = conn.execute("SELECT id FROM nodes").fetchall()
    conn.close()
    return [r[0] for r in rows]
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_timeline_db.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add apps/story-timeline/timeline_db.py tests/story-timeline/test_timeline_db.py
git commit -m "feat(story-timeline): v2 open nodes schema in timeline_db"
```

---

## Task 2: willow_edges.py — Willow edge layer

**Files:**
- Create: `apps/story-timeline/willow_edges.py`
- Test: `tests/story-timeline/test_willow_edges.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/story-timeline/test_willow_edges.py`:

```python
import json
import os
import sys
import pytest

sys.path.insert(0, str(os.path.dirname(__file__) + "/../../apps/story-timeline"))

# Point WillowStore to a tmp dir so tests don't touch real store
@pytest.fixture()
def edges(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "willow"))
    monkeypatch.setenv("WILLOW_CORE",
        "~/github/willow-1.9/core")
    import willow_edges
    import importlib
    importlib.reload(willow_edges)
    return willow_edges

TEST_UUID = "test-user-0000"

def test_add_and_list_edge(edges):
    edges.add_edge("node-A", "node-B", "related_to", uuid=TEST_UUID)
    result = edges.edges_for("node-A", uuid=TEST_UUID)
    assert len(result) == 1
    assert result[0]["relation"] == "related_to"

def test_edges_for_returns_both_directions(edges):
    edges.add_edge("node-X", "node-Y", "causes", uuid=TEST_UUID)
    from_x = edges.edges_for("node-X", uuid=TEST_UUID)
    from_y = edges.edges_for("node-Y", uuid=TEST_UUID)
    assert len(from_x) == 1
    assert len(from_y) == 1
    assert from_x[0]["from_id"] == "node-X"

def test_delete_edge(edges):
    edge_id = edges.add_edge("A", "B", "knows", uuid=TEST_UUID)
    assert edges.delete_edge(edge_id, uuid=TEST_UUID) is True
    assert edges.edges_for("A", uuid=TEST_UUID) == []

def test_reconcile_orphans_removes_stale(edges):
    edges.add_edge("real-node", "ghost-node", "links_to", uuid=TEST_UUID)
    # Only real-node exists
    removed = edges.reconcile_orphans(["real-node"], uuid=TEST_UUID)
    assert removed == 1
    assert edges.edges_for("real-node", uuid=TEST_UUID) == []

def test_reconcile_orphans_keeps_valid(edges):
    edges.add_edge("node-1", "node-2", "mentions", uuid=TEST_UUID)
    removed = edges.reconcile_orphans(["node-1", "node-2"], uuid=TEST_UUID)
    assert removed == 0
    assert len(edges.edges_for("node-1", uuid=TEST_UUID)) == 1

def test_graceful_degradation_when_willow_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_CORE", str(tmp_path / "nonexistent"))
    import willow_edges
    import importlib
    importlib.reload(willow_edges)
    # Should not raise — silently no-ops
    result = willow_edges.add_edge("a", "b", "rel", uuid=TEST_UUID)
    assert result is None
    assert willow_edges.edges_for("a", uuid=TEST_UUID) == []
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_willow_edges.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `willow_edges` not found.

- [ ] **Step 2.3: Create willow_edges.py**

```python
"""
willow_edges.py — Willow edge layer for story-timeline v2.

Wraps WillowStore directly (imported from willow-1.9/core/willow_store.py).
All edges scoped to user-{uuid}/story-timeline/_graph/edges.
Degrades gracefully to no-op when Willow is unavailable.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

_WILLOW_CORE = os.environ.get(
    "WILLOW_CORE",
    str(Path.home() / "github" / "willow-1.9" / "core")
)
if _WILLOW_CORE not in sys.path:
    sys.path.insert(0, _WILLOW_CORE)

try:
    from willow_store import WillowStore
    _STORE = WillowStore()
    _WILLOW_AVAILABLE = True
except Exception:
    _STORE = None
    _WILLOW_AVAILABLE = False


def _collection(uuid: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    return f"user-{safe}/story-timeline/_graph/edges"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "-", value)


def add_edge(from_id: str, to_id: str, relation: str,
             context: str = "", uuid: Optional[str] = None) -> Optional[str]:
    if not _WILLOW_AVAILABLE or not uuid:
        return None
    edge_id = f"{_safe_id(from_id)}__{_safe_id(relation)}__{_safe_id(to_id)}"
    record = {
        "id": edge_id,
        "from_id": from_id,
        "to_id": to_id,
        "relation": relation,
        "context": context,
    }
    _STORE.put(_collection(uuid), record, record_id=edge_id)
    return edge_id


def edges_for(node_id: str, uuid: Optional[str] = None) -> list[dict]:
    if not _WILLOW_AVAILABLE or not uuid:
        return []
    try:
        col = _collection(uuid)
        store = _STORE
        conn = store._conn(col)
        rows = conn.execute(
            "SELECT data FROM records WHERE deleted = 0"
        ).fetchall()
        conn.close()
        results = []
        for row in rows:
            edge = json.loads(row[0])
            if edge.get("from_id") == node_id or edge.get("to_id") == node_id:
                results.append(edge)
        return results
    except Exception:
        return []


def delete_edge(edge_id: str, uuid: Optional[str] = None) -> bool:
    if not _WILLOW_AVAILABLE or not uuid:
        return False
    try:
        col = _collection(uuid)
        store = _STORE
        conn = store._conn(col)
        cur = conn.execute(
            "UPDATE records SET deleted = 1 WHERE id = ?", (edge_id,)
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0
    except Exception:
        return False


def reconcile_orphans(valid_node_ids: list[str], uuid: Optional[str] = None) -> int:
    """Soft-delete edges whose from_id or to_id is not in valid_node_ids.
    Returns count of edges removed."""
    if not _WILLOW_AVAILABLE or not uuid:
        return 0
    valid = set(valid_node_ids)
    removed = 0
    try:
        col = _collection(uuid)
        store = _STORE
        conn = store._conn(col)
        rows = conn.execute(
            "SELECT id, data FROM records WHERE deleted = 0"
        ).fetchall()
        for row in rows:
            edge = json.loads(row[1])
            if edge.get("from_id") not in valid or edge.get("to_id") not in valid:
                conn.execute("UPDATE records SET deleted = 1 WHERE id = ?", (row[0],))
                removed += 1
        conn.commit()
        conn.close()
    except Exception:
        pass
    return removed
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_willow_edges.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 2.5: Commit**

```bash
git add apps/story-timeline/willow_edges.py tests/story-timeline/test_willow_edges.py
git commit -m "feat(story-timeline): Willow edge layer with graceful degradation"
```

---

## Task 3: safe_integration.py — user identity + session composite

**Files:**
- Create: `apps/story-timeline/safe_integration.py`
- Test: `tests/story-timeline/test_safe_integration.py`

- [ ] **Step 3.1: Write the failing tests**

```python
# tests/story-timeline/test_safe_integration.py
import json
import os
import sys
import pytest

sys.path.insert(0, str(os.path.dirname(__file__) + "/../../apps/story-timeline"))

@pytest.fixture()
def si(monkeypatch, tmp_path):
    import safe_integration
    import importlib
    importlib.reload(safe_integration)
    return safe_integration

def test_get_user_uuid_returns_uuid_when_file_exists(si, tmp_path, monkeypatch):
    identity_file = tmp_path / "user_identity.json"
    identity_file.write_text(json.dumps({"uuid": "abc-123"}))
    monkeypatch.setattr(si, "_IDENTITY_PATH", identity_file)
    assert si.get_user_uuid() == "abc-123"

def test_get_user_uuid_returns_none_when_missing(si, tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_IDENTITY_PATH", tmp_path / "nonexistent.json")
    assert si.get_user_uuid() is None

def test_get_user_uuid_returns_none_on_malformed_json(si, tmp_path, monkeypatch):
    bad_file = tmp_path / "user_identity.json"
    bad_file.write_text("not json")
    monkeypatch.setattr(si, "_IDENTITY_PATH", bad_file)
    assert si.get_user_uuid() is None

def test_write_session_composite(si, tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "willow"))
    monkeypatch.setenv("WILLOW_CORE",
        "~/github/willow-1.9/core")
    import importlib
    importlib.reload(si)
    stats = {
        "nodes_created": 3,
        "edges_created": 2,
        "types_used": ["character", "event"],
        "session_duration_s": 120,
    }
    result = si.write_session_composite(stats=stats, uuid="test-uuid-0001")
    assert result is True

def test_write_session_composite_noop_without_willow(si, tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_CORE", str(tmp_path / "nonexistent"))
    import importlib
    importlib.reload(si)
    # Should not raise
    result = si.write_session_composite(stats={}, uuid="test-uuid")
    assert result is False
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_safe_integration.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `safe_integration` not found.

- [ ] **Step 3.3: Create safe_integration.py**

```python
"""
safe_integration.py — User identity + session composite for story-timeline v2.

Reads user UUID from ~/.willow/user_identity.json (provisioned by willow-seed).
Writes a structured session composite atom to Willow on app close.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_IDENTITY_PATH = Path.home() / ".willow" / "user_identity.json"

_WILLOW_CORE = os.environ.get(
    "WILLOW_CORE",
    str(Path.home() / "github" / "willow-1.9" / "core")
)
if _WILLOW_CORE not in sys.path:
    sys.path.insert(0, _WILLOW_CORE)

try:
    from willow_store import WillowStore
    _STORE = WillowStore()
    _WILLOW_AVAILABLE = True
except Exception:
    _STORE = None
    _WILLOW_AVAILABLE = False


def get_user_uuid() -> Optional[str]:
    try:
        data = json.loads(_IDENTITY_PATH.read_text())
        return data.get("uuid") or None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_session_composite(stats: dict, uuid: str) -> bool:
    if not _WILLOW_AVAILABLE or not uuid:
        return False
    import re
    safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    collection = f"user-{safe_uuid}/story-timeline/atoms"
    atom_id = f"session-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    record = {
        "id": atom_id,
        "type": "session_composite",
        "app_id": "story-timeline",
        "user_uuid": uuid,
        "created_at": datetime.now().isoformat(),
        **stats,
    }
    try:
        _STORE.put(collection, record, record_id=atom_id)
        return True
    except Exception:
        return False
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_safe_integration.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 3.5: Commit**

```bash
git add apps/story-timeline/safe_integration.py tests/story-timeline/test_safe_integration.py
git commit -m "feat(story-timeline): user identity + session composite"
```

---

## Task 4: migrate.py — v1 events → v2 nodes

**Files:**
- Create: `apps/story-timeline/migrate.py`
- Test: `tests/story-timeline/test_migrate.py`

- [ ] **Step 4.1: Write the failing tests**

```python
# tests/story-timeline/test_migrate.py
import json
import os
import sqlite3
import sys
import pytest

sys.path.insert(0, str(os.path.dirname(__file__) + "/../../apps/story-timeline"))

@pytest.fixture()
def v1_db(tmp_path):
    """Create a v1 database with the old events schema."""
    db_path = tmp_path / "timeline.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            story       TEXT NOT NULL DEFAULT 'default',
            world_date  TEXT NOT NULL,
            location    TEXT DEFAULT '',
            characters  TEXT DEFAULT '[]',
            summary     TEXT NOT NULL,
            tags        TEXT DEFAULT '[]',
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "INSERT INTO events (story, world_date, location, characters, summary) "
        "VALUES (?, ?, ?, ?, ?)",
        ("my-story", "Day 1", "The Inn", '["Alice","Bob"]', "They met.")
    )
    conn.execute(
        "INSERT INTO events (story, world_date, location, characters, summary) "
        "VALUES (?, ?, ?, ?, ?)",
        ("my-story", "Day 2", "The Road", '[]', "They departed.")
    )
    conn.commit()
    conn.close()
    return db_path

@pytest.fixture()
def migrator(tmp_path, v1_db, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(v1_db))
    import migrate
    import importlib
    importlib.reload(migrate)
    return migrate

def test_needs_migration_true_for_v1_db(migrator):
    assert migrator.needs_migration() is True

def test_needs_migration_false_for_v2_db(tmp_path, monkeypatch):
    v2_path = tmp_path / "v2.db"
    conn = sqlite3.connect(str(v2_path))
    conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, type TEXT, fields TEXT, created TEXT, updated TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setenv("STORY_TIMELINE_DB", str(v2_path))
    import migrate
    import importlib
    importlib.reload(migrate)
    assert migrate.needs_migration() is False

def test_run_migration_converts_events_to_nodes(migrator):
    import timeline_db
    import importlib
    importlib.reload(timeline_db)
    count = migrator.run_migration()
    assert count == 2
    nodes = timeline_db.get_nodes(type_="event")
    assert len(nodes) == 2
    # Check first event's fields
    fields = json.loads(nodes[0]["fields"])
    assert fields["story"] == "my-story"
    assert fields["world_date"] == "Day 1"
    assert fields["location"] == "The Inn"
    assert "Alice" in fields["characters"]

def test_run_migration_is_idempotent(migrator):
    import timeline_db
    import importlib
    importlib.reload(timeline_db)
    migrator.run_migration()
    count2 = migrator.run_migration()
    assert count2 == 0  # second run migrates nothing
    nodes = timeline_db.get_nodes(type_="event")
    assert len(nodes) == 2  # still only 2
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_migrate.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `migrate` not found.

- [ ] **Step 4.3: Create migrate.py**

```python
"""
migrate.py — Migrate v1 story-timeline events → v2 open nodes.

Detects old schema by presence of 'events' table.
Converts each event to a node of type 'event' with all old fields preserved
in the JSON fields blob. Idempotent: checks for existing nodes before inserting.
"""
import json
import os
import sqlite3
from pathlib import Path

# DB_PATH from env (same as timeline_db.py so tests can override)
_DB_PATH = Path(
    os.environ.get("STORY_TIMELINE_DB",
    str(Path.home() / ".willow" / "store" / "story-timeline" / "timeline.db"))
)


def needs_migration() -> bool:
    if not _DB_PATH.exists():
        return False
    conn = sqlite3.connect(str(_DB_PATH))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    return "events" in tables and "nodes" not in tables


def run_migration() -> int:
    """Convert v1 events to v2 nodes. Returns count of rows migrated."""
    if not _DB_PATH.exists():
        return 0
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row

    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "events" not in tables:
        conn.close()
        return 0

    # Ensure nodes table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id       TEXT PRIMARY KEY,
            type     TEXT NOT NULL,
            fields   TEXT NOT NULL DEFAULT '{}',
            created  TEXT DEFAULT (datetime('now')),
            updated  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    events = conn.execute("SELECT * FROM events").fetchall()
    migrated = 0
    for e in events:
        import uuid as _uuid
        node_id = f"migrated-event-{e['id']}"
        # Check idempotency
        exists = conn.execute(
            "SELECT id FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if exists:
            continue
        fields = {
            "story": e["story"],
            "world_date": e["world_date"],
            "location": e["location"] or "",
            "characters": json.loads(e["characters"] or "[]"),
            "summary": e["summary"],
            "tags": json.loads(e["tags"] or "[]"),
        }
        conn.execute(
            "INSERT INTO nodes (id, type, fields, created) VALUES (?, ?, ?, ?)",
            (node_id, "event", json.dumps(fields), e["created_at"])
        )
        migrated += 1
    conn.commit()
    conn.close()
    return migrated
```

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_migrate.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 4.5: Commit**

```bash
git add apps/story-timeline/migrate.py tests/story-timeline/test_migrate.py
git commit -m "feat(story-timeline): v1 events → v2 nodes migration"
```

---

## Task 5: web.py — stdlib HTTP server + graph UI

**Files:**
- Create: `apps/story-timeline/web.py`
- Test: `tests/story-timeline/test_web.py`

- [ ] **Step 5.1: Write the failing tests**

```python
# tests/story-timeline/test_web.py
import json
import os
import sys
import threading
import urllib.request
import pytest

sys.path.insert(0, str(os.path.dirname(__file__) + "/../../apps/story-timeline"))

@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import timeline_db
    import importlib
    importlib.reload(timeline_db)
    # Add some test data
    timeline_db.add_node(type_="character", fields={"name": "Alice"})
    timeline_db.add_node(type_="location", fields={"name": "Forest"})

    import web
    importlib.reload(web)
    srv = web.TimelineHTTPServer(port=19876)
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    import time; time.sleep(0.2)
    yield srv
    srv.stop()

def test_root_serves_html(server):
    resp = urllib.request.urlopen("http://localhost:19876/")
    assert resp.status == 200
    content = resp.read().decode()
    assert "<canvas" in content

def test_api_nodes_returns_json(server):
    resp = urllib.request.urlopen("http://localhost:19876/api/nodes")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert len(data) == 2
    types = {n["type"] for n in data}
    assert types == {"character", "location"}

def test_api_edges_returns_json(server):
    resp = urllib.request.urlopen("http://localhost:19876/api/edges")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert isinstance(data, list)

def test_api_node_by_id(server):
    import timeline_db
    nodes = timeline_db.get_nodes()
    node_id = nodes[0]["id"]
    resp = urllib.request.urlopen(f"http://localhost:19876/api/node/{node_id}")
    assert resp.status == 200
    data = json.loads(resp.read())
    assert data["id"] == node_id
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_web.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `web` not found.

- [ ] **Step 5.3: Create web.py**

```python
"""
web.py — Python stdlib HTTP server for story-timeline v2.

Endpoints:
  GET /              → HTML graph page (inline JS force layout)
  GET /api/nodes     → JSON list of all nodes
  GET /api/edges     → JSON list of all edges (if Willow available)
  GET /api/node/{id} → JSON single node

Launch: TimelineHTTPServer(port=8765).start()
"""
import json
import os
import re
import socketserver
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler
from typing import Optional

import timeline_db
import willow_edges
import safe_integration

_USER_UUID: Optional[str] = None


def _set_user_uuid(uuid: Optional[str]) -> None:
    global _USER_UUID
    _USER_UUID = uuid


_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Story Timeline</title>
<style>
  body { margin: 0; background: #1a1a2e; color: #e0e0e0; font-family: monospace; display: flex; }
  #sidebar { width: 260px; padding: 12px; overflow-y: auto; background: #16213e; height: 100vh; box-sizing: border-box; }
  #sidebar h2 { margin: 0 0 8px; color: #a8d8ea; font-size: 14px; }
  #type-filter { width: 100%; background: #0f3460; color: #e0e0e0; border: 1px solid #a8d8ea; padding: 4px; margin-bottom: 8px; }
  .node-item { padding: 4px 6px; cursor: pointer; border-radius: 3px; margin-bottom: 2px; font-size: 12px; }
  .node-item:hover, .node-item.selected { background: #0f3460; }
  .node-type-tag { font-size: 10px; color: #a8d8ea; }
  #main { flex: 1; display: flex; flex-direction: column; }
  canvas { flex: 1; cursor: grab; }
  #detail { padding: 12px; background: #16213e; min-height: 120px; max-height: 200px; overflow-y: auto; font-size: 12px; border-top: 1px solid #0f3460; }
  #detail h3 { margin: 0 0 6px; color: #a8d8ea; }
  .field-row { margin: 2px 0; }
  .field-key { color: #a8d8ea; }
  .edge-item { color: #f7d794; margin: 2px 0; }
</style>
</head>
<body>
<div id="sidebar">
  <h2>Story Timeline</h2>
  <select id="type-filter"><option value="">All types</option></select>
  <div id="node-list"></div>
</div>
<div id="main">
  <canvas id="graph"></canvas>
  <div id="detail"><em>Click a node to see details</em></div>
</div>
<script>
let allNodes = [], allEdges = [], selected = null;
let simNodes = [], simEdges = [];
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d');
const TYPE_COLORS = {};
const PALETTE = ['#e84393','#00d2ff','#f7d794','#a8ff78','#ff6b6b','#c3a6ff','#ffd460','#48dbfb'];

function typeColor(t) {
  if (!TYPE_COLORS[t]) {
    const keys = Object.keys(TYPE_COLORS);
    TYPE_COLORS[t] = PALETTE[keys.length % PALETTE.length];
  }
  return TYPE_COLORS[t];
}

function resize() {
  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = canvas.parentElement.clientHeight - document.getElementById('detail').offsetHeight;
}

function fieldLabel(node) {
  const f = node.fields || {};
  return f.name || f.title || f.summary?.slice(0,30) || node.type;
}

async function loadData() {
  const [nr, er] = await Promise.all([fetch('/api/nodes'), fetch('/api/edges')]);
  allNodes = await nr.json();
  allEdges = await er.json();
  populateSidebar();
  buildSim();
  requestAnimationFrame(tick);
}

function populateSidebar() {
  const types = [...new Set(allNodes.map(n => n.type))].sort();
  const sel = document.getElementById('type-filter');
  types.forEach(t => {
    const o = document.createElement('option');
    o.value = t; o.textContent = t; sel.appendChild(o);
  });
  sel.onchange = () => renderList(sel.value);
  renderList('');
}

function renderList(typeFilter) {
  const list = document.getElementById('node-list');
  list.innerHTML = '';
  (typeFilter ? allNodes.filter(n => n.type === typeFilter) : allNodes).forEach(n => {
    const div = document.createElement('div');
    div.className = 'node-item' + (selected?.id === n.id ? ' selected' : '');
    div.innerHTML = `<span class="node-type-tag">[${n.type}]</span> ${fieldLabel(n)}`;
    div.onclick = () => selectNode(n);
    list.appendChild(div);
  });
}

function buildSim() {
  const cx = canvas.width / 2, cy = canvas.height / 2;
  simNodes = allNodes.map((n, i) => ({
    ...n,
    fields: typeof n.fields === 'string' ? JSON.parse(n.fields) : (n.fields || {}),
    x: cx + (Math.random()-0.5)*400,
    y: cy + (Math.random()-0.5)*300,
    vx: 0, vy: 0
  }));
  simEdges = allEdges.map(e => ({
    ...e,
    a: simNodes.find(n => n.id === e.from_id),
    b: simNodes.find(n => n.id === e.to_id),
  })).filter(e => e.a && e.b);
}

function simulate() {
  const K = 0.04, REP = 3000, DAMP = 0.82, REST = 120;
  for (let i = 0; i < simNodes.length; i++) {
    simNodes[i].fx = 0; simNodes[i].fy = 0;
    for (let j = 0; j < simNodes.length; j++) {
      if (i === j) continue;
      const dx = simNodes[i].x - simNodes[j].x;
      const dy = simNodes[i].y - simNodes[j].y;
      const d2 = dx*dx + dy*dy || 1, d = Math.sqrt(d2);
      simNodes[i].fx += (dx/d) * REP / d2;
      simNodes[i].fy += (dy/d) * REP / d2;
    }
    // Center pull
    simNodes[i].fx += (canvas.width/2 - simNodes[i].x) * 0.01;
    simNodes[i].fy += (canvas.height/2 - simNodes[i].y) * 0.01;
  }
  for (const e of simEdges) {
    const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
    const d = Math.sqrt(dx*dx + dy*dy) || 1;
    const f = K * (d - REST);
    e.a.fx += (dx/d)*f; e.a.fy += (dy/d)*f;
    e.b.fx -= (dx/d)*f; e.b.fy -= (dy/d)*f;
  }
  for (const n of simNodes) {
    n.vx = (n.vx + n.fx) * DAMP;
    n.vy = (n.vy + n.fy) * DAMP;
    n.x += n.vx; n.y += n.vy;
    n.x = Math.max(20, Math.min(canvas.width-20, n.x));
    n.y = Math.max(20, Math.min(canvas.height-20, n.y));
  }
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  // Edges
  for (const e of simEdges) {
    ctx.beginPath();
    ctx.moveTo(e.a.x, e.a.y); ctx.lineTo(e.b.x, e.b.y);
    ctx.strokeStyle = '#2a4a6b'; ctx.lineWidth = 1; ctx.stroke();
    // Label
    const mx = (e.a.x+e.b.x)/2, my = (e.a.y+e.b.y)/2;
    ctx.fillStyle = '#506070'; ctx.font = '9px monospace';
    ctx.fillText(e.relation, mx, my);
  }
  // Nodes
  for (const n of simNodes) {
    const r = selected?.id === n.id ? 18 : 12;
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, Math.PI*2);
    ctx.fillStyle = typeColor(n.type); ctx.fill();
    if (selected?.id === n.id) {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
    }
    ctx.fillStyle = '#fff'; ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(fieldLabel(n).slice(0,16), n.x, n.y + r + 12);
  }
  ctx.textAlign = 'left';
}

let _frame = 0;
function tick() {
  if (_frame++ % 2 === 0) simulate();
  draw();
  requestAnimationFrame(tick);
}

function selectNode(n) {
  selected = simNodes.find(s => s.id === n.id) || n;
  renderList(document.getElementById('type-filter').value);
  showDetail(selected);
}

async function showDetail(n) {
  const resp = await fetch('/api/node/' + n.id);
  const node = await resp.json();
  const fields = typeof node.fields === 'string' ? JSON.parse(node.fields) : (node.fields || {});
  let html = `<h3>[${node.type}] ${fieldLabel(node)}</h3>`;
  for (const [k,v] of Object.entries(fields)) {
    html += `<div class="field-row"><span class="field-key">${k}:</span> ${Array.isArray(v)?v.join(', '):v}</div>`;
  }
  const nodeEdges = allEdges.filter(e => e.from_id===node.id || e.to_id===node.id);
  if (nodeEdges.length) {
    html += '<hr style="border-color:#0f3460;margin:6px 0">';
    for (const e of nodeEdges) {
      const other = allNodes.find(x => x.id === (e.from_id===node.id?e.to_id:e.from_id));
      const dir = e.from_id===node.id ? '→' : '←';
      html += `<div class="edge-item">${dir} ${e.relation} ${other?fieldLabel({...other,fields:typeof other.fields==='string'?JSON.parse(other.fields):other.fields}):e.from_id===node.id?e.to_id:e.from_id}</div>`;
    }
  }
  document.getElementById('detail').innerHTML = html;
}

canvas.onclick = e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const hit = simNodes.find(n => {
    const dx = n.x-mx, dy = n.y-my;
    return dx*dx+dy*dy < 18*18;
  });
  if (hit) selectNode(hit);
};

window.onresize = () => { resize(); buildSim(); };
resize();
loadData();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # suppress access logs

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = _HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/nodes":
            nodes = timeline_db.get_nodes()
            for n in nodes:
                try:
                    n["fields"] = json.loads(n["fields"])
                except Exception:
                    pass
            self._json(nodes)

        elif self.path == "/api/edges":
            # Return edges for all nodes combined (deduplicated)
            seen = set()
            result = []
            for node_id in timeline_db.get_all_node_ids():
                for e in willow_edges.edges_for(node_id, uuid=_USER_UUID):
                    if e.get("id") not in seen:
                        seen.add(e.get("id"))
                        result.append(e)
            self._json(result)

        elif self.path.startswith("/api/node/"):
            node_id = self.path[len("/api/node/"):]
            node = timeline_db.get_node(node_id)
            if node:
                try:
                    node["fields"] = json.loads(node["fields"])
                except Exception:
                    pass
                self._json(node)
            else:
                self._json({"error": "not found"}, 404)

        else:
            self._json({"error": "not found"}, 404)


class TimelineHTTPServer:
    def __init__(self, port: int = 8765):
        self.port = port
        self._server: Optional[socketserver.TCPServer] = None

    def start(self):
        socketserver.TCPServer.allow_reuse_address = True
        self._server = socketserver.TCPServer(("", self.port), _Handler)
        self._server.serve_forever()

    def stop(self):
        if self._server:
            self._server.shutdown()


def run_web(port: int = 8765, open_browser: bool = True):
    _set_user_uuid(safe_integration.get_user_uuid())
    server = TimelineHTTPServer(port=port)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    url = f"http://localhost:{port}/"
    print(f"Story Timeline web UI: {url}")
    if open_browser:
        import time; time.sleep(0.3)
        webbrowser.open(url)
    try:
        t.join()
    except KeyboardInterrupt:
        server.stop()
```

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_web.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5.5: Commit**

```bash
git add apps/story-timeline/web.py tests/story-timeline/test_web.py
git commit -m "feat(story-timeline): stdlib HTTP server + Canvas force-graph UI"
```

---

## Task 6: Rewrite app.py — TUI + boot orchestrator

**Files:**
- Modify: `apps/story-timeline/app.py`
- Test: `tests/story-timeline/test_app_boot.py`

- [ ] **Step 6.1: Write failing boot tests**

Create `tests/story-timeline/test_app_boot.py`:

```python
import os
import sys
import pytest

sys.path.insert(0, str(os.path.dirname(__file__) + "/../../apps/story-timeline"))

def test_boot_sequence_runs_migration_when_needed(tmp_path, monkeypatch):
    import sqlite3
    db_path = tmp_path / "timeline.db"
    # Create v1 db
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, story TEXT, world_date TEXT NOT NULL, location TEXT, characters TEXT, summary TEXT NOT NULL, tags TEXT, created_at TEXT)")
    conn.execute("INSERT INTO events (story, world_date, summary) VALUES ('s', 'D1', 'A thing happened')")
    conn.commit(); conn.close()
    monkeypatch.setenv("STORY_TIMELINE_DB", str(db_path))

    import migrate, timeline_db
    import importlib
    importlib.reload(migrate); importlib.reload(timeline_db)

    from app import boot_sequence
    result = boot_sequence()
    assert result["migrated"] == 1

def test_boot_sequence_reconciles_edges(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "willow"))
    monkeypatch.setenv("WILLOW_CORE", "~/github/willow-1.9/core")

    import timeline_db, willow_edges, importlib
    importlib.reload(timeline_db); importlib.reload(willow_edges)

    node_id = timeline_db.add_node(type_="character", fields={"name": "Real"})
    willow_edges.add_edge(node_id, "ghost-id", "knows", uuid="boot-test-uuid")

    from app import boot_sequence
    result = boot_sequence(uuid="boot-test-uuid")
    assert result["orphans_removed"] == 1
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_app_boot.py -v 2>&1 | head -20
```

Expected: ImportError — `boot_sequence` not found in `app`.

- [ ] **Step 6.3: Rewrite app.py**

Replace the entire file with:

```python
"""
Story Timeline v2 — open node graph writing tool.
Professor Oakenscroll's successor. Local. Free. Willow-integrated.

Usage:
  python3 app.py          → TUI
  python3 app.py --web    → web server + open browser
"""
import json
import sys
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable, Footer, Header, Input, Label,
    Button, Select, Static, TextArea
)

import timeline_db as db
import willow_edges
import safe_integration
import migrate

# ── Boot ──────────────────────────────────────────────────────────────────────

def boot_sequence(uuid: Optional[str] = None) -> dict:
    """Run startup checks. Returns summary dict."""
    result = {"migrated": 0, "orphans_removed": 0, "uuid": uuid}

    # 1. Migration
    if migrate.needs_migration():
        result["migrated"] = migrate.run_migration()

    # 2. Edge reconciliation
    node_ids = db.get_all_node_ids()
    result["orphans_removed"] = willow_edges.reconcile_orphans(node_ids, uuid=uuid)

    return result


# ── Screens ───────────────────────────────────────────────────────────────────

class CreateNodeScreen(ModalScreen):
    """Create or edit a node. Fields entered as 'key: value' lines."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, node: Optional[dict] = None):
        super().__init__()
        self._node = node  # None = create, dict = edit

    def compose(self) -> ComposeResult:
        existing_type = self._node["type"] if self._node else ""
        existing_fields = ""
        if self._node:
            fields = json.loads(self._node["fields"])
            existing_fields = "\n".join(f"{k}: {v}" for k, v in fields.items())
        yield Vertical(
            Label("Create Node" if not self._node else "Edit Node", id="modal-title"),
            Label("Entity type (e.g. character, location, event)"),
            Input(value=existing_type, placeholder="character", id="type-input"),
            Label("Fields — one 'key: value' per line"),
            TextArea(existing_fields, id="fields-input"),
            Horizontal(
                Button("Save", variant="primary", id="save-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        type_ = self.query_one("#type-input", Input).value.strip()
        if not type_:
            return
        raw = self.query_one("#fields-input", TextArea).text.strip()
        fields = {}
        for line in raw.splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                fields[k.strip()] = v.strip()
        self.dismiss({"type": type_, "fields": fields})


class LinkNodesScreen(ModalScreen):
    """Link two nodes with a relation."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, from_id: str):
        super().__init__()
        self._from_id = from_id

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Link Nodes", id="modal-title"),
            Label(f"From: {self._from_id[:16]}…"),
            Label("Target node ID"),
            Input(placeholder="paste node ID", id="to-id"),
            Label("Relation label"),
            Input(placeholder="knows / causes / located_in / …", id="relation"),
            Horizontal(
                Button("Link", variant="primary", id="link-btn"),
                Button("Cancel", id="cancel-btn"),
            ),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        to_id = self.query_one("#to-id", Input).value.strip()
        relation = self.query_one("#relation", Input).value.strip()
        if not to_id or not relation:
            return
        self.dismiss({"from_id": self._from_id, "to_id": to_id, "relation": relation})


class NodeDetailScreen(ModalScreen):
    """Show full node fields + edges."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, node: dict, edges: list):
        super().__init__()
        self._node = node
        self._edges = edges

    def _fields_str(self) -> str:
        try:
            f = json.loads(self._node["fields"])
        except Exception:
            f = {}
        return "\n".join(f"  {k}: {v}" for k, v in f.items()) or "  (no fields)"

    def _edges_str(self) -> str:
        if not self._edges:
            return "  (no edges)"
        lines = []
        for e in self._edges:
            if e["from_id"] == self._node["id"]:
                lines.append(f"  → {e['relation']} → {e['to_id'][:16]}…")
            else:
                lines.append(f"  ← {e['relation']} ← {e['from_id'][:16]}…")
        return "\n".join(lines)

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"[{self._node['type']}]  {self._node['id'][:24]}", id="modal-title"),
            Label("Fields:"),
            Static(self._fields_str()),
            Label("Edges:"),
            Static(self._edges_str()),
            Button("Close", id="close-btn"),
            id="modal-content",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


# ── Main App ──────────────────────────────────────────────────────────────────

class TimelineApp(App):
    CSS = """
    #modal-content {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        width: 72;
        height: auto;
        max-height: 90vh;
    }
    #modal-title { text-style: bold; margin-bottom: 1; }
    CreateNodeScreen, LinkNodesScreen, NodeDetailScreen { align: center middle; }
    #filter-bar { height: 3; }
    #type-select { width: 24; }
    #search-input { width: 1fr; }
    #status { height: 1; color: $text-muted; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("a", "create_node", "Add node"),
        Binding("e", "edit_node", "Edit"),
        Binding("d", "delete_node", "Delete"),
        Binding("l", "link_node", "Link"),
        Binding("v", "view_node", "View detail"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, uuid: Optional[str] = None):
        super().__init__()
        self._uuid = uuid
        self._type_filter: Optional[str] = None
        self._search: Optional[str] = None
        self._session_stats = {"nodes_created": 0, "edges_created": 0, "types_used": set()}

    def compose(self) -> ComposeResult:
        types = db.get_types()
        type_opts = [("All types", "__all__")] + [(t, t) for t in types]
        yield Header(show_clock=True)
        yield Horizontal(
            Label("Type: "),
            Select(type_opts, id="type-select", value="__all__"),
            Input(placeholder="search…", id="search-input"),
            id="filter-bar",
        )
        yield DataTable(id="node-table")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Story Timeline v2"
        self.sub_title = "open node graph"
        self._build_table()

    def _build_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("ID", "Type", "Summary")
        if self._search:
            nodes = db.search_nodes(self._search)
        else:
            nodes = db.get_nodes(type_=self._type_filter)
        for n in nodes:
            try:
                fields = json.loads(n["fields"])
            except Exception:
                fields = {}
            summary = (
                fields.get("name") or
                fields.get("title") or
                fields.get("summary", "")[:50] or
                str(fields)[:50]
            )
            table.add_row(n["id"][:16] + "…", n["type"], summary)
        self.query_one("#status", Static).update(
            f"{len(nodes)} node(s)"
            + (f"  type={self._type_filter}" if self._type_filter else "")
            + (f"  search='{self._search}'" if self._search else "")
        )

    def _selected_node(self) -> Optional[dict]:
        table = self.query_one(DataTable)
        row = table.cursor_row
        if row < 0:
            return None
        cell = table.get_cell_at((row, 0))
        if not cell:
            return None
        partial_id = str(cell).rstrip("…")
        nodes = db.get_nodes()
        for n in nodes:
            if n["id"].startswith(partial_id):
                return n
        return None

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "type-select":
            self._type_filter = None if event.value == "__all__" else event.value
            self._build_table()

    def on_input_changed(self, event) -> None:
        if event.input.id == "search-input":
            self._search = event.value.strip() or None
            self._build_table()

    def action_create_node(self) -> None:
        def on_dismiss(result):
            if result:
                db.add_node(type_=result["type"], fields=result["fields"])
                self._session_stats["nodes_created"] += 1
                self._session_stats["types_used"].add(result["type"])
                self._build_table()
        self.push_screen(CreateNodeScreen(), on_dismiss)

    def action_edit_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        def on_dismiss(result):
            if result:
                db.update_node(node["id"], fields=result["fields"])
                self._build_table()
        self.push_screen(CreateNodeScreen(node=node), on_dismiss)

    def action_delete_node(self) -> None:
        node = self._selected_node()
        if node and db.delete_node(node["id"]):
            self._build_table()

    def action_link_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        def on_dismiss(result):
            if result:
                willow_edges.add_edge(
                    result["from_id"], result["to_id"],
                    result["relation"], uuid=self._uuid
                )
                self._session_stats["edges_created"] += 1
        self.push_screen(LinkNodesScreen(from_id=node["id"]), on_dismiss)

    def action_view_node(self) -> None:
        node = self._selected_node()
        if not node:
            return
        edges = willow_edges.edges_for(node["id"], uuid=self._uuid)
        self.push_screen(NodeDetailScreen(node=node, edges=edges))

    def action_refresh(self) -> None:
        self._build_table()

    def action_quit(self) -> None:
        stats = {
            "nodes_created": self._session_stats["nodes_created"],
            "edges_created": self._session_stats["edges_created"],
            "types_used": list(self._session_stats["types_used"]),
        }
        if self._uuid:
            safe_integration.write_session_composite(stats=stats, uuid=self._uuid)
        self.exit()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    # User identity
    uuid = safe_integration.get_user_uuid()
    if not uuid:
        print("⚠  ~/.willow/user_identity.json not found — Willow edges disabled.")
        print("   Install willow-seed to enable graph persistence.\n")

    # Boot
    boot = boot_sequence(uuid=uuid)
    if boot["migrated"]:
        print(f"  Migrated {boot['migrated']} v1 events → nodes.")
    if boot["orphans_removed"]:
        print(f"  Removed {boot['orphans_removed']} orphan edge(s).")

    # Launch surface
    if "--web" in sys.argv:
        import web
        web.run_web(port=8765)
    else:
        TimelineApp(uuid=uuid).run()
```

- [ ] **Step 6.4: Run boot tests to verify they pass**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/test_app_boot.py -v
```

Expected: both tests PASS.

- [ ] **Step 6.5: Smoke-test the TUI launches without errors**

```bash
cd ~/github/safe-app-store/apps/story-timeline
python3 -c "
import app, timeline_db
timeline_db.add_node('character', {'name': 'Alice'})
timeline_db.add_node('location', {'name': 'Rivendell'})
print('DB ready. TUI import OK.')
"
```

Expected: `DB ready. TUI import OK.`

- [ ] **Step 6.6: Run full test suite**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/ -v
```

Expected: all tests PASS.

- [ ] **Step 6.7: Commit**

```bash
git add apps/story-timeline/app.py tests/story-timeline/test_app_boot.py
git commit -m "feat(story-timeline): v2 TUI + boot orchestrator"
```

---

## Task 7: Update manifest + wire Makefile --web target

**Files:**
- Modify: `apps/story-timeline/safe-app-manifest.json`

- [ ] **Step 7.1: Update the manifest**

Replace the contents of `apps/story-timeline/safe-app-manifest.json` with:

```json
{
  "name": "story-timeline",
  "version": "2.0.0",
  "description": "Open node graph writing tool. Any entity type, user-defined. Local, private, Willow-integrated.",
  "author": "Professor Oakenscroll / Vishwakarma",
  "entry_point": "app.py",
  "permissions": [
    "filesystem_write",
    "store_read",
    "store_write",
    "store_add_edge",
    "store_edges_for"
  ],
  "sap_scope": "user-{uuid}/story-timeline/**",
  "exposes": {
    "atoms": {
      "path": "user-{uuid}/story-timeline/atoms/",
      "access": "read",
      "requires_user_approval": true,
      "description": "Session composite atoms — writing activity summary"
    }
  },
  "local": true,
  "surfaces": ["tui", "web"],
  "dependencies": {
    "user_identity_json": "required — provisioned by willow-seed",
    "norn_pass_scope": "optional — needed for reflection/insight passes",
    "cross_app_sap_spec": "optional — needed for cross-app atom reads"
  },
  "b17": "STLN2"
}
```

- [ ] **Step 7.2: Verify make run app=story-timeline works**

```bash
cd ~/github/safe-app-store
make run app=story-timeline 2>&1 | head -5 || true
```

Expected: TUI starts (or prints migration notice). `ctrl+c` to exit.

- [ ] **Step 7.3: Verify --web flag works**

```bash
cd ~/github/safe-app-store/apps/story-timeline
timeout 3 python3 app.py --web || true
```

Expected: prints `Story Timeline web UI: http://localhost:8765/` before timeout.

- [ ] **Step 7.4: Commit**

```bash
git add apps/story-timeline/safe-app-manifest.json
git commit -m "feat(story-timeline): v2 — update SAP manifest with permissions + exposes"
```

---

## Task 8: Final integration pass

- [ ] **Step 8.1: Run the full test suite one final time**

```bash
cd ~/github/safe-app-store
python -m pytest tests/story-timeline/ -v --tb=short
```

Expected: all tests PASS. Note any failures and fix before proceeding.

- [ ] **Step 8.2: Manual smoke test — TUI golden path**

```bash
cd ~/github/safe-app-store/apps/story-timeline
python3 app.py
```

Run through:
1. Press `a` → create a node of type `character`, fields `name: Gandalf` → Save
2. Press `a` → create a node of type `location`, fields `name: Rivendell` → Save
3. Navigate to the Gandalf row → press `l` → paste Rivendell node ID → relation `visits` → Link
4. Navigate to the Gandalf row → press `v` → confirm edge appears in detail view
5. Press `q` → app exits cleanly

- [ ] **Step 8.3: Manual smoke test — web golden path**

```bash
cd ~/github/safe-app-store/apps/story-timeline
python3 app.py --web
```

1. Browser opens at `http://localhost:8765/`
2. Both nodes appear as circles in the force graph
3. Edge appears as a connecting line
4. Click a node → detail panel shows fields

- [ ] **Step 8.4: Final commit**

```bash
git add -A
git commit -m "feat(story-timeline): v2 complete — open node graph, Willow edges, TUI + web"
```

---

## External Dependencies (pre-ship blockers)

These are not in scope for this implementation but must be resolved before v2 ships to users:

| Dependency | Status | Impact |
|---|---|---|
| `~/.willow/user_identity.json` | Missing — willow-seed deliverable | Willow edges silently disabled; TUI still usable |
| `norn_pass` scope extension | Missing — willow-1.9 core change | Reflection/insight passes not generated |
| Cross-app SAP manifest spec | Missing — companion task | Other apps can't request read access to story-timeline atoms |

The app degrades gracefully in all three cases — it runs fully without them, just without the Willow-integration features.
