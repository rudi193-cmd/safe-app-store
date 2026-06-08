import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture(autouse=True)
def reset_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    for name in (
        "timeline_db",
        "willow_edges",
        "story_protocol",
        "soil_protocol",
        "safe_integration",
        "promote",
    ):
        sys.modules.pop(name, None)


@pytest.fixture()
def promote_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib
    import promote
    importlib.reload(promote)
    return promote


def test_create_project_cli(promote_cli, capsys):
    rc = promote_cli.main(["create-project", "--title", "Novel Draft"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["type"] == "writing_project"
    assert out["fields"]["title"] == "Novel Draft"


def test_promote_by_timeline_name(promote_cli, capsys):
    promote_cli.main(["create-project", "--title", "Novel Draft"])
    projects = json.loads(capsys.readouterr().out)
    project_id = projects["id"]

    promote_cli.main([
        "create-timeline", "--project", project_id, "--name", "World",
    ])
    capsys.readouterr()

    import timeline_db as db
    note_id = db.add_node(type_="note", fields={"title": "Fog scene", "content": "Mist"})

    rc = promote_cli.main([
        "promote", note_id,
        "--project", project_id,
        "--timeline-name", "World",
        "--no-mirror",
    ])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["entry"]["fields"]["title"] == "Fog scene"
    assert result["provenance"]["source_id"] == note_id
