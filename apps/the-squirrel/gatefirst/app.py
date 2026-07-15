"""
gatefirst.app — the command surface.

Note what is absent: no gate import, no actor context, no authorized() calls.
A command can only do what its handle can do; asking for more is an
AttributeError — the capability was never minted — not a policy check.
"""


def add_person(handle, full_name, birth_date=None, birth_place=None):
    row = handle.add_person(full_name=full_name,
                            birth_date=birth_date, birth_place=birth_place)
    return f"planted #{row['id']}: {row['full_name']}"


def show_people(handle, name_query=""):
    rows = handle.search_persons(name_query)
    if not rows:
        return "(no one in the tree yet)"
    return "\n".join(
        f"#{r['id']} {r['full_name']} "
        f"({r['birth_date'] or '?'} - {r['death_date'] or '?'})"
        for r in rows)


def stash(handle, person_name, story_text, confidence="uncertain"):
    row = handle.add_fragment(person_name=person_name,
                              story_text=story_text, confidence=confidence)
    return f"stashed fragment #{row['id']} for {row['person_name']}"


def export_gedcom(handle):
    return handle.export_gedcom_text()


COMMANDS = {
    "add": add_person,
    "people": show_people,
    "stash": stash,
    "export": export_gedcom,
}


def run(handle, command, *args):
    fn = COMMANDS.get(command)
    if fn is None:
        return f"unknown command {command!r} — one of {sorted(COMMANDS)}"
    try:
        return fn(handle, *args)
    except AttributeError:
        return (f"'{command}' is not granted to this actor — "
                "the handle has no such capability")
