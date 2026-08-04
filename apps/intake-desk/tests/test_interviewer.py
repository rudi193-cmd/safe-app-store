"""The interviewer is injected, and three rules are not the profile's to waive."""
from __future__ import annotations

import pytest

import consent as consent_mod
import interviewer

NARRATOR = "slappy"


def test_riggs_loads_as_the_reference_profile():
    riggs = interviewer.load("riggs")
    assert riggs.name == "Riggs"
    assert any("Names Given Not Chosen" in p for p in riggs.principles)
    assert "riggs" in interviewer.available()


def test_an_unknown_profile_is_refused():
    with pytest.raises(interviewer.InterviewerError, match="no interviewer profile"):
        interviewer.load("nobody")


def test_a_profile_without_principles_or_refusals_is_refused(tmp_path):
    (tmp_path / "thin.toml").write_text('name = "Thin"\nvoice = "flat"\n')
    with pytest.raises(interviewer.InterviewerError, match="principles"):
        interviewer.load("thin", profile_dir=tmp_path)


def test_the_brief_carries_principles_and_refusals():
    brief = interviewer.load("riggs").brief()
    assert "Corrections Not Erasure" in brief
    assert "Never correct the narrator mid-session" in brief
    assert "YOU DO NOT:" in brief


def test_a_session_cannot_open_without_a_recorded_grant(tmp_path):
    """Session rule 1: the scope is read aloud and the record exists first."""
    store = tmp_path / "consent"
    with pytest.raises(interviewer.InterviewerError, match="read the scope aloud"):
        interviewer.open_session(
            consent_store=store, narrator_id=NARRATOR,
            interviewer=interviewer.load("riggs"),
        )


def test_the_refusal_shows_the_operator_what_to_say(tmp_path):
    store = tmp_path / "consent"
    with pytest.raises(interviewer.InterviewerError) as exc:
        interviewer.open_session(
            consent_store=store, narrator_id=NARRATOR,
            interviewer=interviewer.load("riggs"),
        )
    assert "You can change your mind at any time" in str(exc.value)


def test_a_session_opens_with_an_opener_once_consent_is_recorded(tmp_path):
    store = tmp_path / "consent"
    consent_mod.grant_keeping(store, NARRATOR, granted_by="operator")
    opener = interviewer.open_session(
        consent_store=store, narrator_id=NARRATOR,
        interviewer=interviewer.load("riggs"),
    )
    assert opener == "What's the story behind this one?"


def test_the_domain_travels_with_the_profile_not_the_desk(tmp_path):
    """Ship the mold and the reader; the wood stays with whoever grew it."""
    (tmp_path / "clerk.toml").write_text(
        'name = "Clerk"\n'
        'full_name = "The Clerk"\n'
        'domain = "municipal records"\n'
        'voice = "Flat. Exact."\n'
        'principles = ["Read the file number back."]\n'
        'refusals = ["Never speculate about intent."]\n'
        'openers = ["What is the file number?"]\n'
    )
    clerk = interviewer.load("clerk", profile_dir=tmp_path)
    assert clerk.domain == "municipal records"
    assert "Never speculate about intent." in clerk.brief()
    assert "Names Given Not Chosen" not in clerk.brief()
