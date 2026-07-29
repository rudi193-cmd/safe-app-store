"""P2's gate: identity, roles and consent.

Same standard as test_gate.py. These do not check that the consent code works —
test_provenance-style tests would do that. They check that it *cannot be made to
misbehave*: that a truncated log fails verification, that a minor cannot consent
for themselves, that a guardian's authority ends on a birthday with nothing
scheduled, that the person who benefits from a grant can neither ask for it nor
sign it, and that a member who declined is byte-identical to a member who does
not exist — now including the guardian's view of them.

Every assertion here was written by breaking the implementation first and
confirming this file went red. A gate that cannot fail is not a gate.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts import Band, GrantState, Principal, Store  # noqa: E402
from marching_arts.consent import (  # noqa: E402
    CONSENT_CHAIN,
    consent_chain,
    ChainTamperError,
    ConsentedRoster,
    DeidentificationError,
    SqliteConsentBackend,
    SubjectConsentError,
    consent_core_path,
    disclosure_chain,
)

LEADER = Principal("leader")
PARENT = Principal("parent")
STRANGER = Principal("stranger")

TODAY = datetime.date.today()


def birthdate(age_in_years: int) -> str:
    """An ISO birthdate for someone who is exactly this old today.

    Ages rather than fixed dates, so this suite does not quietly start testing
    something else in 2044.
    """
    try:
        return TODAY.replace(year=TODAY.year - age_in_years).isoformat()
    except ValueError:  # 29 February
        return TODAY.replace(year=TODAY.year - age_in_years, day=28).isoformat()


@pytest.fixture()
def roster():
    """A fifteen-year-old with a registered guardian, and an adult member."""
    r = ConsentedRoster(Store(":memory:"))
    r.register_member("minor-member", birthdate(15), "registration form")
    r.register_member("adult-member", birthdate(22), "registration form")
    r.register_guardian("parent", "minor-member", "child", "registration form")
    for i in range(3):
        r.store.record_fact("minor-member", Band.CRAFT, "rehearsal log",
                            payload=f"minor {i}")
        r.store.record_fact("adult-member", Band.CRAFT, "rehearsal log",
                            payload=f"adult {i}")
    return r


# ── the canonical core, not a fork ──────────────────────────────────────────
def test_the_consent_core_is_the_canonical_copy_not_a_fork():
    """UTETY's vendored copy is a worked example, not a source.

    Two copies of a consent primitive is how two consumers end up disagreeing
    about what "revoked" means, and the disagreement surfaces as an
    authorization, not as an error.
    """
    path = consent_core_path()
    assert "utety" not in [p.lower() for p in path.parts], f"forked core: {path}"


# ── grant / revoke / permitted ──────────────────────────────────────────────
def test_grant_revoke_permitted_round_trip(roster):
    assert roster.permitted("adult-member", "process_analysis") is False
    roster.grant_use("adult-member", "process_analysis", "adult-member")
    assert roster.permitted("adult-member", "process_analysis") is True
    roster.revoke_use("adult-member", "process_analysis", "adult-member")
    assert roster.permitted("adult-member", "process_analysis") is False


def test_permitted_is_fail_closed_on_everything_else(roster):
    assert roster.permitted("nobody-at-all", "local_only") is False
    assert roster.permitted("adult-member", "not-a-scope") is False


def test_consent_and_domain_data_are_one_file(tmp_path):
    """The point of the whole binding: back up one file or back up nothing.

    A consent record that can be restored out of step with the data it governs
    will eventually authorize something nobody agreed to.
    """
    db = tmp_path / "corps.db"
    r = ConsentedRoster(Store(str(db)))
    r.register_member("adult-member", birthdate(22), "registration form")
    r.store.record_fact("adult-member", Band.CRAFT, "rehearsal log", payload="x")
    r.grant_use("adult-member", "local_only", "adult-member")
    r.seal("adult-member", "leader", Band.CRAFT, "adult-member", "consent form")
    r.connection.close()

    reopened = sqlite3.connect(str(db))
    tables = {row[0] for row in reopened.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"facts", "grants", "people", "consent_chain",
            "consent_anchor"} <= tables
    assert reopened.execute("SELECT COUNT(*) FROM consent_chain").fetchone()[0] > 0
    assert reopened.execute("SELECT COUNT(*) FROM facts").fetchone()[0] > 0


# ── the count anchor: a plain chain does not detect tail truncation ─────────
def _rows(roster, chain):
    return [json.loads(r[0]) for r in roster.connection.execute(
        "SELECT row FROM consent_chain WHERE chain = ? ORDER BY seq", (chain,))]


def test_tail_truncation_is_detected_only_because_of_the_count_anchor(roster):
    """Delete the newest rows and the survivors still link perfectly.

    This is the attack the anchor exists for, and the newest rows are exactly
    the ones worth deleting: the revocation, and the disclosure that names you.
    So the test asserts *both* halves — that the truncated chain still passes a
    links-only check, and that verification fails anyway.
    """
    chain = disclosure_chain("adult-member")
    for i in range(3):
        roster._disclose("adult-member", "test.event", f"row {i}")
    before = _rows(roster, chain)
    assert len(before) == 3

    roster.connection.execute(
        "DELETE FROM consent_chain WHERE chain = ? AND seq = ?", (chain, 3))
    roster.connection.commit()

    # Links-only: every prev_hash still names the row before it. A chain
    # verifier without the count anchor would sign this off.
    after = _rows(roster, chain)
    assert len(after) == 2
    assert after[1]["prev_hash"] == after[0]["hash"]

    # The anchor still says three.
    assert roster.backend.read_anchor(chain)["count"] == 3
    with pytest.raises(ChainTamperError):
        roster.disclosures("adult-member", reader="adult-member")


def test_a_truncated_consent_chain_denies_rather_than_answers(roster):
    """The gate does not raise. It says no."""
    roster.grant_use("adult-member", "local_only", "adult-member")
    roster.grant_use("adult-member", "kb_promotion", "adult-member")
    assert roster.permitted("adult-member", "kb_promotion") is True
    roster.connection.execute(
        "DELETE FROM consent_chain WHERE chain = ? AND seq ="
        " (SELECT MAX(seq) FROM consent_chain WHERE chain = ?)",
        (consent_chain("adult-member"), consent_chain("adult-member")))
    roster.connection.commit()
    assert roster.permitted("adult-member", "local_only") is False
    assert roster.permitted("adult-member", "kb_promotion") is False
    with pytest.raises(ChainTamperError):
        roster.verify()


def test_deleting_the_whole_chain_is_not_the_same_as_never_having_one(roster):
    """The complete truncation, which the file backend cannot see.

    ``read_rows`` returning ``None`` means "absent", and absent is legitimately
    not tampered. Return ``None`` for an emptied chain too and the strongest
    attack available is also the simplest one: delete every row. This backend
    keeps the anchor in the same store, so an orphaned anchor is evidence that
    rows were here, and the chain reads as emptied rather than as absent.
    """
    roster.grant_use("adult-member", "local_only", "adult-member")
    roster.connection.execute("DELETE FROM consent_chain WHERE chain = ?",
                              (consent_chain("adult-member"),))
    roster.connection.commit()
    assert roster.backend.for_subject("adult-member").read_rows(CONSENT_CHAIN) == []   # emptied, not absent
    assert roster.backend.read_rows("disclosure/never-existed") is None
    assert roster.permitted("adult-member", "local_only") is False
    with pytest.raises(ChainTamperError):
        roster.verify()


def test_a_mid_chain_edit_is_detected(roster):
    roster.grant_use("adult-member", "local_only", "adult-member")
    roster.revoke_use("adult-member", "local_only", "adult-member")
    row = json.loads(roster.connection.execute(
        "SELECT row FROM consent_chain WHERE chain = ? AND seq = 1",
        (consent_chain("adult-member"),)).fetchone()[0])
    row["status"] = "revoked"
    roster.connection.execute(
        "UPDATE consent_chain SET row = ? WHERE chain = ? AND seq = 1",
        (json.dumps(row, sort_keys=True), consent_chain("adult-member")))
    roster.connection.commit()
    assert roster.permitted("adult-member", "local_only") is False
    with pytest.raises(ChainTamperError):
        roster.verify()


def test_a_tampered_chain_is_not_silently_extended(roster):
    """Appending to a broken log would launder it. It refuses instead."""
    roster.grant_use("adult-member", "local_only", "adult-member")
    roster.connection.execute(
        "UPDATE consent_anchor SET count = count + 1 WHERE chain = ?",
        (consent_chain("adult-member"),))
    roster.connection.commit()
    with pytest.raises(ChainTamperError):
        roster.grant_use("adult-member", "kb_promotion", "adult-member")


# ── guardian consent for minors — not member consent ────────────────────────
def test_a_minor_cannot_consent_for_themselves(roster):
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("minor-member", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="minor-member")


def test_a_minors_grant_must_be_guardian_derived(roster):
    """Not merely signed by an adult — declared as guardian-derived, so that
    the expiry clause in the resolver has something to bite on."""
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("minor-member", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="parent", granted_via="member")


def test_only_a_registered_guardian_may_seal_for_a_minor(roster):
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("minor-member", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="some-adult", granted_via="guardian")


def test_the_roster_derives_guardian_or_member_rather_than_taking_it(roster):
    """A caller cannot declare a minor's consent to be their own."""
    roster.seal("minor-member", "leader", Band.CRAFT, "parent", "consent form")
    roster.seal("adult-member", "leader", Band.CRAFT, "adult-member", "consent form")
    via = dict(roster.connection.execute(
        "SELECT subject_id, granted_via FROM grants"))
    assert via == {"minor-member": "guardian", "adult-member": "member"}


