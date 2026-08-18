"""Bite 5 — the school form, health's first purposed egress.

Promoted out of `test_invariants_pending.py` when `homestead_health.school_form`
landed, the records track's capstone and the module's fourth promotion. The
pending file only asserted `export_history` was callable — the least a claim can
say; here it is widened to the bite's real *done when*
(`homestead/docs/PLAN-homestead-health.md` § bite 5):

* the export file exists and reads correctly;
* both log entries carry references and no content (I-15);
* `verify(expected_head=…)` catches a hand-edited entry.

An export is *"explicit act + purpose + ledgered"*, and the mechanism is the
engine's (`keep/export`) — this module composes a subject's several doses into
one form so the school gets one artifact and the ledger one entry. The content
leaves in the artifact and nowhere near a log; the head anchor is held off the
log's own tree, and the receipt returns the head to record off the machine.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep.export import ExportRefused, ledger
from homestead.keep.logs import VisibleLog
from homestead.keep.rungs import Classified, Purpose, Rung

from homestead_health.school_form import export_history


def _dose(vaccine: str, dose_date: str, subject: str = "subj-01") -> Classified:
    """A synthetic immunization dose — the composed record, at its hottest rung.

    An immunization record composes to L4 (the vaccine is a medical act on a
    person), so a dose is an L4 `Classified` carrying a derived form. The subject
    rides as the opaque id, never a name."""
    return Classified(
        Rung.L4,
        {"vaccine": vaccine, "dose_date": dose_date, "subject": subject},
        derived=f"a {vaccine} dose",
    )


# ── bite 5, promoted and widened ─────────────────────────────────────────────


def test_bite5_the_export_exists_and_is_purposed():
    from homestead_health.school_form import export_history as fn

    assert callable(fn)


def test_the_artifact_exists_and_reads(tmp_path, monkeypatch):
    """The record leaves in the artifact, and reads back as what crossed. On S4
    with a purpose declared, an L4 history renders, so the school form carries the
    doses the operator meant it to."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    doses = [_dose("MMR", "2026-08-15"), _dose("DTaP", "2026-05-01")]
    receipt = export_history("subj-01", doses, purpose=Purpose.EXPORT)

    assert receipt.artifact.exists(), "the export writes the artifact"
    body = json.loads(receipt.artifact.read_text(encoding="utf-8"))
    assert body["ref"] == "immunizations/history/subj-01"
    # The content is the two doses that crossed the gate — the form reads correctly.
    vaccines = {row["vaccine"] for row in body["content"]}
    assert vaccines == {"MMR", "DTaP"}


