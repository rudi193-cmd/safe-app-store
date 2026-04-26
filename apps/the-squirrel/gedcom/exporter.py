from datetime import datetime
from pathlib import Path
from typing import List, Dict

def build_gedcom_lines(persons: List[Dict], relationships: List[Dict]) -> List[str]:
    now = datetime.utcnow()
    lines = [
        "0 HEAD", "1 SOUR TheSquirrel", "2 VERS 2.0",
        f"1 DATE {now.strftime('%d %b %Y').upper()}",
        "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8",
    ]
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
    lines.append("0 TRLR")
    return lines

def export(conn, output_path: Path) -> int:
    import sap.core.gate as _gate
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("SELECT * FROM the_squirrel.persons WHERE is_deleted = FALSE")
    rows = cur.fetchall(); cols = [d[0] for d in cur.description]
    persons = [dict(zip(cols, r)) for r in rows]
    cur.execute("SELECT * FROM the_squirrel.relationships")
    rows = cur.fetchall(); cols = [d[0] for d in cur.description]
    rels = [dict(zip(cols, r)) for r in rows]
    lines = build_gedcom_lines(persons, rels)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(persons)
