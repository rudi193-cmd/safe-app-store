"""Consent at intake, and the egress gate.

Spec §9. A README saying "the wood stays with whoever grew it" enforces
nothing; these are the tests that make it a property of the code.
"""
from __future__ import annotations

import json

import pytest

import consent as consent_mod
import desk
import desk_db
import export

NARRATOR = "slappy"
OTHER = "the-colonel"
TAKER = "penny"
WITNESS = "wrench"
BODY = "We pushed it four miles to the campground. Somebody always stops."


def _ready_claim(conn, store, narrator=NARRATOR):
    sid = desk.file_statement(
        conn, consent_store=store, session_id="s1", narrator_id=narrator,
        taker_id=TAKER, body=BODY,
    )
    cid = desk.add_claim(conn, statement_id=sid, span=(0, 41),
                         assertion="They pushed the bike four miles.")
    desk.rule(conn, claim_id=cid, ruled_by=WITNESS, confidence="high")
    desk.publish(conn, claim_id=cid)
    return cid


@pytest.fixture()
def vault(tmp_path):
    store = tmp_path / "consent"
    consent_mod.grant_keeping(store, NARRATOR, granted_by="operator")
    conn = desk_db.connect(tmp_path / "desk.sqlite3")
    return conn, store, tmp_path


# ── intake ────────────────────────────────────────────────────────────────────

def test_filing_without_consent_is_refused(vault):
    conn, store, _ = vault
    with pytest.raises(desk.DeskError, match="absence is not consent"):
        desk.file_statement(
            conn, consent_store=store, session_id="s1", narrator_id="a-stranger",
            taker_id=TAKER, body=BODY,
        )


def test_filing_records_a_disclosure(vault):
    conn, store, _ = vault
    desk.file_statement(conn, consent_store=store, session_id="s1",
                        narrator_id=NARRATOR, taker_id=TAKER, body=BODY)
    from subject_consent import read_disclosures
    actions = [d["action"] for d in read_disclosures(store, NARRATOR)]
    assert "statement_filed" in actions


# ── egress ────────────────────────────────────────────────────────────────────

def test_keeping_consent_does_not_imply_publication(vault):
    """The whole reason testimony_publication is its own scope."""
    conn, store, _ = vault
    _ready_claim(conn, store)
    with pytest.raises(export.ExportRefused, match="no verified publication grant"):
        export.gather(conn, consent_store=store)


def test_export_succeeds_once_publication_is_granted(vault):
    conn, store, _ = vault
    _ready_claim(conn, store)
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    records = export.gather(conn, consent_store=store)
    assert len(records) == 1
    assert records[0]["consent"]["scope"] == "testimony_publication"
    assert records[0]["quoted"] == BODY[0:41]


def test_one_missing_grant_refuses_the_whole_export(vault, tmp_path):
    """Bulk export fails closed. There is no 'most of it'."""
    conn, store, _ = vault
    consent_mod.grant_keeping(store, OTHER, granted_by="operator")
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    _ready_claim(conn, store, narrator=NARRATOR)
    _ready_claim(conn, store, narrator=OTHER)  # keeping only, no publication

    dest = tmp_path / "out.json"
    with pytest.raises(export.ExportRefused) as exc:
        export.to_json(conn, consent_store=store, path=dest)
    assert "1 narrator(s)" in str(exc.value)
    assert not dest.exists(), "a refused export must write nothing"


def test_the_refusal_names_a_count_never_the_narrator(vault):
    conn, store, _ = vault
    _ready_claim(conn, store)
    with pytest.raises(export.ExportRefused) as exc:
        export.gather(conn, consent_store=store)
    assert NARRATOR not in str(exc.value), "naming who withheld is itself a disclosure"


def test_revocation_stops_the_export_at_egress(vault):
    """Checked here, not at ruling time — a grant can be withdrawn in between."""
    conn, store, _ = vault
    _ready_claim(conn, store)
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    assert export.gather(conn, consent_store=store)

    consent_mod.revoke_all(store, NARRATOR, revoked_by="narrator")
    with pytest.raises(export.ExportRefused):
        export.gather(conn, consent_store=store)


def test_withheld_claims_never_export(vault):
    conn, store, _ = vault
    cid = _ready_claim(conn, store)
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    desk.withhold(conn, claim_id=cid, reason="narrator asked")
    with pytest.raises(export.ExportRefused, match="nothing is published"):
        export.gather(conn, consent_store=store)


def test_withhold_narrator_covers_everything_they_gave(vault):
    conn, store, _ = vault
    _ready_claim(conn, store)
    _ready_claim(conn, store)
    n = desk.withhold_narrator(conn, narrator_id=NARRATOR, reason="revoked")
    assert n == 2
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM claims WHERE state='published'").fetchone()["n"]
    assert remaining == 0


def test_export_appends_to_the_disclosure_chain(vault):
    conn, store, _ = vault
    _ready_claim(conn, store)
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    export.gather(conn, consent_store=store)
    from subject_consent import read_disclosures
    assert "exported" in [d["action"] for d in read_disclosures(store, NARRATOR)]


def test_markdown_keeps_the_citation(vault, tmp_path):
    conn, store, _ = vault
    _ready_claim(conn, store)
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    dest = export.to_markdown(conn, consent_store=store, path=tmp_path / "out.md")
    text = dest.read_text()
    assert NARRATOR in text
    assert BODY[0:41] in text, "the verbatim quote travels with the claim"
    assert "witnessed by" in text


def test_json_export_carries_scope_and_provenance(vault, tmp_path):
    conn, store, _ = vault
    _ready_claim(conn, store)
    consent_mod.grant_publication(store, NARRATOR, granted_by="operator")
    dest = export.to_json(conn, consent_store=store, path=tmp_path / "out.json")
    rec = json.loads(dest.read_text())[0]
    assert rec["consent"]["scope"] == "testimony_publication"
    assert rec["ruled_by"] == WITNESS and rec["narrator"] == NARRATOR