def test_a_person_with_no_birthdate_on_file_is_not_a_minor(roster):
    """Fail-closed, and note which way closed points for *this* question.

    Treating an unknown person as a minor would be the cautious-looking answer
    and it is the wrong one: guardian authority is the single mechanism that
    opens somebody's record without their own signature, so "we don't know who
    this is" must not be a route to claiming it.
    """
    assert roster.is_minor("never-registered") is False
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("never-registered", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="self-declared-parent",
                                  granted_via="guardian")
    roster.seal("never-registered", "leader", Band.CRAFT,
                "never-registered", "consent form")
    assert roster.connection.execute(
        "SELECT granted_via FROM grants WHERE subject_id = 'never-registered'"
    ).fetchone()[0] == "member"


@pytest.mark.parametrize("bad", ["not-a-date", "2010-13-45", "", "15"])
def test_a_birthdate_that_is_not_a_date_is_refused(roster, bad):
    """The failure direction is what makes this a gate rather than hygiene.

    ``date('not-a-date')`` is NULL, every comparison against it is NULL, and
    NULL is not true — so a malformed birthdate does not raise anywhere, it
    silently reclassifies a minor as an adult and takes the guardian
    requirement off them. A CHECK that evaluates to NULL *passes*, which is why
    the constraint tests ``date(birthdate) IS NOT NULL`` and not just equality.
    """
    with pytest.raises(sqlite3.IntegrityError):
        roster.register_member("new-member", bad, "registration form")
    assert roster.is_minor("new-member") is False


