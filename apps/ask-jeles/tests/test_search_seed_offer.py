"""synthesize_answer() attaches seed_offer on exactly the 13th call.

Uses the corpus fast-path (an exact nugget match) so this stays a fast,
network-free unit test regardless of which branch actually answers the
question — the milestone wrapper runs after every branch, not just this
one; see search.py::synthesize_answer.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA", str(tmp_path / "app_data"))
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    from askjeles import corpus, search

    corpus.put_nugget(
        question="What is the primary color in Grove?",
        answer="White.",
        sources=["safe-library/themes/grove.json"],
        verified_by="designer",
    )
    return search


def test_seed_offer_absent_before_13th_question(seeded):
    for _ in range(12):
        result = seeded.synthesize_answer("What is the primary color in Grove?")
        assert "seed_offer" not in result


def test_seed_offer_present_on_13th_question(seeded):
    for _ in range(12):
        seeded.synthesize_answer("What is the primary color in Grove?")
    result = seeded.synthesize_answer("What is the primary color in Grove?")
    assert result["seed_offer"]


def test_seed_offer_absent_again_on_14th_question(seeded):
    for _ in range(13):
        seeded.synthesize_answer("What is the primary color in Grove?")
    result = seeded.synthesize_answer("What is the primary color in Grove?")
    assert "seed_offer" not in result
