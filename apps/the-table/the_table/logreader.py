"""logreader.py — read a log as a story.

The piece the whole Hasbeen scene was about: take a log, read it *as a story*
rather than as rows, and hand it to the StorySession engine so it gets played,
scored, and — the point — HALTED at whatever a person never sealed.

A "log" here is a small JSON document: a header plus an ordered list of
entries, each entry a beat. An action entry is something that happened (with a
strong/weak/miss reading, the way the story might land); a decision entry is a
claim the log *inherited but never witnessed* — the thing the engine can't
score past until a human decides. ``world_from_log`` maps that log onto the
exact world schema ``worlds.py`` validates, so the existing ``StorySession``
plays it with no new plumbing — the log becomes a world, the world gets read.

The log is DATA. It stays in a box (a path the caller supplies); this module is
the *reader*, and readers ship — the log never does. ``story_from_log`` writes
the derived world into a box dir and returns its path, so a caller can do:

    from the_table.story_session import StorySession
    from the_table.logreader import story_from_log
    story = StorySession(story_from_log("~/box/session.log.json"))

and then play it exactly like any other world — right up to `who decides?`.
"""
from __future__ import annotations

import json
import os
import tempfile

_STATS = ["Grit", "Weird", "Cute", "Cool"]


def load_log(path: str) -> dict:
    """Read a log JSON from a box path. Raises the usual json/OS errors."""
    with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
        return json.load(f)


def world_from_log(log: dict) -> dict:
    """Map a log document onto the world schema worlds.py validates.

    Log shape:
      {"id","title","setting","characters":[...], "scene_title"?, "opening"?,
       "entries":[ {"kind":"action","prompt","suggests","outcomes":{strong,weak,miss}}
                   | {"kind":"decision","prompt","proposes":{fact,proposed_by}} ]}
    """
    if not log.get("entries"):
        raise ValueError("log has no entries")
    beats = []
    for i, e in enumerate(log["entries"]):
        bid = e.get("id", f"e{i + 1}")
        if e.get("kind") == "decision":
            beats.append({"id": bid, "kind": "decision",
                          "prompt": e.get("prompt", ""), "proposes": e["proposes"]})
        else:
            beats.append({"id": bid, "kind": "action", "prompt": e.get("prompt", ""),
                          "suggests": e.get("suggests", "Cool"), "outcomes": e["outcomes"]})
    return {
        "id": log["id"],
        "title": log["title"],
        "setting": log.get("setting", ""),
        "stats": _STATS,
        "base_stat": log.get("base_stat", 2),
        "characters": log["characters"],
        "places": [{"id": "log", "name": "the log", "desc": log.get("setting", "")}],
        "scenes": [{
            "id": "s1", "title": log.get("scene_title", "the read"), "place": "log",
            "opening": log.get("opening", []), "beats": beats,
        }],
    }


def story_from_log(log_path: str, box_dir: str | None = None) -> str:
    """Read the log at ``log_path``, derive a world, write it into a box dir,
    and return the derived world's path (ready for ``StorySession(path)``).
    The derived world is data too — it lands in a box, not the repo."""
    world = world_from_log(load_log(log_path))
    box = box_dir or tempfile.mkdtemp(prefix="logworld-")
    os.makedirs(box, exist_ok=True)
    world_path = os.path.join(box, f"{world['id']}.world.json")
    with open(world_path, "w", encoding="utf-8") as f:
        json.dump(world, f, ensure_ascii=False, indent=2)
    return world_path