def test_a_guardianship_must_be_over_somebody_else_who_exists(roster):
    with pytest.raises(SubjectConsentError):
        roster.register_guardian("minor-member", "minor-member", "self",
                                 "registration form")
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_guardianship("minor-member", "minor-member",
                                         "child", "registration form")
    with pytest.raises(sqlite3.IntegrityError):
        roster.register_guardian("parent", "no-such-member", "child",
                                 "registration form")


def test_a_minors_use_consent_must_come_from_a_guardian(roster):
    """The same rule over subject-consent's own hash-chained log — enforced by
    joining the chain to the roster inside one database, which is exactly what
    a JSONL file beside the app could not do."""
    with pytest.raises(sqlite3.IntegrityError):
        roster.grant_use("minor-member", "person_inference", "minor-member")
    assert roster.permitted("minor-member", "person_inference") is False
    roster.grant_use("minor-member", "person_inference", "parent")
    assert roster.permitted("minor-member", "person_inference") is True


def test_a_refused_chain_write_leaves_the_chain_usable(roster):
    """A refusal must not wedge the log it refused to extend."""
    with pytest.raises(sqlite3.IntegrityError):
        roster.grant_use("minor-member", "local_only", "minor-member")
    roster.grant_use("minor-member", "local_only", "parent")
    assert roster.permitted("minor-member", "local_only") is True
    roster.verify()


# ── guardian access converts at 18 rather than persisting ───────────────────
def test_guardian_access_stops_at_majority_with_nothing_scheduled(roster):
    """The birthday is the mechanism. No job runs, and no job can fail to run.

    A guardian holds craft-band access to their fifteen-year-old. The same
    grant, unchanged in the table, authorizes nothing once the birthdate says
    the member is eighteen.
    """
    roster.seal("minor-member", "parent", Band.CRAFT, "parent", "consent form")
    assert roster.count(PARENT) == 3

    roster.register_member("minor-member", birthdate(18), "corrected registration")
    assert roster.count(PARENT) == 0
    assert roster.subjects(PARENT) == []
    # The row is untouched: nothing ran, and the access is gone anyway.
    assert roster.connection.execute(
        "SELECT state FROM grants WHERE grantee_id = 'parent'"
    ).fetchone()[0] == GrantState.SEALED.value


def test_conversion_asks_the_member_rather_than_assuming_them(roster):
    """The second half: a grant a guardian gave at fifteen becomes a question
    for the member at eighteen, not an inheritance."""
    roster.seal("minor-member", "parent", Band.CRAFT, "parent", "consent form")
    roster.seal("minor-member", "leader", Band.CRAFT, "parent", "consent form")

    assert roster.convert_at_majority("minor-member") == []  # still a minor

    roster.register_member("minor-member", birthdate(18), "corrected registration")
    assert roster.convert_at_majority("minor-member") == ["leader", "parent"]

    rows = roster.connection.execute(
        "SELECT state, granted_via, sealed_by FROM grants"
        " WHERE subject_id = 'minor-member'").fetchall()
    assert rows == [(GrantState.PENDING.value, "member", None)] * 2
    assert roster.count(PARENT) == 0
    assert roster.count(LEADER) == 0


def test_guardian_authority_cannot_be_written_for_an_adult(roster):
    """Not merely un-honoured at read time — unwritable."""
    roster.register_guardian("parent", "adult-member", "other", "registration form")
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("adult-member", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="parent", granted_via="guardian")


def test_a_guardians_disclosure_access_expires_too(roster):
    roster.seal("minor-member", "parent", Band.CRAFT, "parent", "consent form")
    assert roster.disclosures("minor-member", reader="parent") != []
    roster.register_member("minor-member", birthdate(18), "corrected registration")
    assert roster.disclosures("minor-member", reader="parent") == []
    # The member's own record is still theirs.
    assert roster.disclosures("minor-member", reader="minor-member") != []


# ── silent revocation ───────────────────────────────────────────────────────
def test_revocation_is_silent_and_leaves_no_residue(roster):
    roster.seal("adult-member", "leader", Band.CRAFT, "adult-member", "consent form")
    assert roster.count(LEADER) == 3

    assert roster.revoke("adult-member", "leader", "adult-member") is None

    assert roster.count(LEADER) == 0
    assert roster.subjects(LEADER) == []
    assert roster.connection.execute(
        "SELECT COUNT(*) FROM grants WHERE grantee_id = 'leader'"
    ).fetchone()[0] == 0


