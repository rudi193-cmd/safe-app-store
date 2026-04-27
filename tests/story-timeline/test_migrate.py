import json
import os
import sqlite3
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


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


def test_needs_migration_false_when_no_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "nonexistent.db"))
    import migrate
    import importlib
    importlib.reload(migrate)
    assert migrate.needs_migration() is False


def test_needs_migration_false_for_v2_db(tmp_path, monkeypatch):
    v2_path = tmp_path / "v2.db"
    conn = sqlite3.connect(str(v2_path))
    conn.execute("""
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY, type TEXT NOT NULL,
            fields TEXT NOT NULL DEFAULT '{}',
            created TEXT, updated TEXT
        )
    """)
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
    fields_0 = nodes[0]["fields"]  # already a dict (timeline_db deserializes)
    assert fields_0["story"] == "my-story"
    assert fields_0["world_date"] == "Day 1"
    assert fields_0["location"] == "The Inn"
    assert "Alice" in fields_0["characters"]


def test_run_migration_is_idempotent(migrator):
    import timeline_db
    import importlib
    importlib.reload(timeline_db)
    migrator.run_migration()
    count2 = migrator.run_migration()
    assert count2 == 0
    nodes = timeline_db.get_nodes(type_="event")
    assert len(nodes) == 2
