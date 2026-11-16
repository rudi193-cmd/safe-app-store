"""build.py: lay the box's worlds into the table page. Python 3.9+.

    python apps/game/ui/build.py

Reads box/worlds/*.json and writes table.html from table.src.html. The page
plays a world in the browser only: it is a sketch of the table, not the
record. Rolls and rulings here are never rows; the record is game-master's.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
worlds = [json.loads(p.read_text()) for p in sorted((HERE.parent / "box" / "worlds").glob("*.json"))]
src = (HERE / "table.src.html").read_text()
assert src.count("/*__WORLDS__*/null") == 1
data = json.dumps(worlds, ensure_ascii=False).replace("</", "<\\/")
(HERE / "table.html").write_text(src.replace("/*__WORLDS__*/null", data))
print(f"table.html: {len(worlds)} worlds")
