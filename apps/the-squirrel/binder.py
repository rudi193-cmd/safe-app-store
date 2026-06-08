"""Binder — promotes fragments to person records via fuzzy name match."""
import difflib
from datetime import datetime
from typing import List, Dict, Any
import db.persons as persons_db
import db.fragments as fragments_db


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


class Binder:
    def __init__(self, conn):
        self.conn = conn

    def bind(self, fragment_id: int, person_id: int) -> Dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE the_squirrel.fragments
            SET binder_synced_at = %s
            WHERE id = %s AND is_deleted = 0
        """, (datetime.utcnow(), fragment_id))
        if cur.rowcount == 0:
            self.conn.rollback()
            raise ValueError(f"Fragment {fragment_id} not found or already deleted")
        self.conn.commit()
        return {"fragment_id": fragment_id, "person_id": person_id,
                "synced_at": datetime.utcnow().isoformat()}

    def auto_bind(self, threshold: float = 0.8) -> List[Dict[str, Any]]:
        frags = fragments_db.get_unsynced_fragments(self.conn, limit=200)
        people = persons_db.search_persons(self.conn, "")
        bound = []
        for frag in frags:
            best_score, best_person = 0.0, None
            for person in people:
                score = _name_similarity(frag["person_name"], person["full_name"])
                if score > best_score:
                    best_score, best_person = score, person
            if best_person and best_score >= threshold:
                try:
                    self.bind(frag["id"], best_person["id"])
                    bound.append({"fragment_id": frag["id"],
                                  "person_id": best_person["id"],
                                  "score": round(best_score, 3)})
                except Exception:
                    pass
        return bound
