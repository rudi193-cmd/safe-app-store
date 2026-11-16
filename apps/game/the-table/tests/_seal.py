"""_seal.py -- a stand-in for the human's answer over a beat (flatten F3).

``StorySession.seal`` moves only on an answer from the one-script's
``table.beat_seal`` (a proof that re-checks, read through a box). Unit tests
that only need the story to move on hand it this stand-in instead: it answers
for the beat pending NOW, as the one-script would for a seal the human made.
The real thing -- a box, a proposal, a throwaway human key made in the test,
the one-script's own check -- is ``test_story_session.py``'s
``TestStorySessionSealOnTheRecord``.
"""
from __future__ import annotations

from the_table.seal import beat_path

SUBJECT = "proposal:" + "ab" * 32


def answer_for(session, state: str = "sealed", by: str = "human") -> dict:
    """The answer ``table.beat_seal`` gives for a seal over the pending beat."""
    p = session.pending_seal()
    return {"state": state, "by": by, "seal": 1, "fact_id": p["fact_id"], "data": p["fact"],
            "path": beat_path({**p, "world": session.world.get("id")})}


def human_seal(session, state: str = "sealed", by: str = "human") -> dict:
    """Seal (or, ``state="rejected"``, reject) the pending beat with the stand-in."""
    got = answer_for(session, state, by)
    return session.seal(got["fact_id"], SUBJECT, check=lambda _subject: got)
