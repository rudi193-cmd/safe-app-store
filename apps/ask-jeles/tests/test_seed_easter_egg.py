"""The corpus's first nugget: idempotent, findable, and correct."""

from __future__ import annotations

import pytest


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    from askjeles import corpus as corpus_module

    return corpus_module


def _seed(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    from askjeles import seed_easter_egg

    return seed_easter_egg


def test_seed_creates_nugget_42(monkeypatch, tmp_path, corpus):
    seed_easter_egg = _seed(monkeypatch, tmp_path)
    result = seed_easter_egg.seed()
    assert result["id"] == "42"
    nugget = corpus.get_nugget("42")
    assert "42" in nugget["answer"]
    assert nugget["verified_by"] == "jeles"
    assert "easter-egg" in nugget["tags"]


def test_seed_is_idempotent(monkeypatch, tmp_path, corpus):
    seed_easter_egg = _seed(monkeypatch, tmp_path)
    first = seed_easter_egg.seed()
    second = seed_easter_egg.seed()
    assert first["id"] == second["id"] == "42"
    assert len(corpus.list_nuggets()) == 1


def test_ask_corpus_answers_the_ultimate_question(monkeypatch, tmp_path, corpus):
    seed_easter_egg = _seed(monkeypatch, tmp_path)
    seed_easter_egg.seed()
    result = corpus.ask_corpus("What is the answer to life, the universe, and everything?")
    assert result["found"] is True
    assert result["exact"] is True
    assert result["nugget"]["answer"].startswith("42")
