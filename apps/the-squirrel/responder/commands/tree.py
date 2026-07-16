from typing import Dict
import db.persons as persons_db
from db.persons import PARENT_KIND_PRIORITY
from responder.formatter import result_block


def _subject_parents(tree, subject_id):
    """The subject's parents (forward `parent` rows), sorted by kind priority —
    birth first, so the two pedigree slots are chosen meaningfully, not by
    insertion order."""
    rows = [r for r in tree["relationships"]
            if r["relationship_type"] == "parent" and r["person_id"] == subject_id]
    rows.sort(key=lambda r: PARENT_KIND_PRIORITY.get(r.get("parent_kind"), 1))
    return rows


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
        for i, rel in enumerate(parents[:2]):
            _recurse(rel["related_person_id"], ahnentafel * 2 + i, gen + 1, path | {pid})

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
        for r in parents[2:]:
            k = r.get("parent_kind")
            extra.append(f"{r['related_name']} ({k})" if k else r["related_name"])
        note = ("\n\n_Also parent(s), not shown in the two-slot pedigree: "
                + ", ".join(extra) + " — see `show kin`._")

    return result_block(
        f"tree — {person['full_name']} ({len(ancestors)} persons, {gen_count} gen)",
        chart + note
    )
