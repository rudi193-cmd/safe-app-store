"""Demo tree — `@squirrel: demo load` / `@squirrel: demo clear`.

A genealogy app with an empty tree sells nothing. This seeds three
generations of the Acorn line so People/Tree/Stash/Stories show what
they're for — and clears them without touching anything real.

The Acorns are FICTIONAL, on purpose (never real-family data as demo
content). Demo rows are marked: persons carry memorial_id='DEMO',
fragments carry source='demo'. `demo clear` deletes exactly those.
"""
from responder.formatter import result_block
import db.persons as persons_db
import db.fragments as fragments_db

_DEMO_MARK = "DEMO"

# (name, born, birthplace, died) — three generations, Ahnentafel-complete
# to the grandparents so the pedigree renders full.
_FAMILY = {
    "hazel":    ("Hazel Acorn",     "1902", "Cedar Grove", "1988"),
    "alder":    ("Alder Acorn",     "1874", "Cedar Grove", "1951"),
    "fern":     ("Fern Nutkin",     "1878", "Maple Hollow", "1960"),
    "oakley":   ("Oakley Acorn",    "1841", "Tamarack County", "1913"),
    "willow":   ("Willow Burr",     "1846", "Tamarack County", "1922"),
    "chestnut": ("Chestnut Nutkin", "1850", "Old Grove", "1919"),
    "ivy":      ("Ivy Moss",        "1855", "Old Grove", "1931"),
    "rowan":    ("Rowan Pine",      "1899", "Birchbank", "1970"),
    "juniper":  ("Juniper Acorn",   "1926", "Cedar Grove", None),
}

# child -> parent, both keys of _FAMILY
_PARENTS = [
    ("hazel", "alder"), ("hazel", "fern"),
    ("alder", "oakley"), ("alder", "willow"),
    ("fern", "chestnut"), ("fern", "ivy"),
    ("juniper", "hazel"), ("juniper", "rowan"),
]

_FRAGMENTS = [
    ("Hazel Acorn", "Kept every letter in a biscuit tin. Nobody knows which cousin has the tin now.", "likely"),
    ("Oakley Acorn", "Supposedly walked to Tamarack County behind a lame ox. The ox's name was Duke.", "speculative"),
    ("Fern Nutkin", "The quilt with the oak-leaf pattern is hers. Check the initials in the corner square.", "uncertain"),
]


def cmd_demo(conn, args: list) -> str:
    action = args[0].lower() if args else ""
    if action == "load":
        return _load(conn)
    if action == "clear":
        return _clear(conn)
    return result_block("demo", "Usage: `@squirrel: demo load` — seed the fictional "
                                "Acorn family · `@squirrel: demo clear` — remove it")


def _load(conn) -> str:
    if persons_db.search_persons(conn, "Hazel Acorn"):
        return result_block("demo", "The Acorns are already in the tree. `@squirrel: demo clear` first.")
    ids = {}
    for key, (name, born, place, died) in _FAMILY.items():
        row = persons_db.add_person(conn, full_name=name, birth_date=born,
                                    birth_place=place, death_date=died,
                                    memorial_id=_DEMO_MARK,
                                    bio="Fictional — part of the demo tree.")
        ids[key] = row["id"]
    for child, parent in _PARENTS:
        persons_db.add_relationship(conn, ids[child], ids[parent], "parent")
    persons_db.add_relationship(conn, ids["hazel"], ids["rowan"], "spouse")
    for who, text, confidence in _FRAGMENTS:
        fragments_db.add_fragment(conn, person_name=who, fragment_type="story",
                                  story_text=text, source="demo",
                                  confidence=confidence)
    return result_block("demo",
        f"✓ The Acorn line is in: {len(_FAMILY)} persons, {len(_PARENTS) + 1} links, "
        f"{len(_FRAGMENTS)} stash fragments — all fictional, all marked.\n"
        "Try: `@squirrel: tree Hazel Acorn` · `@squirrel: show stash` · the People page.\n"
        "Remove any time: `@squirrel: demo clear`")


def _clear(conn) -> str:
    removed = persons_db.delete_marked_persons(conn, _DEMO_MARK)
    if not removed:
        return result_block("demo", "No demo data in the tree.")
    fragments_db.delete_by_source(conn, "demo")
    return result_block("demo", f"✓ Cleared {removed} fictional persons and their fragments. "
                                "Your real tree was never touched.")