def test_revocation_history_lives_in_the_disclosure_ledger(roster):
    """No residue in the table the resolver reads; a permanent record in the
    log the subject reads. Those are different requirements and this is how
    both are met at once."""
    roster.seal("adult-member", "leader", Band.CRAFT, "adult-member", "consent form")
    roster.revoke("adult-member", "leader", "adult-member", reason="left the corps")
    actions = [d["action"] for d in
               roster.disclosures("adult-member", reader="adult-member")]
    assert actions == ["grant.sealed", "grant.revoked"]
    # The grantee has no path to it.
    assert roster.disclosures("adult-member", reader="leader") == []


def test_a_revocation_and_its_ledger_row_are_one_transaction(roster):
    """UTETY's audit B4, applied to the revocation path.

    If the ledger write fails, the delete must not survive it — otherwise a
    crash at the wrong moment produces an access removal with no record that it
    happened, which is indistinguishable from tampering after the fact.
    """
    roster.seal("adult-member", "leader", Band.CRAFT, "adult-member", "consent form")

    class _AnchorCrashes(SqliteConsentBackend):
        def write_anchor(self, chain, anchor):
            raise RuntimeError("power cut between the row and the anchor")

    roster.backend = _AnchorCrashes(roster.connection)
    with pytest.raises(RuntimeError):
        roster.revoke("adult-member", "leader", "adult-member")

    assert roster.connection.in_transaction, "the delete had already committed"
    roster.connection.rollback()          # what reopening after a crash does
    assert roster.count(LEADER) == 3      # the grant is back
    roster.backend = SqliteConsentBackend(roster.connection)
    assert [d["action"] for d in
            roster.disclosures("adult-member", reader="adult-member")] == \
        ["grant.sealed"]


# ── consent is never obtained by the person who benefits from it ────────────
def test_the_beneficiary_cannot_request_their_own_access(roster):
    """A section leader asking their own squad is coercion with extra steps."""
    with pytest.raises(sqlite3.IntegrityError):
        roster.request("adult-member", "leader", Band.CRAFT,
                       requested_by="leader", source="asked at rehearsal")


def test_the_beneficiary_cannot_sign_their_own_access(roster):
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("adult-member", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="leader")


def test_a_third_party_may_ask_and_the_ask_is_on_the_record(roster):
    roster.request("adult-member", "leader", Band.CRAFT,
                   requested_by="director", source="staffing review")
    assert roster.count(LEADER) == 0, "a request authorizes nothing"
    detail = roster.disclosures("adult-member", reader="adult-member")[0]
    assert detail["action"] == "grant.requested"
    assert "by=director" in detail["detail"]


def test_a_registered_guardian_is_the_one_carve_out(roster):
    """A parent's access to their own minor's record is the relationship, not
    an abuse of one — and it still ends at eighteen like every other."""
    roster.seal("minor-member", "parent", Band.CRAFT, "parent", "consent form",
                requested_by="parent")
    assert roster.count(PARENT) == 3
    # The carve-out is guardianship, not adulthood: an unrelated adult gets no
    # such licence over the same member.
    with pytest.raises(sqlite3.IntegrityError):
        roster.store.record_grant("minor-member", "leader", Band.CRAFT,
                                  GrantState.SEALED.value, "consent form",
                                  sealed_by="leader", granted_via="guardian")


# ── de-identify or refuse ───────────────────────────────────────────────────
class MissedIdentifier(str):
    """An identifier the removal pass does not find but the verify pass does.

    Its first ``.lower()`` — the one used to build the search needle — answers
    with something absent from the text; every later one answers honestly. That
    is the shape of a real de-identification bug: a normalisation mismatch
    between the pass that removes and the pass that checks. Without the check,
    this text ships with the name still in it and nothing anywhere says so.
    """

    def __init__(self, *_args) -> None:
        self._calls = 0

    def lower(self) -> str:
        self._calls += 1
        return "a needle that is not in the text" if self._calls == 1 else str.lower(self)


SUBJECT_TEXT = "Rivera struggled with the left-foot lead"


def test_deidentification_is_verified_not_attempted(roster):
    out = roster.disclose_text("adult-member", "kb.promotion",
                               SUBJECT_TEXT, ["Rivera"])
    assert isinstance(out, str)
    recorded = roster.disclosures("adult-member", reader="adult-member")[0]
    assert "Rivera" not in recorded["detail"]
    assert "left-foot lead" in recorded["detail"], \
        "de-identified is process; the process is what was supposed to survive"


def test_a_scrub_that_cannot_be_proved_refuses(roster):
    with pytest.raises(DeidentificationError):
        roster.disclose_text("adult-member", "kb.promotion", SUBJECT_TEXT,
                             [MissedIdentifier("Rivera")])


def test_the_refusal_never_carries_the_value(roster):
    """An error message is a disclosure channel like any other."""
    with pytest.raises(DeidentificationError) as caught:
        roster.disclose_text("adult-member", "kb.promotion", SUBJECT_TEXT,
                             [MissedIdentifier("Rivera")])
    message = str(caught.value)
    assert "Rivera" not in message and "left-foot lead" not in message


