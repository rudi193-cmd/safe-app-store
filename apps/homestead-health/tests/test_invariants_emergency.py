"""H-3 — the emergency card is authored, not computed.

Promoted out of `test_invariants_pending.py` when `homestead_health.emergency`
landed — the last pending claim in the module to fall, leaving `UNBUILT` empty.
The `test_h3_…` body is kept as written; around it are the checks that make H-3
real rather than a name: the card exports **exactly** the operator's chosen
fields and nothing a caller slips into the data for a field the card did not name
(authored, not computed), while staying an export like any other — usefulness
does not lower the rung, and the ledger records the act, not the content.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep.export import ExportRefused
from homestead.keep.logs import VisibleLog
from homestead.keep.rungs import Classified, Purpose, Rung

from homestead_health.emergency import CARD_ITEM, Card, export_card


def _datum(value: object, rung: Rung = Rung.L4) -> Classified:
    """A synthetic health datum. L3/L4 carry a derived form; L5 needs none."""
    if rung in (Rung.L3, Rung.L4):
        return Classified(rung, value, derived="a health datum")
    return Classified(rung, value)


# ── H-3, promoted verbatim ───────────────────────────────────────────────────


def test_h3_the_card_holds_only_what_the_operator_chose():
    card = Card(fields=("allergies",))
    assert card.fields == ("allergies",)
    # A computed card is a query someone else effectively wrote. The class
    # must not offer the machinery: no auto-include, no relevance.
    assert not hasattr(Card, "auto_include")
    assert not hasattr(Card, "relevant_fields")


# ── the card is a closed, authored field set ─────────────────────────────────


def test_a_card_refuses_an_empty_or_malformed_field_set():
    with pytest.raises(ValueError):
        Card(fields=())
    with pytest.raises(ValueError):
        Card(fields=("allergies", "allergies"))   # a choice made twice
    with pytest.raises(ValueError):
        Card(fields=("allergies", ""))
    with pytest.raises(TypeError):
        Card(fields=["allergies"])                 # a mutable collection is a heuristic's shape


# ── authored, not computed — the export includes only the chosen fields ──────


def test_the_export_includes_only_the_cards_fields_ignoring_extras(tmp_path, monkeypatch):
    """The heart of H-3. The card names two fields; the caller hands data for a
    third (`diagnosis`). The export carries the two the operator chose and does not
    reach for the extra — a card assembled by what happens to be available is a
    query someone else wrote."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies", "blood_type"))
    data = {
        "allergies": _datum("penicillin"),
        "blood_type": _datum("O+"),
        "diagnosis": _datum("a condition the operator did not put on the card"),
    }
    receipt = export_card(card, "subj-01", data, purpose=Purpose.EXPORT)

    body = json.loads(receipt.artifact.read_text(encoding="utf-8"))
    fields = {row["field"] for row in body["content"]}
    assert fields == {"allergies", "blood_type"}, "the extra datum must not appear"
    assert "a condition" not in receipt.artifact.read_text(encoding="utf-8")


def test_a_chosen_field_with_no_datum_is_a_recorded_gap(tmp_path, monkeypatch):
    """I-8 at the card: a field the operator authored but has no datum for is drawn
    as a gap, not silently omitted. A blank allergy line on an emergency card is
    meaningful — 'none recorded' is not 'no known allergies' — so the absence is
    recorded, carrying no content."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies", "conditions"))
    receipt = export_card(card, "subj-01", {"allergies": _datum("penicillin")}, purpose=Purpose.EXPORT)

    body = json.loads(receipt.artifact.read_text(encoding="utf-8"))
    by_field = {row["field"]: row for row in body["content"]}
    assert by_field["allergies"]["recorded"] is True
    assert by_field["conditions"]["recorded"] is False
    assert by_field["conditions"]["value"] is None, "a gap carries no content"


def test_an_l5_field_is_indistinguishable_from_a_missing_one(tmp_path, monkeypatch):
    """The H-3 audit's finding, closed. An L5-sealed field and a genuinely-missing
    field draw the *same* gap row (recorded: false, no content), so a reader who
    knows the authored template cannot tell 'sealed' from 'never recorded' — the row
    presence itself would otherwise be the refusal signal I-13 forbids. The sealed
    field's content is, of course, absent."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies", "conditions", "ssn"))
    data = {"allergies": _datum("penicillin"), "ssn": _datum("123-45-6789", rung=Rung.L5)}
    receipt = export_card(card, "subj-01", data, purpose=Purpose.EXPORT)

    body = json.loads(receipt.artifact.read_text(encoding="utf-8"))
    by_field = {row["field"]: row for row in body["content"]}

    # Both are present, and identical in everything but their own field label — a
    # reader sees the same "recorded: false, no value" for the sealed field as for
    # the never-recorded one, and cannot tell which is which.
    def shape(row: dict) -> dict:
        return {k: v for k, v in row.items() if k != "field"}

    assert shape(by_field["ssn"]) == shape(by_field["conditions"]), (
        "a sealed field must be indistinguishable from a missing one"
    )
    assert by_field["ssn"] == {"field": "ssn", "value": None, "recorded": False}
    assert by_field["allergies"]["recorded"] is True
    assert "123-45-6789" not in receipt.artifact.read_text(encoding="utf-8")


