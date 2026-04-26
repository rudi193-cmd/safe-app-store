import db.persons as persons_db
from responder.formatter import result_block


def parse_person_args(args: list) -> dict:
    """
    Flags: b.YYYY=birth_date, d.YYYY=death_date, p.Place=birth_place (underscores for spaces)
    Everything else = full_name tokens.
    """
    result = {}
    name_parts = []
    for a in args:
        if a.startswith("b."):
            result["birth_date"] = a[2:]
        elif a.startswith("d."):
            result["death_date"] = a[2:]
        elif a.startswith("p."):
            result["birth_place"] = a[2:].replace("_", " ")
        else:
            name_parts.append(a)
    result["full_name"] = " ".join(name_parts)
    return result


def cmd_add_person(conn, args: list) -> str:
    if not args:
        return result_block("add person", "Usage: `@squirrel: add person Name b.YYYY d.YYYY p.Place`")
    kwargs = parse_person_args(args)
    if not kwargs.get("full_name"):
        return result_block("add person", "Name is required.")
    person = persons_db.add_person(conn, **kwargs)
    lines = [f"✓ **{person['full_name']}** added (id={person['id']})"]
    if person.get("birth_date"):
        lines.append(f"  b. {person['birth_date']}")
    if person.get("birth_place"):
        lines.append(f"  {person['birth_place']}")
    return result_block("add person", "\n".join(lines))


def cmd_show_person(conn, args: list) -> str:
    if not args:
        return result_block("show person", "Usage: `@squirrel: show person Name`")
    query = " ".join(args)
    matches = persons_db.search_persons(conn, query)
    if not matches:
        return result_block("show person", f"No person found matching `{query}`")
    p = matches[0]
    lines = [f"**{p['full_name']}** (id={p['id']})"]
    if p.get("birth_date"):  lines.append(f"  Born:   {p['birth_date']}")
    if p.get("birth_place"): lines.append(f"  Place:  {p['birth_place']}")
    if p.get("death_date"):  lines.append(f"  Died:   {p['death_date']}")
    if p.get("burial_place"):lines.append(f"  Burial: {p['burial_place']}")
    if p.get("bio"):         lines.append(f"\n_{p['bio']}_")
    return result_block("person", "\n".join(lines))


def cmd_show_people(conn, args: list) -> str:
    query = " ".join(args) if args else ""
    people = persons_db.search_persons(conn, query)
    if not people:
        return result_block("show people", "No persons in the tree yet.")
    rows = ["| id | Name | Born | Place |", "|----|------|------|-------|"]
    for p in people:
        rows.append(f"| {p['id']} | {p['full_name']} | {p.get('birth_date','—')} | {p.get('birth_place','—')} |")
    return result_block(f"people ({len(people)})", "\n".join(rows))


def cmd_edit_person(conn, args: list) -> str:
    if len(args) < 3:
        return result_block("edit person", "Usage: `@squirrel: edit person ID field value`")
    try:
        person_id = int(args[0])
    except ValueError:
        return result_block("edit person", f"Expected numeric ID, got `{args[0]}`")
    field = args[1].lower()
    value = " ".join(args[2:])
    allowed = {"birth_date","death_date","birth_place","death_place","burial_place","bio"}
    if field not in allowed:
        return result_block("edit person", f"Unknown field `{field}`.")
    cur = conn.cursor()
    cur.execute(f"UPDATE the_squirrel.persons SET {field} = %s, updated_at = now() WHERE id = %s",
                (value, person_id))
    if cur.rowcount == 0:
        conn.rollback()
        return result_block("edit person", f"No person with id={person_id}")
    conn.commit()
    return result_block("edit person", f"✓ person {person_id} → `{field}` = `{value}`")
