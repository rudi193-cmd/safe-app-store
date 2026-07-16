from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# GEDCOM 5.5.1 PEDI linkage values. 'step' has no standard PEDI, so it exports
# as a plain FAMC plus a NOTE rather than being silently coerced or dropped.
_PEDI = {"birth": "birth", "adopted": "adopted", "foster": "foster"}


def _bucket(kind):
    """Which family a parent-link belongs to. birth and untagged (None) share
    the 'birth' bucket, so a couple where only one link is tagged still exports
    as ONE family, not two single-parent ones; adopted/foster/step each get
    their own bucket."""
    return kind if kind in ("adopted", "foster", "step") else "birth"


def _families(relationships):
    """Group parent/child edges into families keyed by (child, bucket), so a
    person born into one family and adopted into another gets two FAMC links
    with distinct PEDI. Returns (fam, fam_ids, child_to_famc) where each famc
    entry is (fam_id, pedi_or_None, note_or_None)."""
    edges = []
    for r in relationships:
        t = r.get("relationship_type")
        if t == "parent":
            edges.append((r["person_id"], r["related_person_id"], r.get("parent_kind")))
        elif t == "child":
            edges.append((r["related_person_id"], r["person_id"], r.get("parent_kind")))
    fam = OrderedDict()
    for child_id, parent_id, kind in edges:
        key = (child_id, _bucket(kind))
        info = fam.setdefault(key, {"child": child_id, "bucket": key[1],
                                    "parents": [], "kinds": set()})
        if parent_id not in info["parents"]:
            info["parents"].append(parent_id)
        info["kinds"].add(kind)
    fam_ids = {key: i for i, key in enumerate(fam, start=1)}
    child_to_famc = {}
    for key, fid in fam_ids.items():
        bucket = fam[key]["bucket"]
        kinds = fam[key]["kinds"]
        if bucket in ("adopted", "foster"):
            pedi, note = bucket, None
        elif bucket == "step":
            pedi, note = None, "step-parent linkage"
        else:  # birth bucket — assert PEDI birth only if explicitly tagged
            pedi = "birth" if "birth" in kinds else None
            note = None
        child_to_famc.setdefault(key[0], []).append((fid, pedi, note))
    return fam, fam_ids, child_to_famc


def build_gedcom_lines(persons: List[Dict], relationships: List[Dict]) -> List[str]:
    now = datetime.utcnow()
    lines = [
        "0 HEAD", "1 SOUR TheSquirrel", "2 VERS 2.0",
        f"1 DATE {now.strftime('%d %b %Y').upper()}",
        "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8",
    ]
    fam, fam_ids, child_to_famc = _families(relationships or [])
    name_of = {p["id"]: p["full_name"] for p in persons}
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
        for fid, pedi, note in child_to_famc.get(pid, []):
            lines.append(f"1 FAMC @F{fid}@")
            if pedi:
                lines.append(f"2 PEDI {pedi}")
            elif note:
                lines.append(f"2 NOTE {note}")
    for key, fid in fam_ids.items():
        child_id = key[0]
        parents = fam[key]["parents"]
        lines.append(f"0 @F{fid}@ FAM")
        if len(parents) >= 1: lines.append(f"1 HUSB @I{parents[0]}@")
        if len(parents) >= 2: lines.append(f"1 WIFE @I{parents[1]}@")
        # A FAM holds one couple; parents beyond two can't be HUSB/WIFE, so
        # name them in NOTEs rather than dropping the relationship silently.
        for extra in parents[2:]:
            nm = name_of.get(extra, "")
            lines.append(f"1 NOTE additional parent: @I{extra}@{(' ' + nm) if nm else ''}")
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