def test_a_refused_disclosure_writes_nothing(roster):
    """Refuse *before* the append, so a failed scrub does not put the name in
    the very log that was supposed to prove it never went anywhere."""
    with pytest.raises(DeidentificationError):
        roster.disclose_text("adult-member", "kb.promotion", SUBJECT_TEXT,
                             [MissedIdentifier("Rivera")])
    assert roster.disclosures("adult-member", reader="adult-member") == []
    assert roster.connection.execute(
        "SELECT COUNT(*) FROM consent_chain").fetchone()[0] == 0


# ── only a sealed grant authorizes ──────────────────────────────────────────
def test_a_pending_grant_authorizes_nothing(roster):
    roster.request("adult-member", "leader", Band.CRAFT,
                   requested_by="director", source="staffing review")
    assert roster.count(LEADER) == 0
    assert roster.subjects(LEADER) == []


def test_a_draft_guardian_grant_is_inert(roster):
    """Draft is what a machine may produce. The machine may not seal, and a
    draft that named a real guardian would still authorize nothing."""
    roster.store.record_grant("minor-member", "leader", Band.CRAFT,
                              GrantState.DRAFT.value, "inferred from roster",
                              granted_via="guardian")
    assert roster.count(LEADER) == 0
    assert roster.subjects(LEADER) == []


# ── refusal stays invisible — extended to guardians ─────────────────────────
def _view(roster, principal, subject):
    """Everything a principal can learn about one subject, in one tuple.

    Rows, the count, whether the subject occupies a slot in the list, and
    whatever the disclosure log will hand this reader. A refusal that differs in
    any one of the four is a refusal that can be detected.
    """
    return (
        roster.visible(principal, where="facts.subject_id = :s",
                       params={"s": subject}),
        roster.count(principal, where="facts.subject_id = :s",
                     params={"s": subject}),
        subject in roster.subjects(principal),
        roster.disclosures(subject, reader=principal.person_id),
    )


def test_a_minor_whose_guardian_declined_is_indistinguishable_from_no_such_member(roster):
    """The existing gate, carried onto the guardian path.

    A guardian who did not consent must leave their member looking exactly like
    a member who was never enrolled. If the two differ anywhere — a count, a
    list length, an empty slot, a readable log — then declining is the signal,
    and every family who exercised the choice is marked by exercising it.
    """
    declined = _view(roster, LEADER, "minor-member")
    absent = _view(roster, LEADER, "no-such-member")
    assert declined == absent == ([], 0, False, [])


def test_a_guardian_who_declined_is_indistinguishable_from_no_guardian(roster):
    """And symmetrically, from the guardian's side of the seat.

    ``parent`` is a registered guardian who has sealed nothing; ``stranger`` is
    nobody at all. Neither may learn that the difference exists.
    """
    as_guardian = _view(roster, PARENT, "minor-member")
    as_nobody = _view(roster, STRANGER, "minor-member")
    assert as_guardian == as_nobody == ([], 0, False, [])
    assert roster.count(PARENT) == roster.count(STRANGER) == 0
    assert roster.subjects(PARENT) == roster.subjects(STRANGER) == []


def test_a_revoked_guardian_is_indistinguishable_from_one_who_never_consented(roster):
    """Compared on the data surface only.

    A guardian keeps their entitlement to the *subject's* disclosure log while
    the subject is a minor — that log is the member's record and the guardian
    reads it on the member's behalf, not on their own. Silent revocation is a
    claim about what a grantee can observe of the data, and this is the version
    of it that holds for the case where grantee and guardian are one person.
    """
    def data_surface(principal, subject):
        return _view(roster, principal, subject)[:3]

    roster.seal("minor-member", "parent", Band.CRAFT, "parent", "consent form")
    assert roster.count(PARENT) == 3
    roster.revoke("minor-member", "parent", "minor-member")
    assert data_surface(PARENT, "minor-member") == \
        data_surface(STRANGER, "no-such-member") == ([], 0, False)


def test_a_revoked_third_party_learns_nothing_at_all(roster):
    """And for a grantee who is not a guardian, the stronger claim holds whole:
    every channel, including the log."""
    roster.seal("minor-member", "leader", Band.CRAFT, "parent", "consent form")
    assert roster.count(LEADER) == 3
    roster.revoke("minor-member", "leader", "parent")
    assert _view(roster, LEADER, "minor-member") == \
        _view(roster, LEADER, "no-such-member") == ([], 0, False, [])


def test_expiry_at_majority_is_as_invisible_as_a_refusal(roster):
    """Turning eighteen must not look different from never having consented.

    Otherwise the grantee learns a birthday, which is L1 data they were not
    given, from the shape of an absence.
    """
    roster.seal("minor-member", "leader", Band.CRAFT, "parent", "consent form")
    roster.register_member("minor-member", birthdate(18), "corrected registration")
    expired = _view(roster, LEADER, "minor-member")
    never = _view(roster, LEADER, "no-such-member")
    assert expired == never == ([], 0, False, [])


def test_probing_the_disclosure_log_tells_a_grantee_nothing(roster):
    """A subject with a rich history and a subject who does not exist answer a
    non-entitled reader identically."""
    roster.seal("adult-member", "leader", Band.CRAFT, "adult-member", "consent form")
    roster.revoke("adult-member", "leader", "adult-member")
    assert roster.disclosures("adult-member", reader="leader") == \
        roster.disclosures("no-such-member", reader="leader") == []