def test_a_card_with_nothing_recordable_is_refused(tmp_path, monkeypatch):
    """A card of only gaps (or only L5 drops) has nothing that could cross — an
    export of nothing is not an export, refused before any log is written."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies", "conditions"))
    with pytest.raises(ExportRefused):
        export_card(card, "subj-01", {}, purpose=Purpose.EXPORT)          # all gaps
    with pytest.raises(ExportRefused):
        export_card(card, "subj-01", {"allergies": _datum("x", rung=Rung.L5)}, purpose=Purpose.EXPORT)
    assert not (tmp_path / "logs").exists(), "a refused card writes no log"


# ── it stays an export — the rung is not lowered, and the ledger holds the act ─


def test_usefulness_does_not_lower_the_rung(tmp_path, monkeypatch):
    """The wrong answer is lowering the rung so the card can leave; the right answer
    is an export. An L4 field crosses S4 only because a purpose is declared, and the
    card composes to L4 — the rung is not lowered, the ceremony is."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies",))
    receipt = export_card(card, "subj-01", {"allergies": _datum("penicillin")}, purpose=Purpose.EXPORT)
    assert receipt.rung is Rung.L4
    assert receipt.ref == "emergency/card/subj-01"

    # Without a purpose, an L4 datum may not cross S4 — the export refuses.
    with pytest.raises(ExportRefused):
        export_card(card, "subj-01", {"allergies": _datum("penicillin")}, purpose=None)


def test_both_logs_carry_references_and_no_card_content(tmp_path, monkeypatch):
    """I-15 at the card's egress: the content leaves in the artifact, the logs hold
    the act by reference and metadata only. The log entry's key set is the same
    closed set the school form's is — no field a card datum could ride into."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies", "blood_type"))
    data = {"allergies": _datum("penicillin"), "blood_type": _datum("O+")}
    export_card(card, "subj-01", data, purpose=Purpose.EXPORT)

    integrity_text = (tmp_path / "logs" / "integrity.jsonl").read_text(encoding="utf-8")
    for blob in (integrity_text, (tmp_path / "logs" / "visible.jsonl").read_text(encoding="utf-8")):
        assert "penicillin" not in blob and "O+" not in blob, "no card content in a log (I-15)"

    entry = json.loads(integrity_text)
    assert set(entry) == {
        "act", "at", "matter", "item_type", "item_id", "purpose", "rung",
        "disposition", "prev",
    }
    assert entry["item_type"] == CARD_ITEM and entry["item_id"] == "subj-01"

    visible = VisibleLog().read()
    assert len(visible) == 1 and visible[0]["event"] == "exported"
    assert visible[0]["ref"] == "emergency/card/subj-01"


def test_the_card_export_validates_the_subject_id(tmp_path, monkeypatch):
    """The card is an export, so it inherits the shared subject-id guard — a newline
    id (the audit's critical finding) is refused before anything is written, here as
    in the school form, because both call the one validator."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    card = Card(fields=("allergies",))
    with pytest.raises(ExportRefused):
        export_card(card, "subj-01\nFORGED", {"allergies": _datum("penicillin")}, purpose=Purpose.EXPORT)
    assert not (tmp_path / "logs").exists() and not (tmp_path / "exports").exists()
