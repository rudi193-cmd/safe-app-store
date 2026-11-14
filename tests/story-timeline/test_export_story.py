"""export-story: a timeline written in story-timeline, out as the story
markdown willow's game box plays. The story is the game box's second
chapter of the clockwork cellar, written here the way a writer would:
a project, a timeline, characters, places, scene entries and beat entries."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/story-timeline"))


@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_TIMELINE_DB", str(tmp_path / "timeline.db"))
    import importlib

    import timeline_db

    importlib.reload(timeline_db)
    import story_protocol

    importlib.reload(story_protocol)
    import export_story

    importlib.reload(export_story)
    return timeline_db, story_protocol, export_story


def with_fields(db, node: dict, **extra) -> dict:
    """A node's own fields, and a writer's free ones beside them."""
    fields = {**node["fields"], **{k.replace("_", " "): v for k, v in extra.items()}}
    db.update_node(node["id"], fields)
    return db.get_node(node["id"])


def build_wasp_nest(db, proto) -> str:
    """The wasp nest, written in story-timeline; its timeline's id."""
    project = proto.create_writing_project("The Clockwork Cellar", summary="A family game, once a week.")
    timeline = proto.create_timeline(
        project["id"], "The Wasp Nest", timeline_kind="world",
        description="The same valley, a week on: up in the cellar ceiling, where the springs go. "
                    "Every name here is a character, never a player.",
    )  # fmt: skip
    with_fields(db, timeline, stats="Grit, Wit, Heart, Weird", offers="guest")
    for name, role, extra in (
        ("Pell", "miller's apprentice", {"seated": "yes", "stats": "Grit 2, Heart 1"}),
        ("Juno", "tinker", {"seated": "yes", "stats": "Wit 2, Weird 1"}),
        ("Brann", "goat-herd", {"seated": "yes", "stats": "Heart 2"}),
        ("Cogwen", "the cellar's clockwork keeper", {}),
        ("Old Vell", "keeper of the lantern fair", {}),
        ("Prince Aldric", "freed, perhaps, last time", {}),
    ):
        db.add_node(type_="character", fields={"name": name, "role": role, "project": "The Clockwork Cellar", **extra})  # fmt: skip
    for name in ("The cellar ceiling", "Cogwen's workshop"):
        db.add_node(type_="place", fields={"name": name, "project": project["id"]})
    db.add_node(type_="character", fields={"name": "Somebody Else", "role": "of another book", "project": "Another"})  # fmt: skip

    order = iter(range(100))

    def entry(title, entry_kind, summary="", **extra):
        node = proto.create_timeline_entry(timeline["id"], title, summary=summary, order_index=next(order), entry_kind=entry_kind)  # fmt: skip
        return with_fields(db, node, **extra)

    entry("Up into the ceiling", "scene", place="The cellar ceiling",
          summary="The springs Cogwen kept go up, one by one, into the dark.\nSomething hums up there, and something glints.")  # fmt: skip
    entry("Prince Aldric comes to watch.", "beat", id="prince", kind="action", by="brann", suggests="Heart",
          when="sealed clockwork-cellar::room::free is sealed",
          strong="He holds the ladder, and owes Brann's goats a second favour.",
          weak="He holds the ladder, badly.", miss="He talks the whole time.")  # fmt: skip
    entry("Juno climbs after the springs.", "beat", id="climb", kind="action", by="juno", suggests="Wit",
          strong="She finds the nest, and every spring is woven into it like straw.",
          weak="She finds the nest, and the nest finds her: the wasps wake.",
          miss="The beam she's on is a spring too. Down she comes.")  # fmt: skip
    entry("The wasps come out.", "beat", id="wasps", kind="action", by="pell", suggests="Grit",
          when="up-into-the-ceiling::climb is weak, miss",
          strong="Pell swings a smoking lantern and they scatter.",
          weak="Pell gets them off Juno, and gets stung for it.", miss="Everyone runs, and the wasps keep the nest.")  # fmt: skip
    entry("Is Old Vell's lamp in the nest?", "beat", id="lamp", kind="decision", proposed_by="old-vell",
          fact="Old Vell's lost lamp is in the nest, and it's still lit.")  # fmt: skip
    entry("A week passes in the valley.", "milestone")
    entry("Cogwen's workshop", "scene", place="Cogwen's workshop",
          summary="Behind the backwards gear is a room no one has been in.\n"
                  "In the middle of it, something tall, half built, made of springs.")  # fmt: skip
    entry("Brann asks Cogwen what she's building.", "beat", id="ask", kind="action", by="brann", suggests="Heart",
          strong="Cogwen tells him: a friend, so the cellar isn't lonely.",
          weak='Cogwen says "a friend", and won\'t say whose.', miss="Cogwen covers it with a sheet and says nothing at all.")  # fmt: skip
    entry("The table's guest looks at it too.", "beat", id="guest", kind="action", by="pell", suggests="Heart",
          when="offered guest is sealed", strong="The guest knows what it is, and smiles.",
          weak="The guest has seen one before, a long time ago.", miss="The guest goes very quiet.")  # fmt: skip
    entry("What is Cogwen building?", "beat", id="friend", kind="decision", proposed_by="cogwen",
          fact="Cogwen is building a clockwork friend, from one spring of everything she ever let go.")  # fmt: skip
    entry("The springs were Cogwen's all along.", "fact")
    return timeline["id"]


def test_a_timeline_exports_as_the_story_the_game_box_reads(modules):
    db, proto, export = modules
    text = export.story_markdown(build_wasp_nest(db, proto))
    lines = text.splitlines()
    assert lines[0].startswith("<!-- exported from story-timeline: timeline ")
    assert lines[1] == "# The Wasp Nest"
    for line in ("id: the-wasp-nest", "stats: Grit, Wit, Heart, Weird", "base stat: 1", "offers: guest",
                 "- pell: Pell | miller's apprentice | seated | Grit 2, Heart 1",
                 "- cogwen: Cogwen | the cellar's clockwork keeper",
                 "- the-cellar-ceiling: The cellar ceiling",
                 "## Scene up-into-the-ceiling: Up into the ceiling @ the-cellar-ceiling",
                 "Something hums up there, and something glints.",
                 "### Prince Aldric comes to watch.",
                 "when: sealed clockwork-cellar::room::free is sealed",
                 "proposed by: old-vell", "- miss: The guest goes very quiet."):  # fmt: skip
        assert line in lines, line
    assert "Somebody Else" not in text  # a character of another project
    assert "A week passes" not in text and "were Cogwen's all along" not in text  # chronology, not play
    assert text.index("## Scene up-into") < text.index("### Juno climbs") < text.index("## Scene cogwen-s-workshop")


def test_export_story_writes_once_and_refuses_a_timeline_not_there(modules, tmp_path, capsys):
    db, proto, _ = modules
    import importlib

    import promote

    importlib.reload(promote)
    tid = build_wasp_nest(db, proto)
    to = tmp_path / "wasp-nest.md"
    assert promote.main(["export-story", "--timeline", tid, "--to", str(to)]) == 0
    assert to.read_text().splitlines()[1] == "# The Wasp Nest"
    assert promote.main(["export-story", "--timeline", tid, "--to", str(to)]) == 2
    assert "never written over" in capsys.readouterr().err
    assert promote.main(["export-story", "--timeline", "no-such"]) == 2
