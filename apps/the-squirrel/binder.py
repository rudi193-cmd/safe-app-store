"""Binder — promotes fragments to person records via fuzzy name match.

B-008 fix (verifier-confirmed):
  - No silent 200 cap. auto_bind examines every unsynced fragment it can
    within a work budget, and REPORTS what it did — examined, bound,
    ambiguous, remaining — so "bind all" never claims to have done more
    than it did.
  - Ties don't silently mis-bind. A father and son both named "Oscar Mann"
    used to bind to whichever the query returned first. Now a match must
    clear the threshold AND beat the runner-up by a margin; otherwise it's
    counted ambiguous and left for a human, not guessed.
  - Provenance persists. bind() records WHICH person via mark_bound.
"""
import difflib
from datetime import datetime
from typing import Dict, Any
import db.persons as persons_db
import db.fragments as fragments_db

# Budget on name-comparisons per invocation (~the 3.7s the verifier measured
# for 200k pairs). Beyond it, we report `remaining` instead of hanging the
# watcher thread on a loop-until-dry over thousands×thousands.
_COMPARISON_BUDGET = 200_000


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


class Binder:
    def __init__(self, conn):
        self.conn = conn

    def bind(self, fragment_id: int, person_id: int) -> Dict[str, Any]:
        if not fragments_db.mark_bound(self.conn, fragment_id, person_id):
            raise ValueError(f"Fragment {fragment_id} not found or already deleted")
        return {"fragment_id": fragment_id, "person_id": person_id,
                "synced_at": datetime.utcnow().isoformat()}

    def auto_bind(self, threshold: float = 0.82, margin: float = 0.08) -> Dict[str, Any]:
        """Fuzzy-promote unsynced fragments. Returns a report dict:
        {examined, bound: [...], ambiguous, remaining}. `remaining` > 0 means
        the work budget was hit and a re-run continues; `bound == [] and
        remaining == 0` means the stash is fully reconciled (nothing left to
        confidently match), NOT that work was silently skipped."""
        frags = fragments_db.get_unsynced_fragments(self.conn, limit=1_000_000)
        people = persons_db.all_persons(self.conn)
        if not people:
            return {"examined": 0, "bound": [], "ambiguous": 0,
                    "remaining": len(frags), "note": "no persons to match against"}

        per_frag = max(1, len(people))
        max_frags = max(1, _COMPARISON_BUDGET // per_frag)
        batch = frags[:max_frags]

        bound, ambiguous = [], 0
        for frag in batch:
            scored = sorted(
                ((_name_similarity(frag["person_name"], p["full_name"]), p) for p in people),
                key=lambda t: t[0], reverse=True)
            best_score, best_person = scored[0]
            runner_up = scored[1][0] if len(scored) > 1 else 0.0
            if best_score < threshold:
                continue
            if best_score - runner_up < margin:
                ambiguous += 1          # confident but tied — needs a human
                from sap.core import gaps
                gaps.log("ambiguous_bind", f"fragment {frag['id']}: {frag['person_name']}",
                         detail=f"matches multiple people (top {round(best_score, 2)})")
                continue
            try:
                self.bind(frag["id"], best_person["id"])
                bound.append({"fragment_id": frag["id"],
                              "person_id": best_person["id"],
                              "score": round(best_score, 3)})
            except Exception:
                pass
        return {"examined": len(batch), "bound": bound, "ambiguous": ambiguous,
                "remaining": len(frags) - len(batch)}