def test_the_chain_name_does_not_leak_the_subject(roster):
    """Chain names are hashed, so the set of table keys is not a roster."""
    roster._disclose("adult-member", "test.event")
    names = {r[0] for r in roster.connection.execute(
        "SELECT DISTINCT chain FROM consent_chain")}
    assert "adult-member" not in " ".join(names)
    assert disclosure_chain("adult-member") == \
        "disclosure/" + hashlib.sha256(b"adult-member").hexdigest()[:32]


# ── one member's consent chain is theirs alone ────────────────────────────────
#
# Before partitioning, every subject's transitions were links in one global
# chain. Deleting one member's rows to honour a request broke consent for the
# whole corps, and refusing to delete them was the only alternative. These are
# the tests for the fix, and each one fails against the old global chain.

def _adults(roster, *ids):
    for i in ids:
        roster.register_member(i, "1998-01-01", "test")
        roster.grant_use(i, "local_only", i)
    return ids


def test_forgetting_one_member_leaves_everyone_elses_consent_intact(roster):
    _adults(roster, "alice", "bob", "carol")
    roster.connection.execute("DELETE FROM consent_chain WHERE chain = ?",
                              (consent_chain("bob"),))
    roster.connection.execute("DELETE FROM consent_anchor WHERE chain = ?",
                              (consent_chain("bob"),))
    roster.connection.commit()

    assert roster.permitted("alice", "local_only") is True
    assert roster.permitted("carol", "local_only") is True
    assert roster.permitted("bob", "local_only") is False
    roster.verify()  # sweeps every remaining chain; none is broken


def test_a_forgotten_member_is_indistinguishable_from_one_who_never_existed(roster):
    _adults(roster, "dave")
    roster.connection.execute("DELETE FROM consent_chain WHERE chain = ?",
                              (consent_chain("dave"),))
    roster.connection.execute("DELETE FROM consent_anchor WHERE chain = ?",
                              (consent_chain("dave"),))
    roster.connection.commit()

    gone = roster.backend.for_subject("dave")
    never = roster.backend.for_subject("no-such-person")
    assert gone.read_rows(CONSENT_CHAIN) is None      # absent, not emptied
    assert never.read_rows(CONSENT_CHAIN) is None
    assert roster.permitted("dave", "local_only") is False
    roster.verify()


def test_one_tampered_chain_does_not_hide_behind_the_others(roster):
    """Independence cuts both ways: a broken chain no longer breaks the corps,
    which is also how one could go unnoticed. The sweep is what closes that."""
    _adults(roster, "erin", "frank")
    roster.connection.execute(
        "UPDATE consent_anchor SET count = count + 1 WHERE chain = ?",
        (consent_chain("frank"),))
    roster.connection.commit()

    roster.verify("erin")                       # erin's chain is fine
    with pytest.raises(ChainTamperError):
        roster.verify("frank")
    with pytest.raises(ChainTamperError):
        roster.verify()                         # and the sweep finds it


def test_a_consent_row_cannot_be_written_into_another_subjects_chain(roster):
    """The partition must be a fact, not a filing convention — otherwise
    deleting one member's chain silently takes another member's consent."""
    _adults(roster, "gina")
    wrong = roster.backend.for_subject("gina")
    with pytest.raises(SubjectConsentError):
        wrong.append_row(CONSENT_CHAIN, {"subject_id": "someone-else",
                                         "scope": "local_only",
                                         "status": "granted"})


def test_an_unscoped_backend_refuses_the_consent_chain(roster):
    """Fail closed. An unscoped write would land in a global chain and rebuild
    exactly the entanglement this removes."""
    with pytest.raises(SubjectConsentError):
        roster.backend.read_rows(CONSENT_CHAIN)
    with pytest.raises(SubjectConsentError):
        roster.backend.append_row(CONSENT_CHAIN, {"subject_id": "gina"})


def test_the_guardian_rule_survived_the_partitioning(roster):
    """The regression this migration exists for: 003's trigger matched the
    chain name EXACTLY, so adding a suffix silently switched it off and a minor
    could consent for themselves."""
    roster.register_member("kid", "2012-01-01", "test")
    with pytest.raises(sqlite3.IntegrityError):
        roster.grant_use("kid", "local_only", "kid")


def test_the_old_global_chain_name_cannot_dodge_the_guardian_rule(roster):
    """A writer reaching past this module could otherwise insert under the bare
    name the trigger used to match, and slip through the gap."""
    roster.register_member("kid2", "2012-01-01", "test")
    row = json.dumps({"subject_id": "kid2", "scope": "local_only",
                      "status": "granted", "granted_by": "kid2"}, sort_keys=True)
    with pytest.raises(sqlite3.IntegrityError):
        roster.connection.execute(
            "INSERT INTO consent_chain(chain, seq, row) VALUES ('consent', 1, ?)",
            (row,))


# ── conversion has a caller, and the caller is opening the roster ───────────
#
# Expiry is a predicate and needs nobody to run it. Conversion is a write, and
# until now nothing outside this file and the demo ever called it: a member
# turned eighteen, guardian access correctly stopped resolving, and nobody was
# ever asked whether they wanted to grant it themselves. These are the gates on
# the pass that closes that, and each one was written by breaking the
# implementation first.


