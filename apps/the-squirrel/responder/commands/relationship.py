import db.persons as persons_db
from db.persons import VALID_RELATIONSHIP_TYPES, add_relationship
from responder.formatter import result_block
from typing import Optional, Tuple


def parse_link_args(args: list) -> Optional[Tuple[str, str, str]]:
    """Parse: Oscar Mann → parent → Carl Mann. Arrow can be → or ->"""
    arrows = {"→", "->"}
    idx = [i for i, a in enumerate(args) if a in arrows]
    if len(idx) < 2:
        return None
    i1, i2 = idx[0], idx[1]
    name_a = " ".join(args[:i1]).strip()
    rel = args[i1 + 1].strip().lower() if i1 + 1 < i2 else ""
    name_b = " ".join(args[i2 + 1:]).strip()
    if not name_a or not rel or not name_b:
        return None
    return name_a, rel, name_b


def cmd_link(conn, args: list) -> str:
    parsed = parse_link_args(args)
    if parsed is None:
        return result_block("link", "Usage: `@squirrel: link Name → rel_type → Name`\nRel types: parent, child, spouse, sibling")
    name_a, rel, name_b = parsed
    if rel not in VALID_RELATIONSHIP_TYPES:
        return result_block("link", f"Invalid relationship `{rel}`. Use: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}")
    pa = persons_db.search_persons(conn, name_a)
    pb = persons_db.search_persons(conn, name_b)
    if not pa:
        return result_block("link", f"Person not found: `{name_a}`")
    if not pb:
        return result_block("link", f"Person not found: `{name_b}`")
    add_relationship(conn, pa[0]["id"], pb[0]["id"], rel)
    return result_block("link", f"✓ **{pa[0]['full_name']}** → `{rel}` → **{pb[0]['full_name']}**")


def cmd_show_kin(conn, args: list) -> str:
    if not args:
        return result_block("show kin", "Usage: `@squirrel: show kin Name`")
    matches = persons_db.search_persons(conn, " ".join(args))
    if not matches:
        return result_block("show kin", f"No person found matching `{" ".join(args)}`")
    person = matches[0]
    tree = persons_db.get_family_tree(conn, person["id"])
    rels = tree["relationships"]
    if not rels:
        return result_block("kin", f"**{person['full_name']}** — no relationships on record.")
    lines = [f"**{person['full_name']}** relationships:"]
    for r in rels:
        lines.append(f"  {r['relationship_type']}: {r['related_name']}")
    return result_block("kin", "\n".join(lines))
