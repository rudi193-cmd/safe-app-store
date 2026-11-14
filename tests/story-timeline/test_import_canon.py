"""import-canon: what a game table sealed, put on the writer's timeline as
fact entries ("the play grows the world"). CANON is willow's game box's own
export-canon output from a night in the clockwork cellar, word for word."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))

CANON = """<!-- canon from a game box: record 60b81be3ba3d6f59e34378b6bef120827eb16c722ca036f4e8ab347377b56ad0, 45 rows -->
# What the table made true

- The red button is bait: whoever leaves it alone wins the room.
  sealed: proposal:c33406e786b9464fa2574813eb945b7acf609dd07eae6598a8841b3c57cac782 | row 27 | clockwork-cellar::room::button
- A guest comes down the stair: Old Vell from the lantern fair.
  sealed: proposal:0bd1dc512fb17c38b28b0c63fc99ac3bcc65267ab2d8128d00ba70306ef9e384 | row 28 | clockwork-cellar, offered by pell as a guest
- A guest walks into the cellar: the Lantern Man, who carries his own light and answers only in riddles.
  sealed: proposal:7e76fe97c33a503985bdc9311ebc5bd2541d2934b2ea2a7c174474a854f8f3aa | row 34 | clockwork-cellar::room::guest
- Prince Aldric is free, and owes Brann's goats a favour.
  sealed: proposal:21fc52cedfc39c00e16e6492d7fd874e483c82e5728bdbcb95ad5073e49e5de8 | row 41 | clockwork-cellar::room::free
"""


@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib

    import timeline_db

    importlib.reload(timeline_db)
    import story_protocol

    importlib.reload(story_protocol)
    import import_canon

    importlib.reload(import_canon)
    import export_story

    importlib.reload(export_story)
    return timeline_db, story_protocol, import_canon, export_story


@pytest.fixture()
def cellar(modules):
    _, proto, _, _ = modules
    project = proto.create_writing_project("The Clockwork Cellar")
    return proto.create_timeline(project["id"], "The Clockwork Cellar", timeline_kind="world")["id"]


def test_each_sealed_fact_becomes_a_fact_entry_with_its_seal(modules, cellar):
    _, proto, imp, _ = modules
    got = imp.import_canon(CANON, cellar)
    assert len(got["added"]) == 4 and not got["skipped"]
    entries = proto.list_timeline_entries(cellar)
    assert [e["fields"]["entry_kind"] for e in entries] == ["fact"] * 4
    free = next(e for e in entries if "Prince Aldric is free" in e["fields"]["summary"])
    assert free["fields"]["from"] == "clockwork-cellar::room::free"
    assert free["fields"]["canon subject"].startswith("proposal:") and free["fields"]["sealed row"] == 41
    assert free["fields"]["record"] == got["record"] and len(got["record"]) == 64
    vell = next(e for e in entries if "Old Vell" in e["fields"]["summary"])
    assert vell["fields"]["from"] == "clockwork-cellar, offered by pell as a guest"
    source = [n for n in modules[0].get_nodes(type_="commonplace_item") if n["fields"]["source_kind"] == "canon"]
    assert len(source) == 4 and all(n["fields"]["tags"] == "game-box" for n in source)


def test_importing_again_adds_only_whats_new(modules, cellar):
    _, proto, imp, _ = modules
    first = CANON.rsplit("- Prince Aldric", 1)[0]  # an earlier night: three facts
    assert len(imp.import_canon(first, cellar)["added"]) == 3
    again = imp.import_canon(CANON, cellar)
    assert len(again["added"]) == 1 and len(again["skipped"]) == 3
    assert len(proto.list_timeline_entries(cellar)) == 4


def test_a_long_fact_gets_a_short_title_and_keeps_its_words(modules, cellar):
    _, proto, imp, _ = modules
    imp.import_canon(CANON, cellar)
    lantern = next(e for e in proto.list_timeline_entries(cellar) if "Lantern Man" in e["fields"]["summary"])
    assert lantern["fields"]["title"].endswith("...") and len(lantern["fields"]["title"]) <= 84
    assert lantern["fields"]["summary"].endswith("answers only in riddles.")


def test_facts_stay_out_of_the_story_the_box_plays(modules, cellar):
    db, proto, imp, export = modules
    imp.import_canon(CANON, cellar)
    entry = proto.create_timeline_entry(cellar, "Down the stair", order_index=99, entry_kind="scene")
    db.update_node(entry["id"], {**entry["fields"], "place": "The mill stair"})
    text = export.story_markdown(cellar)
    assert "## Scene down-the-stair" in text and "Prince Aldric is free" not in text


@pytest.mark.parametrize(
    "text, says",
    [
        ("# What the table made true\n", "line 1: not a game box's canon"),
        (CANON.replace("  sealed: proposal:", "  sealed proposal:", 1), "line 5: a fact is"),
        (CANON.rsplit("\n  sealed:", 1)[0] + "\n", "a fact with no seal under it"),
    ],
)
def test_canon_that_isnt_one_is_refused(modules, cellar, text, says):
    _, _, imp, _ = modules
    with pytest.raises(ValueError, match=says):
        imp.import_canon(text, cellar)


def test_the_command_line_imports_and_says_what_it_did(modules, cellar, tmp_path, capsys):
    import importlib

    import promote

    importlib.reload(promote)
    f = tmp_path / "canon.md"
    f.write_text(CANON)
    assert promote.main(["import-canon", str(f), "--timeline", cellar, "--no-mirror"]) == 0
    out = capsys.readouterr().out
    assert "4 added, 0 already on the timeline" in out and "added  Prince Aldric is free" in out
    assert promote.main(["import-canon", str(f), "--timeline", "nowhere"]) == 2
