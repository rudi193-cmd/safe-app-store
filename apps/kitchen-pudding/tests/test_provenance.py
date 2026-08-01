from __future__ import annotations

import pytest

from kitchen_pudding.provenance import Provenance, aggregate


def test_ordering_is_weakest_to_strongest():
    assert Provenance.ASSUMED < Provenance.FITTED < Provenance.MEASURED


def test_aggregate_is_the_weakest_ingredient_not_an_average():
    result = aggregate([Provenance.MEASURED, Provenance.MEASURED, Provenance.ASSUMED])
    assert result is Provenance.ASSUMED


def test_aggregate_all_measured_is_measured():
    assert aggregate([Provenance.MEASURED, Provenance.MEASURED]) is Provenance.MEASURED


def test_aggregate_single_assumed_ingredient_drags_down_a_large_recipe():
    # A gate that cannot fail is not a gate: this is the one behavior that
    # distinguishes min() from a mean, an "any measured" check, or a majority
    # vote — all of which would pass this recipe as reliable.
    mostly_measured = [Provenance.MEASURED] * 9 + [Provenance.ASSUMED]
    assert aggregate(mostly_measured) is Provenance.ASSUMED


def test_aggregate_rejects_empty_recipe():
    with pytest.raises(ValueError):
        aggregate([])


def test_parse_accepts_case_insensitive_names():
    assert Provenance.parse("Measured") is Provenance.MEASURED
    assert Provenance.parse("fitted") is Provenance.FITTED
    assert Provenance.parse("ASSUMED") is Provenance.ASSUMED


def test_parse_rejects_unknown_value():
    with pytest.raises(ValueError):
        Provenance.parse("guessed")


def test_str_is_lowercase_name():
    assert str(Provenance.MEASURED) == "measured"