@pytest.fixture()
def aged_out(tmp_path):
    """A file-backed corps where a member turned eighteen while it was shut.

    Sealed by a registered guardian at fifteen, then the birthday passes with
    the file closed — which is the whole scenario, because a local-first app on
    a corps laptop has no process running to notice.
    """
    db = tmp_path / "corps.db"
    r = ConsentedRoster(Store(str(db)))
    r.register_member("member", birthdate(15), "registration form")
    r.register_guardian("parent", "member", "child", "registration form")
    for i in range(3):
        r.store.record_fact("member", Band.CRAFT, "rehearsal log",
                            payload=f"member {i}")
    r.seal("member", "parent", Band.CRAFT, "parent", "consent form")
    r.seal("member", "leader", Band.CRAFT, "parent", "consent form")
    r.register_member("member", birthdate(18), "corrected registration")
    r.connection.close()
    return db


class _ChainCrashes(SqliteConsentBackend):
    """A backend that dies between the row and the anchor for ONE subject.

    Scoped to one chain rather than all of them so the sweep's isolation is
    testable: a chain nobody can extend must not stop the members either side
    of it from being asked.
    """

    def __init__(self, conn, doomed_chain):
        super().__init__(conn)
        self._doomed = doomed_chain

    def write_anchor(self, chain, anchor):
        if chain == self._doomed:
            raise RuntimeError("power cut between the row and the anchor")
        return super().write_anchor(chain, anchor)


def test_opening_the_roster_is_what_converts(aged_out):
    """The gap this closes: the write had no caller in any real flow.

    Opening is the right one for an offline app with no scheduler, and it is
    where migrations already run — ``Store.__init__`` brings the schema up to
    date on construction, this brings consent state up to date on the same
    call. Opened with the pass switched off, the guardian seals are still
    sitting there; opened normally, the member has been asked.
    """
    untouched = ConsentedRoster(Store(str(aged_out)), convert_on_open=False)
    assert untouched.opened.converted == {}
    assert untouched.connection.execute(
        "SELECT COUNT(*) FROM grants WHERE granted_via = 'guardian'"
    ).fetchone()[0] == 2
    untouched.connection.close()

    opened = ConsentedRoster(Store(str(aged_out)))
    assert opened.opened.converted == {"member": ["leader", "parent"]}
    assert opened.opened.unconvertible == ()
    assert opened.connection.execute(
        "SELECT state, granted_via, sealed_by, requested_by FROM grants"
        " WHERE subject_id = 'member' ORDER BY grantee_id"
    ).fetchall() == [(GrantState.PENDING.value, "member", None, None)] * 2


def test_opening_twice_asks_once(aged_out):
    """Idempotence, and it is the ledger that makes it matter.

    The disclosure chain is append-only, so a pass that ran twice would leave a
    member's permanent record saying their guardian's authority ended twice.
    Nothing bookkeeps this: a converted grant is no longer guardian-derived, so
    it no longer matches the query that finds work.
    """
    first = ConsentedRoster(Store(str(aged_out)))
    assert first.opened.converted == {"member": ["leader", "parent"]}
    ledger = [d["action"] for d in first.disclosures("member", reader="member")]
    assert ledger.count("grant.converted_at_majority") == 2  # one per grantee
    first.connection.close()

    for _ in range(2):
        again = ConsentedRoster(Store(str(aged_out)))
        assert again.opened.converted == {}, "a second open asked a second time"
        assert [d["action"] for d in
                again.disclosures("member", reader="member")] == ledger
        again.connection.close()


def test_conversion_never_mints_a_grant_nobody_signed(aged_out):
    """The one thing the whole schema refuses, at the one write that could.

    Carrying the guardian's seal across and relabelling it ``member`` would
    look like continuity and would be a forgery — the member never signed
    anything. Nothing below this module would stop it: the subject is no longer
    a minor, so the guardian triggers do not fire, and ``sealed_by`` would be
    populated, so the CHECK is satisfied. The second half of this test performs
    that write by hand to show the database accepts it.
    """
    r = ConsentedRoster(Store(str(aged_out)))
    for state, via, sealed_by in r.connection.execute(
            "SELECT state, granted_via, sealed_by FROM grants"
            " WHERE subject_id = 'member'"):
        assert (state, via, sealed_by) == (GrantState.PENDING.value, "member", None)
    assert r.count(LEADER) == 0
    assert r.count(PARENT) == 0
    assert r.subjects(LEADER) == []

    r.connection.execute(
        "UPDATE grants SET state = 'sealed', granted_via = 'member',"
        "                  sealed_by = 'member'"
        " WHERE subject_id = 'member' AND grantee_id = 'leader'")
    r.connection.commit()
    assert r.count(LEADER) == 3, (
        "if this stops being true the schema grew a rule and this test can be"
        " weakened; while it is true, this test is the only thing refusing it")


