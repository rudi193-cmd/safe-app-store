import json
import os
import sqlite3
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture()
def v1_db(tmp_path):
    db_path = tmp_path / "timeline.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story TEXT NOT NULL DEFAULT 'default',
            world_date TEXT NOT NULL,
            location TEXT DEFAULT '',
            characters TEXT DEFAULT '[]',
            summary TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "INSERT INTO events (story, world_date, summary) VALUES (?, ?, ?)",
        ("s", "D1", "A thing happened")
    )
    conn.commit()
    conn.close()
    return db_path


def test_boot_sequence_runs_migration_when_needed(tmp_path, v1_db, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(v1_db))
    import migrate, timeline_db
    import importlib
    importlib.reload(migrate)
    importlib.reload(timeline_db)
    from app import boot_sequence
    result = boot_sequence()
    assert result["migrated"] == 1


def test_boot_sequence_no_migration_for_v2_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "clean.db"))
    import migrate, timeline_db
    import importlib
    importlib.reload(migrate)
    importlib.reload(timeline_db)
    # Add a v2 node to force nodes table creation
    timeline_db.add_node(type_="character", fields={"name": "Alice"})
    from app import boot_sequence
    result = boot_sequence()
    assert result["migrated"] == 0


def test_boot_sequence_reconciles_edges(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "edges.db"))
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "willow"))
    from pathlib import Path
    monkeypatch.setenv("WILLOW_CORE", str(
        Path(__file__).parents[5] / "willow-1.9" / "core"
    ))
    import migrate, timeline_db, willow_edges
    import importlib
    importlib.reload(migrate)
    importlib.reload(timeline_db)
    importlib.reload(willow_edges)
    willow_edges._WILLOW_STORE = None

    node_id = timeline_db.add_node(type_="character", fields={"name": "Real"})
    willow_edges.add_edge(node_id, "ghost-id", "knows", uuid="boot-test-uuid")

    from app import boot_sequence
    result = boot_sequence(uuid="boot-test-uuid")
    assert result["orphans_removed"] == 1


def test_boot_sequence_returns_dict_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "keys.db"))
    import migrate, timeline_db
    import importlib
    importlib.reload(migrate)
    importlib.reload(timeline_db)
    from app import boot_sequence
    result = boot_sequence()
    assert "migrated" in result
    assert "orphans_removed" in result
