from typing import Dict
import db.persons as persons_db
from responder.formatter import result_block


def build_ancestors_dict(conn, person_id: int, depth: int = 3) -> Dict[int, Dict]:
    """Build Ahnentafel-numbered ancestor dict. 1=subject, 2=father, 3=mother, 4-7=grandparents."""
    result = {}

    def _recurse(pid, ahnentafel, gen):
        if gen > depth or ahnentafel > 127:
            return
        tree = persons_db.get_family_tree(conn, pid)
        if tree["person"] is None:
            return
        result[ahnentafel] = tree["person"]
        parents = [r for r in tree["relationships"] if r["relationship_type"] == "parent"]
        for i, rel in enumerate(parents[:2]):
            _recurse(rel["related_person_id"], ahnentafel * 2 + i, gen + 1)

    _recurse(person_id, 1, 1)
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
        return result_block("tree", f"No person found matching `{" ".join(args)}`")
    person = matches[0]
    ancestors = build_ancestors_dict(conn, person["id"], depth=3)
    chart = render_pedigree(person["full_name"], ancestors)
    gen_count = max((k.bit_length() - 1 for k in ancestors), default=0)
    return result_block(
        f"tree — {person['full_name']} ({len(ancestors)} persons, {gen_count} gen)",
        chart
    )