def test_an_unanswered_conversion_is_not_itself_a_disclosure(aged_out):
    """A pending ask leaks a birthday and a former guardianship, or it would.

    If a section leader could see that a member has an unanswered conversion
    request, they would have learned that the member just turned eighteen and
    that somebody used to consent on their behalf — two L1 facts nobody granted
    them, recovered from the shape of a question. So the ask exists only in the
    grants table, where it authorizes nothing, and in the member's own ledger,
    which is now theirs alone.
    """
    r = ConsentedRoster(Store(str(aged_out)))
    assert _view(r, LEADER, "member") == \
        _view(r, LEADER, "no-such-member") == ([], 0, False, [])

    # Not written into the grantee's log either — "tell them a request is
    # waiting" is the helpful-looking version of this leak.
    assert r.disclosures("leader", reader="leader") == []
    assert r.disclosures("parent", reader="parent") == []
    # The former guardian's authority over the log expired on the same birthday.
    assert r.disclosures("member", reader="parent") == []
    # The member's own record has it, and only theirs.
    assert [d["action"] for d in r.disclosures("member", reader="member")][-2:] \
        == ["grant.converted_at_majority"] * 2


def test_a_draft_guardian_grant_is_not_converted_into_a_question(aged_out):
    """Draft is what a machine produced, and asking about it is acting on it.

    Turning an inference into a consent question put to a member ratifies the
    inference, and it writes ``guardian_authority_ended`` into an append-only
    log for authority that never existed. Sealed rows only.
    """
    r = ConsentedRoster(Store(str(aged_out)), convert_on_open=False)
    r.store.record_grant("member", "director", Band.CRAFT,
                         GrantState.DRAFT.value, "inferred from roster",
                         granted_via="guardian")
    assert r.convert_everyone_at_majority().converted == \
        {"member": ["leader", "parent"]}
    assert r.connection.execute(
        "SELECT state, granted_via FROM grants WHERE grantee_id = 'director'"
    ).fetchone() == (GrantState.DRAFT.value, "guardian")
    assert not any("director" in d["detail"] for d in
                   r.disclosures("member", reader="member"))


def test_a_failed_conversion_leaves_guardian_access_expired(aged_out):
    """The failure direction. Never fall back to leaving the old grant live.

    Untouched is the safe state and this is why: the guardian's seal is still
    sitting in the table, unchanged, and it authorizes exactly nothing, because
    what ended the access was the birthday and not the conversion. A pass that
    could not finish costs the member an invitation, not their privacy.
    """
    r = ConsentedRoster(Store(str(aged_out)), convert_on_open=False)
    r.backend = _ChainCrashes(r.connection, disclosure_chain("member"))

    sweep = r.convert_everyone_at_majority()
    assert sweep.converted == {}
    assert sweep.unconvertible == ("member",)
    assert not r.connection.in_transaction, "a rewrite was left open uncommitted"

    assert r.connection.execute(
        "SELECT DISTINCT state, granted_via FROM grants WHERE subject_id = 'member'"
    ).fetchall() == [(GrantState.SEALED.value, "guardian")]
    assert r.count(PARENT) == 0
    assert r.count(LEADER) == 0
    assert _view(r, PARENT, "member")[:3] == ([], 0, False)


def test_a_failed_conversion_does_not_ride_in_on_the_next_success(aged_out):
    """One member's broken chain must not stop — or forge — anyone else's.

    Two things at once. A chain that cannot be extended is attacker-editable by
    anyone holding the file, so a sweep that propagated the first raise would
    let one tampered chain keep the whole corps out of the app. And the failed
    member's rewrite is still open on the shared connection when the next
    member's ledger row commits: leave it there and it lands as an access
    change with no record that it happened.
    """
    r = ConsentedRoster(Store(str(aged_out)), convert_on_open=False)
    r.register_member("second", birthdate(15), "registration form")
    r.register_guardian("parent", "second", "child", "registration form")
    r.seal("second", "leader", Band.CRAFT, "parent", "consent form")
    r.register_member("second", birthdate(18), "corrected registration")

    r.backend = _ChainCrashes(r.connection, disclosure_chain("member"))
    sweep = r.convert_everyone_at_majority()

    assert sweep.converted == {"second": ["leader"]}
    assert sweep.unconvertible == ("member",)
    assert r.connection.execute(
        "SELECT DISTINCT state, granted_via FROM grants WHERE subject_id = 'member'"
    ).fetchall() == [(GrantState.SEALED.value, "guardian")]
    r.backend = SqliteConsentBackend(r.connection)
    assert "grant.converted_at_majority" not in \
        [d["action"] for d in r.disclosures("member", reader="member")]


def test_a_corrected_birthdate_is_not_missed(tmp_path):
    """Why the work set is derived from the data and not from a bookmark.

    The obvious phrasing is "convert everyone who crossed majority since the
    roster was last opened". This member crossed it four years before the
    record was created: registered at fifteen from a form with a typo, and
    corrected two seasons later. Every window query answers nobody, and answers
    it silently and permanently. "A guardian seal on somebody who is not a
    minor" has no window in it and is true whenever it is asked.
    """
    db = tmp_path / "corps.db"
    r = ConsentedRoster(Store(str(db)))
    r.register_member("member", birthdate(15), "registration form")
    r.register_guardian("parent", "member", "child", "registration form")
    r.store.record_fact("member", Band.CRAFT, "rehearsal log", payload="x")
    r.seal("member", "leader", Band.CRAFT, "parent", "consent form")
    r.register_member("member", birthdate(22), "birthdate corrected from the form")
    r.connection.close()

    assert ConsentedRoster(Store(str(db))).opened.converted == \
        {"member": ["leader"]}