def test_both_logs_carry_references_and_no_content(tmp_path, monkeypatch):
    """I-15 at the egress. The integrity ledger and the visible log each get one
    entry, and neither carries a vaccine, a date, or any datum — only the
    reference, the purpose, the rung, and the disposition. The content is in the
    artifact; the logs prove the act without holding its matter."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    export_history("subj-01", [_dose("MMR", "2026-08-15")], purpose=Purpose.EXPORT)

    integrity_text = (tmp_path / "logs" / "integrity.jsonl").read_text(encoding="utf-8")
    visible_text = (tmp_path / "logs" / "visible.jsonl").read_text(encoding="utf-8")

    for blob in (integrity_text, visible_text):
        assert "MMR" not in blob, "a log must not carry the vaccine (I-15)"
        assert "2026-08-15" not in blob, "a log must not carry the dose date (I-15)"
    # It carries exactly one act, by reference and purpose.
    assert integrity_text.strip().count("\n") == 0, "exactly one integrity entry"
    entry = json.loads(integrity_text)
    assert entry["item_id"] == "subj-01" and entry["purpose"] == "export"
    assert entry["rung"] == "L4" and entry["disposition"] == "render"

    # Structural, not coincidental (the grep above only knows the two literals it
    # was told): the entry's key set is a fixed, closed set of references and
    # metadata — there is no field a future dose datum could ride into. A new field
    # of any kind fails this.
    assert set(entry) == {
        "act", "at", "matter", "item_type", "item_id", "purpose", "rung",
        "disposition", "prev",
    }

    visible = VisibleLog().read()
    assert len(visible) == 1 and visible[0]["event"] == "exported"
    assert visible[0]["ref"] == "immunizations/history/subj-01"
    assert set(visible[0]) == {"at", "event", "ref"}, (
        "the visible log carries only a timestamp, the closed event, and a reference"
    )


def test_verify_catches_a_hand_edited_entry(tmp_path, monkeypatch):
    """The bite's third *done when*. The head the receipt returns is what the
    operator records off the machine; against it, a hand-edited ledger entry does
    not verify. This is the only closure that means anything against someone who
    can also edit the on-disk anchor (the module docstring's own limit)."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    receipt = export_history("subj-01", [_dose("MMR", "2026-08-15")], purpose=Purpose.EXPORT)
    head = receipt.head

    # Fresh out of the export, the recorded head verifies.
    assert ledger().verify(expected_head=head) is True

    # Hand-edit one entry — flip the ledgered purpose — and re-verify against the
    # head recorded before the edit. The chain no longer hashes to it.
    log_file = tmp_path / "logs" / "integrity.jsonl"
    tampered = log_file.read_text(encoding="utf-8").replace(
        '"purpose":"export"', '"purpose":"filing"'
    )
    assert tampered != log_file.read_text(encoding="utf-8"), "the edit must actually change the file"
    log_file.write_text(tampered, encoding="utf-8")

    assert ledger().verify(expected_head=head) is False, (
        "a hand-edited entry must not verify against the off-machine head"
    )


def test_an_empty_history_is_refused(tmp_path, monkeypatch):
    """An export of nothing is not an export, and is refused before either log is
    written — the same fail-before-ledger posture keep/export takes for an
    undeclared purpose or an L5 datum. Nothing is left behind as an export of
    nothing."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    with pytest.raises(ExportRefused):
        export_history("subj-01", [], purpose=Purpose.EXPORT)
    assert not (tmp_path / "logs").exists(), "a refused export writes no log"


def test_an_l5_dose_is_dropped_and_a_wholly_l5_history_is_refused(tmp_path, monkeypatch):
    """serve_all drops what denies, so an L5 datum (which no immunization record
    should hold, but the rule is the rule) never reaches the form — and a history
    with nothing left to carry is refused, not ledgered as an export of the empty
    set."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    sealed = Classified(Rung.L5, {"vaccine": "SEALED", "subject": "subj-01"})
    receipt = export_history(
        "subj-01", [_dose("MMR", "2026-08-15"), sealed], purpose=Purpose.EXPORT
    )
    body = json.loads(receipt.artifact.read_text(encoding="utf-8"))
    vaccines = {row["vaccine"] for row in body["content"]}
    assert vaccines == {"MMR"}, "the L5 dose is dropped, not exported"
    assert "SEALED" not in receipt.artifact.read_text(encoding="utf-8")

    with pytest.raises(ExportRefused):
        export_history("subj-01", [sealed], purpose=Purpose.EXPORT)


def test_an_undeclared_purpose_is_refused(tmp_path, monkeypatch):
    """A purpose is required — an export is a purposeful act. Passing None reaches
    keep/export's own refusal; the school form does not invent a default that lets
    a purposeless export through."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    with pytest.raises(ExportRefused):
        export_history("subj-01", [_dose("MMR", "2026-08-15")], purpose=None)


def test_a_malformed_subject_id_is_refused_before_anything_is_written(tmp_path, monkeypatch):
    """The audit's critical finding, closed at the app boundary. The engine's two
    reference validators disagree about newlines (keep/export accepts one,
    keep/logs rejects it), and export_record writes the artifact and commits the
    IntegrityLog *before* the VisibleLog — so a subject id with a newline would
    leave the record on disk and in the ledger and then raise: a leak that looks
    like a refusal. So a malformed id is refused here, with nothing written, before
    a dose is served."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    for bad in ("subj-01\nFORGED", "subj\t01", "a/b", "..", "\u200b", "  ", None):
        with pytest.raises(ExportRefused):
            export_history(bad, [_dose("MMR", "2026-08-15")], purpose=Purpose.EXPORT)

    # The clincher: after a refused newline id, nothing was written — no artifact,
    # no ledger entry, no visible act. A refusal leaves nothing behind.
    assert not (tmp_path / "logs").exists(), "a refused malformed id writes no log"
    assert not (tmp_path / "exports").exists(), "a refused malformed id writes no artifact"


def test_a_same_instant_collision_surfaces_as_export_refused(tmp_path, monkeypatch):
    """The module's contract is ExportRefused; a same-microsecond filename collision
    in the export tree surfaces from the engine as a bare FileExistsError (the
    artifact's O_EXCL create, before any log write). It is converted at this
    boundary so a batch-export caller gets the contract's exception, not a raw
    filesystem error — and because the collision precedes any ledger write, nothing
    is left half-committed."""
    import homestead_health.school_form as sf

    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    def collide(*args, **kwargs):
        raise FileExistsError("[Errno 17] File exists")

    monkeypatch.setattr(sf, "export_record", collide)
    with pytest.raises(ExportRefused):
        export_history("subj-01", [_dose("MMR", "2026-08-15")], purpose=Purpose.EXPORT)


def test_the_export_names_the_subject_by_id_never_a_name(tmp_path, monkeypatch):
    """H-1 rides through the egress: the ref the artifact and both logs carry is the
    opaque subject id, and a SubjectRef stringifies to that id. Nothing about the
    subject beyond the id crosses into a reference."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    from homestead_health.roster import SubjectRef

    receipt = export_history(
        SubjectRef("subj-07"), [_dose("MMR", "2026-08-15", subject="subj-07")],
        purpose=Purpose.EXPORT,
    )
    assert receipt.ref == "immunizations/history/subj-07"
    visible = VisibleLog().read()
    assert visible[0]["ref"] == "immunizations/history/subj-07"
