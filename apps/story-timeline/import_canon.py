"""Import what a game table made true onto a writer's timeline.

The other half of export_story.py, and of the-table's StorySession design:
"the play grows the world". Willow's game box writes the facts its game
master sealed as markdown (demo/game-box/session.py export-canon there):

    <!-- canon from a game box: record <hash>, <n> rows -->
    # What the table made true

    - Prince Aldric is free, and owes Brann's goats a favour.
      sealed: proposal:<sha256> | row 41 | clockwork-cellar::room::free

Each fact becomes a commonplace item of kind `canon`, promoted onto the
timeline as a `fact` entry with story-timeline's own promote_to_timeline
(derived_from and appears_on_timeline edges, SOIL mirrors when a session
has a uuid). The entry carries its provenance in its own fields too, so it
holds without SOIL: the seal's proposal, its row, where in play it came
from, and which record. A fact whose seal is already on the timeline is
skipped, so importing again adds only what's new.

Only what was sealed is in the file, and only the writer running this puts
it on the timeline: the game master seals, the writer promotes.
"""

from __future__ import annotations

import re

import story_protocol as proto
import timeline_db as db

HEAD = re.compile(r"^<!-- canon from a game box: record ([0-9a-f]{64}), \d+ rows -->$")
FACT = re.compile(r"^- (.+)$")
SEAL = re.compile(r"^\s+sealed: (proposal:[0-9a-f]{64}) \| row (\d+) \| (.+)$")


def read(text: str) -> tuple[str, list[dict]]:
    """(the record's hash, each sealed fact), or ValueError naming the line."""
    lines = text.splitlines()
    if not lines or not (m := HEAD.match(lines[0].strip())):
        raise ValueError("line 1: not a game box's canon (its first line names the record)")
    record, facts, fact = m.group(1), [], None
    for at, line in enumerate(lines[1:], 2):
        if not line.strip() or line.startswith("# "):
            continue
        if fact is None and (m := FACT.match(line)):
            fact = (at, m.group(1).strip())
        elif fact is not None and (m := SEAL.match(line)):
            facts.append({"fact": fact[1], "subject": m.group(1), "row": int(m.group(2)), "from": m.group(3).strip()})  # fmt: skip
            fact = None
        else:
            raise ValueError(f"line {at}: a fact is `- what` and then `  sealed: proposal:... | row N | where`")  # fmt: skip
    if fact is not None:
        raise ValueError(f"line {fact[0]}: a fact with no seal under it")
    return record, facts


def _title(fact: str, width: int = 80) -> str:
    if len(fact) <= width:
        return fact
    return fact[:width].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def import_canon(text: str, timeline_id: str, *, uuid: str | None = None, mirror: bool = True) -> dict:  # fmt: skip
    """Put each sealed fact not already there on the timeline: {added, skipped}."""
    if proto.get_timeline(timeline_id) is None:
        raise ValueError(f"timeline not found: {timeline_id}")
    record, facts = read(text)
    there = {e["fields"].get("canon subject") for e in proto.list_timeline_entries(timeline_id)}
    added, skipped = [], []
    for f in facts:
        if f["subject"] in there:
            skipped.append(f)
            continue
        provenance = {"canon subject": f["subject"], "sealed row": f["row"], "from": f["from"], "record": record}  # fmt: skip
        item = proto.create_commonplace_item(_title(f["fact"]), content=f["fact"], source_kind="canon", tags="game-box")  # fmt: skip
        db.update_node(item["id"], {**item["fields"], **provenance})
        result = proto.promote_to_timeline(item["id"], timeline_id, entry_kind="fact", uuid=uuid, mirror=mirror)  # fmt: skip
        entry = result["entry"]
        db.update_node(entry["id"], {**entry["fields"], **provenance})
        there.add(f["subject"])
        added.append({**f, "entry_id": entry["id"]})
    return {"record": record, "added": added, "skipped": skipped}
