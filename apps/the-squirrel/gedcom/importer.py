import re
from pathlib import Path
from typing import List, Dict
import db.fragments as fragments_db
import sap.core.gate as _gate

def _parse_gedcom(text: str) -> List[Dict]:
    persons = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\d+)\s+(@\S+@\s+)?(\S+)\s*(.*)?$', line)
        if not m:
            continue
        level = int(m.group(1))
        tag_id = (m.group(2) or "").strip()
        tag = m.group(3)
        value = (m.group(4) or "").strip()
        if level == 0 and "INDI" in (tag_id + " " + tag):
            if current:
                persons.append(current)
            current = {"_id": tag_id.strip("@"), "name": "",
                       "birth_date": None, "birth_place": None,
                       "death_date": None, "_in_birt": False, "_in_deat": False}
        elif current is not None:
            if tag == "NAME":
                current["name"] = value.replace("/", "").strip()
            elif tag == "BIRT":
                current["_in_birt"] = True; current["_in_deat"] = False
            elif tag == "DEAT":
                current["_in_deat"] = True; current["_in_birt"] = False
            elif tag == "DATE":
                if current["_in_birt"]: current["birth_date"] = value
                elif current["_in_deat"]: current["death_date"] = value
            elif tag == "PLAC" and current["_in_birt"]:
                current["birth_place"] = value
    if current:
        persons.append(current)
    return persons

def import_ged(conn, filepath: Path) -> int:
    _gate.authorized("write")
    text = filepath.read_text(encoding="utf-8", errors="replace")
    persons = _parse_gedcom(text)
    count = 0
    for p in persons:
        if not p.get("name"):
            continue
        story = f"GEDCOM import: {p['name']}"
        if p.get("birth_date"):  story += f", b.{p['birth_date']}"
        if p.get("birth_place"): story += f", {p['birth_place']}"
        if p.get("death_date"):  story += f", d.{p['death_date']}"
        fragments_db.add_fragment(conn, person_name=p["name"],
                                  fragment_type="document", story_text=story,
                                  source=filepath.name, confidence="likely")
        count += 1
    return count
