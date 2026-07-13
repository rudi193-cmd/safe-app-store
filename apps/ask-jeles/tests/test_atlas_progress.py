"""Tests for the Ask Jeles -> Catalog completion bridge."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from askjeles import atlas_progress as ap

COURSES = [
    {"id": "intro-philosophy", "title": "Introduction to Philosophy", "field": "philosophy",
     "topics": ["Arguments & fallacies", "Free will"], "requires": []},
    {"id": "logic", "title": "Formal Logic", "field": "philosophy",
     "topics": ["Propositional logic", "Predicate logic"], "requires": ["intro-philosophy"]},
    {"id": "quantum-mechanics", "title": "Quantum Mechanics", "field": "physics",
     "topics": ["Schrodinger equation", "Wavefunctions"], "requires": ["classical-mechanics"]},
    {"id": "classical-mechanics", "title": "Classical Mechanics", "field": "physics",
     "topics": ["Newton's laws"], "requires": []},
    {"id": "cooking", "title": "Cooking", "field": "life",
     "topics": ["Knife skills"], "requires": []},
]


def test_full_title_phrase_matches():
    ids = ap.match_courses("A gentle introduction to philosophy and free will", COURSES)
    assert "intro-philosophy" in ids


def test_all_significant_title_tokens_match_multiword():
    # "quantum" + "mechanics" both present -> match; "quantum" alone would not.
    assert "quantum-mechanics" in ap.match_courses("notes on quantum wave mechanics", COURSES)
    assert "quantum-mechanics" not in ap.match_courses("a quantum leap in sales", COURSES)


def test_topic_only_mention_does_not_complete():
    # Conservative by design: mentioning a shared topic ("schrodinger equation")
    # without naming the subject must NOT complete the course.
    ids = ap.match_courses("derived the schrodinger equation today", COURSES)
    assert "quantum-mechanics" not in ids


def test_generic_query_does_not_overmatch():
    # Short/stopword-ish text should not paint the atlas gold.
    assert ap.match_courses("intro to science", COURSES) == set()


def test_prereq_closure_pulls_the_chain():
    by_id = {c["id"]: c for c in COURSES}
    closed = ap.prereq_closure({"quantum-mechanics"}, by_id)
    assert closed == {"quantum-mechanics", "classical-mechanics"}


def test_build_progress_end_to_end():
    events = [
        {"query": "introduction to philosophy", "query_class": "research"},
        {"query": "quantum mechanics wavefunctions", "pedagogy": {"topic": "physics"}},
    ]
    milestones = {"questions_asked": 13, "seed_planted": True}
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)

    payload = ap.build_progress(events, COURSES, milestones, now=now)

    completed = set(payload["completed_course_ids"])
    # direct hits + prereq closure
    assert {"intro-philosophy", "quantum-mechanics", "classical-mechanics"} <= completed
    assert "cooking" not in completed
    assert payload["stats"]["events_scanned"] == 2
    assert payload["stats"]["questions_asked"] == 13
    assert payload["stats"]["seed_planted"] is True
    assert payload["schema"] == ap.SCHEMA
    # Serializable.
    json.dumps(payload)


def test_courses_json_is_present_and_well_formed():
    courses = ap.load_courses()
    assert len(courses) > 100
    ids = {c["id"] for c in courses}
    # Every prerequisite references a real course.
    for c in courses:
        for req in c.get("requires", []):
            assert req in ids, f"{c['id']} requires missing {req}"
