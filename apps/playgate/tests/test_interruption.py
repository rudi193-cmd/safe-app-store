"""The interruption record: what it refuses, and when it demotes itself."""
from __future__ import annotations

import pytest

from playgate.interruption import (
    Interruption,
    InterruptionError,
    weakest,
)


# -- absence is a value, not a gap ----------------------------------------

def test_a_missing_record_is_an_error_not_an_assumed_one():
    """The single most important behaviour in this module.

    Defaulting a missing field to `assumed` would make "nobody wrote a record"
    and "somebody recorded that nobody has looked" the same value. Only one of
    those is a fact, and a catalog that cannot tell them apart is lying by
    omission from its first commit.
    """
    with pytest.raises(InterruptionError, match="no interruption record"):
        Interruption.from_json(None)


def test_an_explicit_assumed_record_is_accepted():
    record = Interruption.from_json({"provenance": "assumed"})
    assert record.provenance == "assumed"
    assert record.count_per_10min is None


def test_assumed_may_not_carry_a_count():
    """A count with no observation behind it is a guess in an observation's
    clothes; there is nowhere for the number to have come from."""
    with pytest.raises(InterruptionError, match="assumed record carries a count"):
        Interruption(provenance="assumed", count_per_10min=0)


def test_an_unknown_provenance_is_refused():
    with pytest.raises(InterruptionError, match="not one of"):
        Interruption(provenance="probably fine")


def test_unknown_fields_are_refused():
    with pytest.raises(InterruptionError, match="unknown interruption fields"):
        Interruption.from_json({"provenance": "assumed", "score": 4})


# -- the stronger states have to earn it ----------------------------------

def test_measured_without_a_count_is_refused():
    with pytest.raises(InterruptionError, match="carries no count"):
        Interruption(provenance="measured", observed_version="1.0",
                     observed_at="2026-08-02", observed_by="a parent")


def test_measured_must_be_bound_to_a_build_and_a_date():
    with pytest.raises(InterruptionError, match="missing"):
        Interruption(provenance="measured", count_per_10min=6)


def test_fitted_must_state_its_rule():
    """`fitted` means derived by a stated rule. An unstated rule is not a rule
    and the number behind it is unauditable."""
    with pytest.raises(InterruptionError, match="must state the rule"):
        Interruption(provenance="fitted", count_per_10min=3)


def test_a_negative_count_is_refused():
    with pytest.raises(InterruptionError, match="negative"):
        Interruption(provenance="fitted", count_per_10min=-1, note="rule")


def test_a_deceptive_close_is_its_own_dismissal_kind():
    """Not a worse `unskippable` — a different mechanism, in which escaping the
    interruption is itself monetised."""
    record = Interruption(
        provenance="measured", count_per_10min=12, dismissal="deceptive_close",
        observed_version="3.1", observed_at="2026-08-02", observed_by="a parent",
    )
    assert record.dismissal == "deceptive_close"


def test_an_unrecognised_dismissal_is_refused():
    with pytest.raises(InterruptionError, match="dismissal"):
        Interruption(provenance="assumed", dismissal="mostly fine")


# -- decay -----------------------------------------------------------------

MEASURED = Interruption(
    provenance="measured", count_per_10min=6, dismissal="after_delay",
    observed_version="3.1", observed_at="2026-08-02", observed_by="a parent",
)


def test_a_measurement_survives_its_own_build():
    assert MEASURED.effective("3.1").provenance == "measured"


def test_a_measurement_demotes_when_the_build_moves_under_it():
    """Ad load is a tuning parameter. A count observed on 3.1 says nothing about
    3.2, and a record that kept claiming `measured` would carry the authority of
    having been checked while describing a build that no longer exists."""
    demoted = MEASURED.effective("3.2")
    assert demoted.provenance == "fitted"
    assert "3.1" in demoted.note and "3.2" in demoted.note


def test_demotion_keeps_the_count_as_evidence_about_the_publisher():
    """It falls to `fitted`, not to `assumed`: the old number is still evidence
    about how these people behave, which is what fitted means."""
    assert MEASURED.effective("3.2").count_per_10min == 6


def test_demotion_does_not_mutate_the_original():
    MEASURED.effective("9.9")
    assert MEASURED.provenance == "measured"


def test_an_unknown_installed_version_does_not_demote():
    """Nothing is known to have changed. Demoting here would punish a missing
    version field rather than an actual drift."""
    assert MEASURED.effective(None).provenance == "measured"


def test_assumed_and_fitted_do_not_demote_further():
    fitted = Interruption(provenance="fitted", count_per_10min=2, note="rule")
    assert fitted.effective("anything").provenance == "fitted"
    assert Interruption(provenance="assumed").effective("anything").provenance == "assumed"


# -- combination -----------------------------------------------------------

def test_a_view_is_worth_its_weakest_input():
    assert weakest("measured", "assumed") == "assumed"
    assert weakest("measured", "fitted") == "fitted"
    assert weakest("measured", "measured") == "measured"


def test_weakest_is_not_an_average():
    """Averaging is the operation by which a strong input hides a weak one.
    Three measured facts and one assumed fact is an assumed view, not 75%."""
    assert weakest("measured", "measured", "measured", "assumed") == "assumed"


def test_weakest_refuses_an_unrecognised_state():
    with pytest.raises(InterruptionError, match="not recognised"):
        weakest("measured", "probably fine")
