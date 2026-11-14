"""Export a timeline as a story the game box plays, in markdown.

A writing project's timeline, written in story-timeline, becomes the story
markdown willow's game box reads (demo/game-box/author.py there), which
makes it a world willow's game-master add-on plays. Nothing here plays,
rolls or seals: it writes the writer's structure out, as written.

What goes where:

- the timeline is the story: its name the title, its description the
  setting, and its own fields `stats`, `base stat` and `offers`, when set;
- the project's characters and places are the nodes of type `character`
  and `place` whose `project` field names the project (its title or id): a
  character's `role`, and `seated` and `stats` when it is played at the
  table (`seated: yes`, `stats: Grit 2, Heart 1`);
- each `scene` entry, in timeline order, is a scene: its title, its
  `place` field (a place's name), and its summary as the opening lines;
- each `beat` entry after a scene is one of that scene's beats: its title
  is the prompt, and its fields are the beat's (`kind`, `by`, `suggests`,
  `when`, `strong`, `weak`, `miss`, `proposed by`, `fact`);
- `milestone` and `fact` entries are the writer's chronology, not play, and
  are left out.
"""

from __future__ import annotations

import re

import story_protocol as proto
import timeline_db as db

DEFAULT_STATS = "Grit, Wit, Heart, Weird"
BEAT_FIELDS = ("kind", "by", "suggests", "when")
OUTCOMES = ("strong", "weak", "miss")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "x"


def _field(node: dict, *names: str) -> str:
    fields = node.get("fields", {})
    for name in names:
        value = fields.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _of_project(node: dict, project: dict) -> bool:
    named = _field(node, "project")
    return bool(named) and named in (project["id"], _field(project, "title"))


def story_markdown(timeline_id: str) -> str:
    """The story markdown for a timeline; ValueError when there is none."""
    timeline = proto.get_timeline(timeline_id)
    if timeline is None:
        raise ValueError(f"timeline not found: {timeline_id}")
    project = db.get_node(_field(timeline, "project_id")) or {"id": "", "fields": {}}
    name = _field(timeline, "name")
    out = [f"<!-- exported from story-timeline: timeline {timeline_id} -->", f"# {name}", ""]
    out.append(f"id: {slug(name)}")
    if setting := _field(timeline, "description"):
        out.append(f"setting: {setting}")
    out.append(f"stats: {_field(timeline, 'stats') or DEFAULT_STATS}")
    out.append(f"base stat: {_field(timeline, 'base stat', 'base_stat') or 1}")
    if offers := _field(timeline, "offers"):
        out.append(f"offers: {offers}")
    out += ["", "## Characters", ""]
    for c in db.get_nodes(type_="character"):
        if _of_project(c, project):
            line = f"- {slug(_field(c, 'name'))}: {_field(c, 'name')} | {_field(c, 'role') or 'a character'}"
            if _field(c, "seated").lower() in ("yes", "true", "seated"):
                line += " | seated"
            if stats := _field(c, "stats"):
                line += f" | {stats}"
            out.append(line)
    out += ["", "## Places", ""]
    for p in db.get_nodes(type_="place"):
        if _of_project(p, project):
            out.append(f"- {slug(_field(p, 'name'))}: {_field(p, 'name')}")
    in_scene = False
    for entry in proto.list_timeline_entries(timeline_id):
        kind = _field(entry, "entry_kind") or "scene"
        title = _field(entry, "title")
        if kind == "scene":
            in_scene = True
            out += ["", f"## Scene {slug(title)}: {title} @ {slug(_field(entry, 'place'))}", ""]
            out += [ln.strip() for ln in _field(entry, "summary").splitlines() if ln.strip()]
        elif kind == "beat" and in_scene:
            out += ["", f"### {title}", "", f"id: {slug(_field(entry, 'id') or title)[:40].strip('-')}"]
            out += [f"{f}: {_field(entry, f)}" for f in BEAT_FIELDS if _field(entry, f)]
            if _field(entry, "proposed by"):
                out.append(f"proposed by: {_field(entry, 'proposed by')}")
            if _field(entry, "fact"):
                out.append(f"fact: {_field(entry, 'fact')}")
            outcomes = [f"- {o}: {_field(entry, o)}" for o in OUTCOMES if _field(entry, o)]
            if outcomes:
                out += [""] + outcomes
    return "\n".join(out) + "\n"
