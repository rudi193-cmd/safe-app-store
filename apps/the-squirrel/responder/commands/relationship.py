import db.persons as persons_db
from db.persons import VALID_RELATIONSHIP_TYPES, VALID_PARENT_KINDS, add_relationship
from responder.formatter import result_block
from typing import Optional, Tuple

_USAGE = ("Usage: `@squirrel: link Name → rel → Name`\n"
          "Rel: parent, child, spouse, sibling. Parent/child may carry a kind:\n"
          "`birth parent`, `adopted parent`, `foster parent`, `step parent` "
          "(e.g. `link Steve Jobs → adopted parent → Paul Jobs`).")


def parse_link_args(args: list) -> Optional[Tuple[str, str, Optional[str], str]]:
    """Parse: Name → [kind] rel → Name. Arrow can be → or ->.
    Returns (name_a, rel_type, parent_kind|None, name_b)."""
    arrows = {"→", "->"}
    idx = [i for i, a in enumerate(args) if a in arrows]
    if len(idx) < 2:
        return None
    i1, i2 = idx[0], idx[1]
    name_a = " ".join(args[:i1]).strip()
    middle = [w.lower() for w in args[i1 + 1:i2]]
    name_b = " ".join(args[i2 + 1:]).strip()
    if not name_a or not middle or not name_b:
        return None
    # A kind may appear on either side of the base type ("adopted parent" or
    # "parent adopted"). Split kinds from non-kinds so word order doesn't
    # silently swallow the kind; a lone kind with no base type (e.g. "birth")
    # falls through as an invalid rel, which cmd_link reports rather than
    # accepting silently.
    kinds = [w for w in middle if w in VALID_PARENT_KINDS]
    rest = [w for w in middle if w not in VALID_PARENT_KINDS]
    kind = kinds[0] if kinds else None
    rel = rest[0] if rest else middle[0]
    return name_a, rel, kind, name_b


def cmd_link(conn, args: list) -> str:
    parsed = parse_link_args(args)
    if parsed is None:
        return result_block("link", _USAGE)
    name_a, rel, kind, name_b = parsed
    if rel not in VALID_RELATIONSHIP_TYPES:
        return result_block("link", f"Invalid relationship `{rel}`. Use: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}")
    pa = persons_db.search_persons(conn, name_a)
    pb = persons_db.search_persons(conn, name_b)
    if not pa:
        return result_block("link", f"Person not found: `{name_a}`")
    if not pb:
        return result_block("link", f"Person not found: `{name_b}`")
    try:
        add_relationship(conn, pa[0]["id"], pb[0]["id"], rel, parent_kind=kind)
    except ValueError as e:
        return result_block("link", f"✗ {e}")
    label = f"{kind} {rel}" if kind else rel
    return result_block("link", f"✓ **{pa[0]['full_name']}** → `{label}` → **{pb[0]['full_name']}**")


def cmd_show_kin(conn, args: list) -> str:
    if not args:
        return result_block("show kin", "Usage: `@squirrel: show kin Name`")
    matches = persons_db.search_persons(conn, " ".join(args))
    if not matches:
        return result_block("show kin", f"No person found matching `{' '.join(args)}`")
    person = matches[0]
    tree = persons_db.get_family_tree(conn, person["id"])
    rels = tree["relationships"]
    if not rels:
        return result_block("kin", f"**{person['full_name']}** — no relationships on record.")
    lines = [f"**{person['full_name']}** relationships:"]
    _invert = {"parent": "child", "child": "parent"}
    for r in rels:
        rtype = r["relationship_type"]
        if r.get("related_person_id") == person["id"]:
            rtype = _invert.get(rtype, rtype)  # reverse row: label inverts
        kind = r.get("parent_kind")
        label = f"{kind} {rtype}" if kind and rtype in ("parent", "child") else rtype
        lines.append(f"  {label}: {r['related_name']}")
    return result_block("kin", "\n".join(lines))
