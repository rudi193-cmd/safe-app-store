import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture(autouse=True)
def reset_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    for name in (
        "timeline_db",
        "willow_edges",
        "story_protocol",
        "suggestion_store",
        "mcp_client",
        "intelligence",
        "app",
    ):
        sys.modules.pop(name, None)


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    monkeypatch.setenv("STORY_TIMELINE_DISABLE_MCP", "1")
    import importlib
    import timeline_db
    import story_protocol
    import suggestion_store
    importlib.reload(timeline_db)
    importlib.reload(story_protocol)
    importlib.reload(suggestion_store)

    timeline_db.add_node(type_="book", fields={"title": "Dune", "author": "Herbert"})
    note_id = timeline_db.add_node(
        type_="note",
        fields={"title": "Spice", "content": "Melange drives everything"},
    )
    project = story_protocol.create_writing_project("Novel")
    timeline = story_protocol.create_timeline(project["id"], "World")
    suggestion_store.create_suggestion(
        note_id,
        suggestion_kind="promotion",
        proposed_fields={
            "timeline_id": timeline["id"],
            "timeline_label": "Novel / World",
            "title": "Spice beat",
            "summary": "Opening",
        },
        status=suggestion_store.STATUS_PENDING,
    )
    suggestion_store.create_research_packet(
        note_id,
        query="What is spice?",
        summary="A fictional substance.",
    )

    import app as app_module
    importlib.reload(app_module)
    return app_module


def test_library_app_rebuilds_without_crash(app_env):
    app_module = app_env

    async def _exercise() -> None:
        app = app_module.LibraryApp(uuid=None)
        async with app.run_test() as pilot:
            app._rebuild_home()
            app._rebuild_intelligence_table()
            app._rebuild_writing_context()
            app._rebuild_selected_context("#selected-context-books", None)
            home = app.query_one("#home-dashboard")
            assert "Shelves" in str(home.render())
            assert "Jeles" in str(home.render()) or "loose thread" in str(home.render())
            counts = app._counts()
            assert counts["books"] == 1
            assert counts["pending_suggestions"] == 1
            await pilot.press("h")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "HelpScreen"

    asyncio.run(_exercise())


def test_app_compiles(app_env):
    import py_compile
    from pathlib import Path

    app_path = Path(__file__).resolve().parents[2] / "apps/story-timeline/app.py"
    py_compile.compile(str(app_path), doraise=True)
