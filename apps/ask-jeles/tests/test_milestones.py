"""The 13th-question seed milestone: fires exactly once, ever, and the
plant itself is idempotent."""

from __future__ import annotations

import pytest


@pytest.fixture()
def milestones(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA", str(tmp_path / "app_data"))
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    from askjeles import milestones as milestones_module

    return milestones_module


def test_no_offer_before_the_13th_question(milestones):
    for _ in range(12):
        assert milestones.record_question_and_maybe_offer_seed() is None


def test_offer_fires_exactly_on_the_13th_question(milestones):
    for _ in range(12):
        milestones.record_question_and_maybe_offer_seed()
    offer = milestones.record_question_and_maybe_offer_seed()
    assert offer == milestones.SEED_OFFER_MESSAGE


def test_offer_never_fires_again_after_the_13th(milestones):
    for _ in range(13):
        milestones.record_question_and_maybe_offer_seed()
    for _ in range(50):
        assert milestones.record_question_and_maybe_offer_seed() is None


def test_counter_persists_across_module_reimport(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA", str(tmp_path / "app_data"))
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path / "store"))
    from askjeles import milestones as first

    for _ in range(10):
        first.record_question_and_maybe_offer_seed()

    import importlib

    from askjeles import milestones as second

    importlib.reload(second)
    for _ in range(2):
        assert second.record_question_and_maybe_offer_seed() is None
    assert second.record_question_and_maybe_offer_seed() == second.SEED_OFFER_MESSAGE


def test_plant_seed_writes_a_nugget_from_the_pool(milestones):
    from askjeles import corpus

    result = milestones.plant_seed()
    assert "id" in result
    nugget = corpus.get_nugget(result["id"])
    assert nugget["verified_by"] == "jeles"
    assert "seed" in nugget["tags"]
    assert nugget["question"] in {choice["question"] for choice in milestones._SEED_POOL}


def test_plant_seed_is_idempotent(milestones):
    from askjeles import corpus

    first = milestones.plant_seed()
    second = milestones.plant_seed()
    assert first["id"] == second["id"]
    assert second.get("already_planted") is True
    assert len(corpus.list_nuggets()) == 1


def test_declining_never_writes_a_nugget(milestones):
    from askjeles import corpus

    for _ in range(13):
        milestones.record_question_and_maybe_offer_seed()
    # Declining in the TUI just means plant_seed() is never called — nothing
    # to assert on milestones itself beyond: the corpus stays untouched.
    assert corpus.list_nuggets() == []
