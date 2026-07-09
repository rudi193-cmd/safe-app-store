"""Verified-nugget corpus: storage, ranked ask/search, gap logging."""

from __future__ import annotations

import pytest


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    # _conn() keys its connection cache by the full resolved db path, so a
    # fresh WILLOW_STORE_ROOT per test is enough isolation without reload.
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    from askjeles import corpus as corpus_module

    return corpus_module


def _seed_grove(corpus):
    return corpus.put_nugget(
        question="What's the primary color in Grove?",
        answer="The primary color in Grove is #ffffff (white).",
        sources=["safe-library/themes/grove.json"],
        verified_by="designer",
        tags=["color", "grove", "primary"],
    )


def test_put_requires_core_fields(corpus):
    assert "error" in corpus.put_nugget("", "", [], "")
    assert "error" in corpus.put_nugget("Q?", "A.", [], "")


def test_put_and_get_roundtrip(corpus):
    result = _seed_grove(corpus)
    assert "id" in result
    nugget = corpus.get_nugget(result["id"])
    assert nugget["question"] == "What's the primary color in Grove?"
    assert nugget["verified_by"] == "designer"
    assert nugget["status"] == "verified"


def test_get_missing_returns_error(corpus):
    assert corpus.get_nugget("does-not-exist") == {"error": "not_found"}


def test_search_ranks_question_match_first(corpus):
    _seed_grove(corpus)
    corpus.put_nugget(
        question="What's the accent color in Nord?",
        answer="The accent color in Nord is #88c0d0 (ice blue).",
        sources=["safe-library/themes/nord.json"],
        verified_by="designer",
    )
    hits = corpus.search_nuggets("primary color Grove")
    assert hits
    assert hits[0]["question"].startswith("What's the primary color")


def test_weak_overlap_is_not_a_confident_ask(corpus):
    # "color" overlaps with the Grove nugget, so search_nuggets() (a loose
    # ranked lookup) may legitimately surface it — but that weak overlap
    # must not be enough for ask_corpus() to call it a confident answer.
    _seed_grove(corpus)
    asked = corpus.ask_corpus("What is the accent color in Tokyo Night?")
    assert asked["found"] is False


def test_ask_corpus_exact_match(corpus):
    _seed_grove(corpus)
    result = corpus.ask_corpus("What's the primary color in Grove?")
    assert result["found"] is True
    assert result["exact"] is True
    assert "white" in result["nugget"]["answer"].lower()


def test_ask_corpus_miss_logs_gap(corpus):
    result = corpus.ask_corpus("What is the accent color in Tokyo Night?")
    assert result["found"] is False
    gaps = corpus.list_gaps()
    assert len(gaps) == 1
    assert gaps[0]["question"] == "What is the accent color in Tokyo Night?"
    assert gaps[0]["asked_count"] == 1


def test_ask_corpus_repeated_miss_bumps_count_not_duplicates(corpus):
    corpus.ask_corpus("What is the accent color in Tokyo Night?")
    corpus.ask_corpus("what is the accent color in tokyo night")
    gaps = corpus.list_gaps()
    assert len(gaps) == 1
    assert gaps[0]["asked_count"] == 2


def test_search_nuggets_never_logs_a_gap(corpus):
    corpus.search_nuggets("some unmatched query")
    assert corpus.list_gaps() == []


def test_to_search_hit_shape(corpus):
    _seed_grove(corpus)
    nugget = corpus.list_nuggets()[0]
    hit = corpus.to_search_hit(nugget, 1)
    assert hit["source_id"] == "corpus"
    assert hit["confidence"] == "verified"
    assert hit["title"] == nugget["question"]
    assert hit["snippet"] == nugget["answer"]
    assert hit["url"] == "safe-library/themes/grove.json"


def test_list_nuggets_most_recent_first(corpus):
    first = _seed_grove(corpus)
    second = corpus.put_nugget(
        question="What's the accent color in Nord?",
        answer="The accent color in Nord is #88c0d0 (ice blue).",
        sources=["safe-library/themes/nord.json"],
        verified_by="designer",
    )
    nuggets = corpus.list_nuggets()
    assert nuggets[0]["_id"] == second["id"]
    assert nuggets[1]["_id"] == first["id"]
