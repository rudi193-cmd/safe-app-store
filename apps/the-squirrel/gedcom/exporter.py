from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# GEDCOM 5.5.1 PEDI linkage values. 'step' has no standard PEDI, so it exports
# as a plain FAMC plus a NOTE rather than being silently coerced or dropped.
_PEDI = {"birth": "birth", "adopted": "adopted", "foster": "foster"}


def _families(relationships):
    """Group parent/child edges into families keyed by (child, kind), so a
    person born into one family and adopted into another gets two FAMC links
    with distinct PEDI. Returns (fam_ordered, fam_ids, child_to_famc)."""
    edges = []
    for r in relationships:
        t = r.get("relationship_type")
        if t == "parent":
            edges.append((r["person_id"], r["related_person_id"], r.get("parent_kind")))
        elif t == "child":
            edges.append((r["related_person_id"], r["person_id"], r.get("parent_kind")))
    fam = OrderedDict()
    for child_id, parent_id, kind in edges:
        key = (child_id, kind)
        fam.setdefault(key, {"child": child_id, "kind": kind, "parents": []})
        if parent_id not in fam[key]["parents"]:
            fam[key]["parents"].append(parent_id)
    fam_ids = {key: i for i, key in enumerate(fam, start=1)}
    child_to_famc = {}
    for (child_id, kind), fid in fam_ids.items():
        child_to_famc.setdefault(child_id, []).append((fid, kind))
    return fam, fam_ids, child_to_famc


def build_gedcom_lines(persons: List[Dict], relationships: List[Dict]) -> List[str]:
    now = datetime.utcnow()
    lines = [
        "0 HEAD", "1 SOUR TheSquirrel", "2 VERS 2.0",
        f"1 DATE {now.strftime('%d %b %Y').upper()}",
        "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8",
    ]
    fam, fam_ids, child_to_famc = _families(relationships or [])
    for p in persons:
        pid = p["id"]
        lines.append(f"0 @I{pid}@ INDI")
        lines.append(f"1 NAME {p['full_name']}")
        parts = p["full_name"].rsplit(" ", 1)
        if len(parts) == 2:
            lines += [f"2 GIVN {parts[0]}", f"2 SURN {parts[1]}"]
        if p.get("birth_date") or p.get("birth_place"):
            lines.append("1 BIRT")
            if p.get("birth_date"):  lines.append(f"2 DATE {p['birth_date']}")
            if p.get("birth_place"): lines.append(f"2 PLAC {p['birth_place']}")
        if p.get("death_date") or p.get("death_place"):
            lines.append("1 DEAT")
            if p.get("death_date"):  lines.append(f"2 DATE {p['death_date']}")
            if p.get("death_place"): lines.append(f"2 PLAC {p['death_place']}")
        if p.get("burial_place"):
            lines += ["1 BURI", f"2 PLAC {p['burial_place']}"]
        # FAMC — how this person is a child of each family they belong to.
        for fid, kind in child_to_famc.get(pid, []):
            lines.append(f"1 FAMC @F{fid}@")
            if kind in _PEDI:
                lines.append(f"2 PEDI {_PEDI[kind]}")
            elif kind:
                lines.append(f"2 NOTE {kind}-parent linkage")
    for (child_id, kind), fid in fam_ids.items():
        parents = fam[(child_id, kind)]["parents"]
        lines.append(f"0 @F{fid}@ FAM")
        if len(parents) >= 1: lines.append(f"1 HUSB @I{parents[0]}@")
        if len(parents) >= 2: lines.append(f"1 WIFE @I{parents[1]}@")
        lines.append(f"1 CHIL @I{child_id}@")
    lines.append("0 TRLR")
    return lines

def export(conn, output_path: Path) -> int:
    import db.persons as persons_db
    persons = persons_db.all_persons(conn)
    rels = persons_db.all_relationships(conn)
    lines = build_gedcom_lines(persons, rels)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(persons)
