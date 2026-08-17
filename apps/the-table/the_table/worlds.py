"""worlds.py -- load and validate an authored world JSON file.

A "world" is a small, self-contained story script: a cast of characters (some
seated -- played by a person -- some not), a set of places, and an ordered
list of scenes made of beats. ``StorySession`` (``story_session.py``) plays a
world through the-table's existing ``GameSession`` spine; this module only
loads one and checks its shape.

Deliberately dumb: ``load_world`` returns the parsed JSON as a plain ``dict``
(the same shape it read off disk), not a bespoke object graph. Nothing here
authors or hardcodes any particular world -- the loader reads whatever path
it is given, worked out from the "PINNED WORLD SCHEMA" this file mirrors
exactly. The only world shipped alongside this app, ``worlds/hasbeen.json``,
is authored data, not code, and is loaded the same way any other world file
would be.

Validation is intentionally shallow-but-complete: every field the pinned
schema promises is checked to exist and be the right JSON type, every
cross-reference the schema implies (a scene's ``place`` must name a real
place, a beat's ``suggests`` must name a real stat, a character's ``stats``
keys must be a subset of the world's ``stats``) is checked, and every
violation raises ``WorldError`` with a message naming exactly what was wrong
and where -- so a bad world fails loudly and legibly, at load time, not with
a confusing ``KeyError`` three calls deep into ``StorySession``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class WorldError(ValueError):
    """Raised when a world file is missing, unreadable, or does not match
    the pinned world schema. Always carries a human-legible reason."""


def _fail(path: Any, msg: str) -> None:
    raise WorldError(f"world {path!r}: {msg}")


def _require_keys(path: Any, obj: dict, keys: tuple, where: str) -> None:
    if not isinstance(obj, dict):
        _fail(path, f"{where} must be a JSON object, got {type(obj).__name__}")
    missing = [k for k in keys if k not in obj]
    if missing:
        _fail(path, f"{where} is missing required key(s): {missing}")


def _require_type(path: Any, value: Any, types, where: str) -> None:
    if not isinstance(value, types):
        want = types.__name__ if isinstance(types, type) else " or ".join(t.__name__ for t in types)
        _fail(path, f"{where} must be a {want}, got {type(value).__name__}")


def _validate_character(path: Any, char: dict, index: int, stat_names: set) -> None:
    where = f"characters[{index}]"
    _require_keys(path, char, ("id", "name", "role", "seat", "stats"), where)
    _require_type(path, char["id"], str, f"{where}.id")
    _require_type(path, char["name"], str, f"{where}.name")
    _require_type(path, char["role"], str, f"{where}.role")
    _require_type(path, char["seat"], bool, f"{where}.seat")
    _require_type(path, char["stats"], dict, f"{where}.stats")
    unknown = set(char["stats"]) - stat_names
    if unknown:
        _fail(path, f"{where}.stats names stat(s) not in the world's stats list: {sorted(unknown)}")
    for stat_name, value in char["stats"].items():
        _require_type(path, value, (int, float), f"{where}.stats[{stat_name!r}]")


def _validate_place(path: Any, place: dict, index: int) -> None:
    where = f"places[{index}]"
    _require_keys(path, place, ("id", "name"), where)
    _require_type(path, place["id"], str, f"{where}.id")
    _require_type(path, place["name"], str, f"{where}.name")
    if "desc" in place:
        _require_type(path, place["desc"], str, f"{where}.desc")


def _validate_beat(path: Any, beat: dict, scene_index: int, beat_index: int, stat_names: set) -> None:
    where = f"scenes[{scene_index}].beats[{beat_index}]"
    _require_keys(path, beat, ("id", "kind", "prompt"), where)
    _require_type(path, beat["id"], str, f"{where}.id")
    _require_type(path, beat["prompt"], str, f"{where}.prompt")
    kind = beat["kind"]
    if kind == "action":
        _require_keys(path, beat, ("suggests", "outcomes"), where)
        _require_type(path, beat["suggests"], str, f"{where}.suggests")
        if beat["suggests"] not in stat_names:
            _fail(path, f"{where}.suggests={beat['suggests']!r} is not one of the world's stats {sorted(stat_names)}")
        _require_type(path, beat["outcomes"], dict, f"{where}.outcomes")
        _require_keys(path, beat["outcomes"], ("strong", "weak", "miss"), f"{where}.outcomes")
        for bucket in ("strong", "weak", "miss"):
            _require_type(path, beat["outcomes"][bucket], str, f"{where}.outcomes.{bucket}")
    elif kind == "decision":
        _require_keys(path, beat, ("proposes",), where)
        _require_type(path, beat["proposes"], dict, f"{where}.proposes")
        _require_keys(path, beat["proposes"], ("fact", "proposed_by"), f"{where}.proposes")
        _require_type(path, beat["proposes"]["fact"], str, f"{where}.proposes.fact")
        _require_type(path, beat["proposes"]["proposed_by"], str, f"{where}.proposes.proposed_by")
    else:
        _fail(path, f"{where}.kind must be 'action' or 'decision', got {kind!r}")


def _validate_scene(path: Any, scene: dict, index: int, stat_names: set, place_ids: set) -> None:
    where = f"scenes[{index}]"
    _require_keys(path, scene, ("id", "title", "place", "opening", "beats"), where)
    _require_type(path, scene["id"], str, f"{where}.id")
    _require_type(path, scene["title"], str, f"{where}.title")
    _require_type(path, scene["place"], str, f"{where}.place")
    if scene["place"] not in place_ids:
        _fail(path, f"{where}.place={scene['place']!r} does not name a place in the world's places list")
    _require_type(path, scene["opening"], list, f"{where}.opening")
    for i, line in enumerate(scene["opening"]):
        _require_type(path, line, str, f"{where}.opening[{i}]")
    _require_type(path, scene["beats"], list, f"{where}.beats")
    if not scene["beats"]:
        _fail(path, f"{where}.beats must not be empty")
    seen_beat_ids = set()
    for i, beat in enumerate(scene["beats"]):
        _validate_beat(path, beat, index, i, stat_names)
        if beat["id"] in seen_beat_ids:
            _fail(path, f"{where} has a duplicate beat id {beat['id']!r}")
        seen_beat_ids.add(beat["id"])


def _validate_world(path: Any, world: Any) -> dict:
    _require_type(path, world, dict, "the world")
    _require_keys(path, world, ("id", "title", "setting", "stats", "base_stat",
                                "characters", "places", "scenes"), "the world")

    _require_type(path, world["id"], str, "world.id")
    _require_type(path, world["title"], str, "world.title")
    _require_type(path, world["setting"], str, "world.setting")

    _require_type(path, world["stats"], list, "world.stats")
    if not world["stats"]:
        _fail(path, "world.stats must not be empty")
    for i, stat in enumerate(world["stats"]):
        _require_type(path, stat, str, f"world.stats[{i}]")
    if len(set(world["stats"])) != len(world["stats"]):
        _fail(path, f"world.stats has duplicate names: {world['stats']}")
    stat_names = set(world["stats"])

    _require_type(path, world["base_stat"], (int, float), "world.base_stat")

    _require_type(path, world["characters"], list, "world.characters")
    if not world["characters"]:
        _fail(path, "world.characters must not be empty")
    seen_char_ids = set()
    for i, char in enumerate(world["characters"]):
        _validate_character(path, char, i, stat_names)
        if char["id"] in seen_char_ids:
            _fail(path, f"characters[{i}] has a duplicate id {char['id']!r}")
        seen_char_ids.add(char["id"])
    if not any(c["seat"] for c in world["characters"]):
        _fail(path, "at least one character must have seat: true -- a world with no seats has no one to play it")

    _require_type(path, world["places"], list, "world.places")
    seen_place_ids = set()
    for i, place in enumerate(world["places"]):
        _validate_place(path, place, i)
        if place["id"] in seen_place_ids:
            _fail(path, f"places[{i}] has a duplicate id {place['id']!r}")
        seen_place_ids.add(place["id"])
    place_ids = seen_place_ids

    _require_type(path, world["scenes"], list, "world.scenes")
    if not world["scenes"]:
        _fail(path, "world.scenes must not be empty")
    seen_scene_ids = set()
    for i, scene in enumerate(world["scenes"]):
        _validate_scene(path, scene, i, stat_names, place_ids)
        if scene["id"] in seen_scene_ids:
            _fail(path, f"scenes[{i}] has a duplicate id {scene['id']!r}")
        seen_scene_ids.add(scene["id"])

    return world


def load_world(path) -> dict:
    """Read, parse, and validate a world JSON file at ``path``.

    Returns the world as a plain ``dict`` (the validated JSON, untouched --
    ``StorySession`` indexes into it directly). Raises ``WorldError`` with a
    specific, human-legible reason on anything from a missing file to a
    malformed beat three scenes in.
    """
    p = Path(path)
    if not p.exists():
        _fail(str(p), "file does not exist")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        _fail(str(p), f"could not read file: {e}")
    try:
        world = json.loads(text)
    except json.JSONDecodeError as e:
        _fail(str(p), f"not valid JSON: {e}")
    return _validate_world(str(p), world)


# ── the worlds index ─────────────────────────────────────────────────────────
#
# The story-side parallel to registry.py's game index, and deliberately even
# smaller: a story world is DATA (a JSON file), not a factory, so "registering"
# one is dropping a validated file into ``worlds/`` -- no code change, no
# register() call. ``available_worlds()`` is the discovery seam that makes a
# shipped world first-class: the test suite loads and plays EVERY name it
# returns, so a new world is covered the moment it lands, exactly the way
# adding a game to registry.py is one line and the registry tests pick it up.
#
# NOTE ON WHY STORY WORLDS ARE NOT IN registry.py: registry.py's games are
# auto-driven to terminal by a policy (proof.py, baseline.py, test_registry.py
# all iterate registry.games() and drive each with random/first-legal moves).
# A story world's decision beat has ZERO legal moves by design -- only a named
# human's seal() advances it -- so no policy can carry one to terminal. Putting
# a world in the game registry would break those policy-driven sweeps. The
# worlds index is the correct home: discovered and validated, but driven by a
# loop that seals decisions with a human, never by a blind policy.

WORLDS_DIR = Path(__file__).resolve().parent.parent / "worlds"


def available_worlds() -> dict:
    """``name -> Path`` for every shipped world JSON under ``worlds/``.

    The name is the file stem (``worlds/aetheris.json`` -> ``"aetheris"``).
    Returns an empty dict if the directory is absent. This does not validate
    the files -- it only lists them; ``load_named_world`` (or ``load_world``)
    validates on read, so a malformed file still fails loudly when opened.
    """
    if not WORLDS_DIR.is_dir():
        return {}
    return {p.stem: p for p in sorted(WORLDS_DIR.glob("*.json"))}


def load_named_world(name: str) -> dict:
    """Load and validate the shipped world registered under ``name`` (its file
    stem under ``worlds/``). Raises ``WorldError`` if no such world is shipped
    (naming the ones that are) or if the file fails validation."""
    worlds = available_worlds()
    if name not in worlds:
        _fail(name, f"no shipped world named {name!r}; available: {sorted(worlds)}")
    return load_world(worlds[name])
