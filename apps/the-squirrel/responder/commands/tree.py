from typing import Dict
import db.persons as persons_db
from db.persons import PARENT_KIND_PRIORITY
from responder.formatter import result_block


def _subject_parents(tree, subject_id):
    """The subject's parents, from BOTH grammars: forward `parent` rows
    (subject, X, 'parent') and reverse `child` rows (X, subject, 'child') —
    both mean X is the subject's parent. Returns normalized dicts
    {id, name, kind}, sorted by kind priority so the two pedigree slots go
    to birth parents first, not by insertion order.

    A reverse `parent` row (X, subject, 'parent') means the subject is X's
    parent and is correctly excluded — that's the B-001 distinction."""
    out = []
    for r in tree["relationships"]:
        t = r["relationship_type"]
        if t == "parent" and r["person_id"] == subject_id:
            out.append({"id": r["related_person_id"], "name": r.get("related_name"),
                        "kind": r.get("parent_kind")})
        elif t == "child" and r.get("related_person_id") == subject_id:
            # reverse: person_id is the parent; related_name is its name
            out.append({"id": r["person_id"], "name": r.get("related_name"),
                        "kind": r.get("parent_kind")})
    out.sort(key=lambda p: PARENT_KIND_PRIORITY.get(p["kind"], 1))
    return out


def build_ancestors_dict(conn, person_id: int, depth: int = 3) -> Dict[int, Dict]:
    """Build Ahnentafel-numbered ancestor dict. 1=subject, 2=father, 3=mother, 4-7=grandparents."""
    result = {}

    def _recurse(pid, ahnentafel, gen, path):
        # path is PATH-LOCAL, not global: a person legitimately appears in two
        # slots (same grandfather on both sides), so we only refuse to revisit
        # an id already on the CURRENT ancestry chain — that's a cycle.
        if gen > depth or ahnentafel > 127 or pid in path:
            return
        tree = persons_db.get_family_tree(conn, pid)
        if tree["person"] is None:
            return
        result[ahnentafel] = tree["person"]
        # Only forward rows: (pid, X, 'parent') means X is pid's parent.
        # Reverse rows (child, pid, 'parent') land in the same list from the
        # UNION and must not be walked — they'd recurse into pid itself.
        # Sorted by kind so the two Ahnentafel slots go to birth parents first
        # (B-011): which two show is a rule now, not insertion luck.
        parents = _subject_parents(tree, pid)
        for i, par in enumerate(parents[:2]):
            _recurse(par["id"], ahnentafel * 2 + i, gen + 1, path | {pid})

    _recurse(person_id, 1, 1, frozenset())
    return result


def render_pedigree(subject_name: str, ancestors: Dict) -> str:
    def fmt(n):
        p = ancestors.get(n)
        if not p:
            return "Unknown"
        name = p.get("full_name", "Unknown")
        year = p.get("birth_date", "")
        return f"{name} ({year})" if year else name

    lines = []
    pad = "    "
    has_g = any(4 <= k <= 7 for k in ancestors)

    if has_g:
        if ancestors.get(4): lines.append(f"{pad*2}┌─ {fmt(4)}")
        if ancestors.get(2): lines.append(f"{pad}┌─ {fmt(2)}")
        if ancestors.get(5): lines.append(f"{pad*2}└─ {fmt(5)}")
    elif ancestors.get(2):
        lines.append(f"{pad}┌─ {fmt(2)}")

    lines.append(f"{subject_name} ──────┤")

    if has_g:
        if ancestors.get(6): lines.append(f"{pad*2}┌─ {fmt(6)}")
        if ancestors.get(3): lines.append(f"{pad}└─ {fmt(3)}")
        if ancestors.get(7): lines.append(f"{pad*2}└─ {fmt(7)}")
    elif ancestors.get(3):
        lines.append(f"{pad}└─ {fmt(3)}")

    return "```\n" + "\n".join(lines) + "\n```"


def cmd_tree(conn, args: list) -> str:
    if not args:
        return result_block("tree", "Usage: `@squirrel: tree Name`")
    matches = persons_db.search_persons(conn, " ".join(args))
    if not matches:
        from sap.core import gaps
        gaps.log("unknown_person", " ".join(args), detail="asked in tree")
        return result_block("tree", f"No person found matching `{' '.join(args)}`")
    person = matches[0]
    ancestors = build_ancestors_dict(conn, person["id"], depth=3)
    chart = render_pedigree(person["full_name"], ancestors)
    gen_count = max((k.bit_length() - 1 for k in ancestors), default=0)

    # B-011: a pedigree has two parent slots; if the subject has more parents
    # (adoptive + biological), name the ones that don't fit — never drop them
    # in silence.
    tree = persons_db.get_family_tree(conn, person["id"])
    parents = _subject_parents(tree, person["id"])
    note = ""
    if len(parents) > 2:
        extra = []
        for par in parents[2:]:
            k = par.get("kind")
            extra.append(f"{par['name']} ({k} parent)" if k else par["name"])
        note = ("\n\n_Also parent(s), not shown in the two-slot pedigree: "
                + ", ".join(extra) + " — see `show kin`._")

    return result_block(
        f"tree — {person['full_name']} ({len(ancestors)} persons, {gen_count} gen)",
        chart + note
    )
