"""Authentication: the gate that makes every other gate in this app mean something.

``Principal("delacroix")`` was an unverified string, so every guarantee the
resolver enforced was conditional on a claim nothing checked. These tests hold
the replacement, and the shape of them matters as much as the count:

**The boundary is the read, not the login.** So most of what follows attacks the
store with a principal that never went through ``authenticate`` — fabricated,
edited, borrowed from another process, expired. A test suite that only checked
``authenticate("x", "wrong")`` would be testing the door of a building with no
walls.

**Arming is one-way, and the downgrade is the interesting half.** The obvious
implementation requires proofs when credentials exist, which makes
``DELETE FROM credentials`` a privilege escalation. Two tests here exist only for
that, and one of them is the reason ``auth_policy`` is a separate table.

**What these tests cannot see, stated plainly.** Nothing here makes the file
confidential — every test below runs against a database that ``sqlite3`` would
open and read in full with no credential at all. Two tests assert the narrower
true thing: neither the secret nor the signing key is recoverable *from the
file*. Confidentiality against someone holding the disk is P3's stolen-device
gate and needs a cipher this project does not have.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts import Band, Store  # noqa: E402
from marching_arts.auth import (  # noqa: E402
    ITERATIONS,
    KDF,
    AuthError,
    Authenticator,
    unproven,
)
from marching_arts.policy import Principal  # noqa: E402

#: The schema's floor, so the suite is not 20 × 366ms of key stretching. The
#: production cost is asserted separately in
#: ``test_the_shipped_cost_is_the_one_that_ships``.
CHEAP = 100_000
SECRET = "correct horse battery staple"


@pytest.fixture()
def store():
    """An unarmed store — no credentials, resolves unproven principals."""
    s = Store(":memory:")
    s.auth = Authenticator(s.connection, iterations=CHEAP)
    s.record_fact("delacroix", int(Band.CRAFT), "rehearsal-log", payload="own row")
    s.record_fact("rivera", int(Band.CRAFT), "rehearsal-log", payload="squad row")
    s.record_grant("rivera", "delacroix", int(Band.CRAFT), "sealed",
                   "consent-form", sealed_by="rivera")
    # A row `delacroix` cannot see, and the fixture is wrong without it. The
    # roles tripwire below compares what a decorated principal sees against what
    # a plain one sees, and with every row already visible the comparison is
    # 2 == 2 no matter what a role does. Found by a mutation that granted
    # `admin` a blanket ALLOW: the tripwire did not fire, because there was
    # nothing left for the blanket to reveal.
    s.record_fact("hayes", int(Band.CRAFT), "rehearsal-log", payload="nobody's business")
    return s


@pytest.fixture()
def armed(store):
    """The same store with one credential enrolled, which arms it forever."""
    store.auth.enroll("delacroix", SECRET, "roster-import")
    return store


# ── the unarmed database still behaves exactly as it did ─────────────────────
#
# 161 tests were written before this module existed and every one of them passes
# an unproven principal. If arming were the default they would all fail, and the
# temptation would be to relax the gate rather than to gate arming.

def test_an_unarmed_database_resolves_an_unproven_principal(store):
    """Backwards compatibility, as an assertion rather than an accident."""
    assert store.auth.required is False
    assert store.count(Principal("delacroix")) == 2


def test_the_first_enrolment_arms_it_and_nothing_else_has_to(store):
    """No setup call, no config flag. Enrolling a credential is the switch,
    because a flag is a second copy of the truth and is wrong the first time
    somebody opens the file without setting it."""
    assert store.auth.required is False
    store.auth.enroll("delacroix", SECRET, "roster-import")
    assert store.auth.required is True


# ── the store refuses a principal nobody proved ──────────────────────────────

def test_an_unproven_principal_resolves_nothing_once_armed(armed):
    """The whole point. This is the call that used to work."""
    with pytest.raises(AuthError):
        armed.count(Principal("delacroix"))


def test_a_proven_principal_resolves_exactly_what_it_did_before(armed):
    """And authentication changes no authorization answer. A gate that also
    altered the result set would be two changes wearing one name."""
    who = armed.auth.authenticate("delacroix", SECRET)
    assert armed.count(who) == 2
    assert [f.payload for f in armed.visible(who)] == ["own row", "squad row"]


@pytest.mark.parametrize("read", ["count", "visible", "subjects"])
def test_every_read_path_is_gated_not_just_the_one_that_was_tested(armed, read):
    """``predicate`` is the choke point, so all three reads inherit the check —
    which is why the check is there and not in ``visible``. A fourth read added
    later gets it for free; a check bolted onto each caller would not."""
    with pytest.raises(AuthError):
        getattr(armed, read)(Principal("delacroix"))
    who = armed.auth.authenticate("delacroix", SECRET)
    assert getattr(armed, read)(who) is not None


def test_a_filtered_read_is_gated_too(armed):
    """A caller-supplied ``where`` must not be a way in. It is ANDed inside the
    predicate, and the proof is checked before either is compiled."""
    with pytest.raises(AuthError):
        armed.count(Principal("delacroix"), where="facts.band = 2")


# ── tampering with a proof that was real ─────────────────────────────────────
#
# `Principal` is a frozen dataclass and stays freely constructible on purpose:
# the identity, the roles and the expiry are all inside the signed message, so
# editing any of them breaks the signature. These are the edits worth trying.

def test_a_proof_does_not_transfer_to_another_person(armed):
    """The substitution attack, and the reason ``person_id`` is signed."""
    who = armed.auth.authenticate("delacroix", SECRET)
    with pytest.raises(AuthError):
        armed.count(replace(who, person_id="hayes"))


def test_roles_cannot_be_added_after_the_proof_was_issued(armed):
    """The escalation attack, and the reason ``roles`` is signed. Roles are not
    *verified* — there is no roles table — but they cannot be appended to a token
    that was minted without them."""
    who = armed.auth.authenticate("delacroix", SECRET)
    with pytest.raises(AuthError):
        armed.count(replace(who, roles=frozenset({"director"})))


def test_an_expiry_cannot_be_pushed_out(armed):
    """The expiry travels inside the token, so it has to be signed or it is a
    suggestion. Rewrite it and keep the digest: the digest no longer matches."""
    who = armed.auth.authenticate("delacroix", SECRET)
    _, _, digest = who.proof.rpartition(".")
    far_future = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
    with pytest.raises(AuthError):
        armed.count(replace(who, proof=f"{far_future}.{digest}"))


def test_an_expired_proof_is_refused(armed):
    """Short-lived by default, because a token with no expiry is a credential."""
    stale = armed.auth.authenticate("delacroix", SECRET, ttl_seconds=-1)
    with pytest.raises(AuthError):
        armed.count(stale)


def test_stripping_the_proof_is_not_a_way_round_it(armed):
    who = armed.auth.authenticate("delacroix", SECRET)
    with pytest.raises(AuthError):
        armed.count(unproven(who))


def test_a_malformed_proof_fails_as_a_bad_proof_and_not_as_a_crash(armed):
    """The expiry is parsed only *after* the signature verifies. Parsing first
    would turn a hostile token into a ``ValueError`` from ``fromisoformat`` —
    still a failure, but one that escapes ``AuthError`` and would sail past a
    caller catching the documented exception."""
    who = armed.auth.authenticate("delacroix", SECRET)
    for bad in ("", "no-dot", ".", "not-a-date.deadbeef", who.proof[:-1],
                "9999-13-45T99:99:99+00:00.deadbeef"):
        with pytest.raises(AuthError):
            armed.count(replace(who, proof=bad))


def test_a_proof_from_another_process_is_worthless(armed):
    """The signing key is per-:class:`Authenticator` and never written down, so a
    token minted anywhere else — another process, another database, a copy of
    this file on someone's laptop — verifies against a key that does not exist
    here. This is what buys the absence of a key at rest."""
    elsewhere = Authenticator(armed.connection, key=b"\x01" * 32, iterations=CHEAP)
    borrowed = elsewhere.issue("delacroix")
    with pytest.raises(AuthError):
        armed.count(borrowed)
    # and the reverse: this store's token means nothing to the other authenticator
    with pytest.raises(AuthError):
        elsewhere.verify(armed.auth.authenticate("delacroix", SECRET))


def test_a_token_does_not_survive_reopening_the_database(armed, tmp_path):
    """Recorded as behaviour rather than defended as a feature: reopening mints a
    new key, so yesterday's token is refused. Correct for an app with no server —
    there is no session to resume, only a file to reopen — and it is the price of
    keeping no key at rest."""
    path = str(tmp_path / "corps.db")
    first = Store(path)
    first.auth = Authenticator(first.connection, iterations=CHEAP)
    first.auth.enroll("delacroix", SECRET, "roster-import")
    token = first.auth.authenticate("delacroix", SECRET)
    first.connection.close()

    reopened = Store(path)
    assert reopened.auth.required is True
    with pytest.raises(AuthError):
        reopened.count(token)


# ── the credential itself ────────────────────────────────────────────────────

def test_the_wrong_secret_does_not_authenticate(armed):
    with pytest.raises(AuthError):
        armed.auth.authenticate("delacroix", "hunter2")


def test_an_unknown_person_and_a_wrong_secret_are_indistinguishable(armed):
    """No oracle. "No such person" versus "wrong secret" tells an attacker which
    half to keep guessing, which halves the work for free."""
    with pytest.raises(AuthError) as unknown:
        armed.auth.authenticate("nobody-here", SECRET)
    with pytest.raises(AuthError) as wrong:
        armed.auth.authenticate("delacroix", "hunter2")
    assert str(unknown.value) == str(wrong.value)


def test_a_forged_proof_and_an_expired_one_are_indistinguishable(armed):
    """The oracle that matters more. "Expired" tells a forger their forgery was
    structurally sound and only needs a fresher timestamp."""
    who = armed.auth.authenticate("delacroix", SECRET)
    with pytest.raises(AuthError) as expired:
        armed.auth.verify(armed.auth.authenticate("delacroix", SECRET, ttl_seconds=-1))
    with pytest.raises(AuthError) as forged:
        armed.auth.verify(replace(who, person_id="hayes"))
    assert str(expired.value) == str(forged.value)


def test_a_blank_person_or_secret_is_refused_at_enrolment(store):
    for person, secret in (("", SECRET), ("   ", SECRET), ("delacroix", "")):
        with pytest.raises(AuthError):
            store.auth.enroll(person, secret, "roster-import")
    assert store.auth.required is False       # and a refused enrolment does not arm


def test_the_shipped_cost_is_the_one_that_ships():
    """The constant, and the schema floor under it. These tests run at the floor
    so the suite is not thirty seconds of key stretching, which is exactly the
    shape of change that quietly ships a weak default."""
    assert ITERATIONS == 600_000
    assert KDF == "pbkdf2_hmac_sha256"
    s = Store(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        s.connection.execute(
            "INSERT INTO credentials(person_id, kdf, iterations, salt, verifier,"
            " source) VALUES ('cheap', ?, 1000, ?, ?, 'test')",
            (KDF, b"x" * 16, b"y" * 32))


def test_the_cost_is_stored_per_row_so_it_can_be_raised(store):
    """A credential enrolled at yesterday's cost must keep working after the
    constant goes up, or raising it locks out the whole corps."""
    store.auth.enroll("delacroix", SECRET, "roster-import")
    assert store.connection.execute(
        "SELECT iterations FROM credentials WHERE person_id = 'delacroix'"
    ).fetchone()[0] == CHEAP
    expensive = Authenticator(store.connection, key=store.auth._key,
                              iterations=CHEAP * 2)
    assert expensive.authenticate("delacroix", SECRET) is not None    # old row still verifies
    expensive.enroll("rivera", SECRET, "roster-import")
    assert store.connection.execute(
        "SELECT iterations FROM credentials WHERE person_id = 'rivera'"
    ).fetchone()[0] == CHEAP * 2


def test_an_unknown_kdf_does_not_authenticate_anybody(armed):
    """A row claiming a derivation this build does not implement is corrupt or
    forged. Either way it is not a reason to guess — and the CHECK means the only
    way to get one there is to change the schema, which is the case this covers."""
    armed.connection.execute(
        "UPDATE credentials SET kdf = 'pbkdf2_hmac_sha256' WHERE 0")   # no-op, shape only
    with pytest.raises(sqlite3.IntegrityError):
        armed.connection.execute("UPDATE credentials SET kdf = 'rot13'")


# ── enrolment is not the bypass ──────────────────────────────────────────────

def test_a_credential_cannot_be_silently_replaced(armed):
    """The attack enrolment invites: a section leader with the laptop re-enrols a
    member and reads their record. Replacing an existing credential requires
    proving the old one."""
    with pytest.raises(AuthError):
        armed.auth.enroll("delacroix", "my-secret-now", "helpful-leader")
    assert armed.auth.authenticate("delacroix", SECRET) is not None


def test_rotation_needs_the_old_secret_and_retires_it(armed):
    with pytest.raises(AuthError):
        armed.auth.enroll("delacroix", "new", "self", rotating_from="hunter2")
    armed.auth.enroll("delacroix", "new secret", "self", rotating_from=SECRET)
    assert armed.auth.authenticate("delacroix", "new secret") is not None
    with pytest.raises(AuthError):
        armed.auth.authenticate("delacroix", SECRET)


def test_a_second_credential_cannot_sit_beside_the_first(armed):
    """What the schema can enforce where the module's rule cannot: ``person_id``
    is a primary key, so an INSERT reaching past this module still cannot give
    one person two credentials. Recorded because the rotation rule above is
    module-level only — weaker than every rule in migration 002, the same
    asymmetry migration 004 records about its partition check."""
    with pytest.raises(sqlite3.IntegrityError):
        armed.connection.execute(
            "INSERT INTO credentials(person_id, kdf, iterations, salt, verifier,"
            " source) VALUES ('delacroix', ?, 600000, ?, ?, 'forged')",
            (KDF, b"x" * 16, b"y" * 32))


# ── the latch ────────────────────────────────────────────────────────────────

def test_authentication_cannot_be_turned_off(armed):
    with pytest.raises(sqlite3.IntegrityError):
        armed.connection.execute("UPDATE auth_policy SET required = 0")
    assert armed.auth.required is True


def test_the_latch_row_cannot_be_deleted_either(armed):
    """Deleting the latch is disarming it by another name."""
    with pytest.raises(sqlite3.IntegrityError):
        armed.connection.execute("DELETE FROM auth_policy")
    assert armed.auth.required is True


def test_deleting_every_credential_locks_everyone_out(armed):
    """The downgrade attack, and the reason arming is its own table.

    Derive "authentication required" from the presence of credentials and
    ``DELETE FROM credentials`` becomes a privilege escalation: the gate opens
    for unproven principals. Here the same delete locks the corps out of their
    own database, which is the correct direction to fail. The recovery is a
    restore, and migration 006 says so.
    """
    armed.connection.execute("DELETE FROM credentials")
    armed.connection.commit()
    assert armed.auth.required is True
    with pytest.raises(AuthError):
        armed.count(Principal("delacroix"))                 # unproven: still refused
    with pytest.raises(AuthError):
        armed.auth.authenticate("delacroix", SECRET)         # and nobody can get in


# ── nothing secret is at rest ────────────────────────────────────────────────

def _file_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def test_the_secret_is_not_in_the_file(tmp_path):
    """The narrow true claim, since the broad one is false: the file is fully
    readable by anyone holding it, and what they do not get is the password."""
    path = str(tmp_path / "corps.db")
    s = Store(path)
    s.auth = Authenticator(s.connection, iterations=CHEAP)
    s.auth.enroll("delacroix", SECRET, "roster-import")
    s.connection.commit()
    assert SECRET.encode() not in _file_bytes(path)


def test_the_signing_key_is_not_in_the_file(tmp_path):
    """No key at rest, asserted against the bytes rather than against the schema.

    A ``secrets`` table would be the obvious design and this is why there isn't
    one: a signing key beside the data it authenticates is a key an attacker with
    the file can use to mint any principal they like.
    """
    path = str(tmp_path / "corps.db")
    s = Store(path)
    key = b"\xab" * 32
    s.auth = Authenticator(s.connection, key=key, iterations=CHEAP)
    s.auth.enroll("delacroix", SECRET, "roster-import")
    s.auth.authenticate("delacroix", SECRET)
    s.connection.commit()
    blob = _file_bytes(path)
    assert key not in blob
    assert key.hex().encode() not in blob
    assert s.connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%secret%'"
        " OR name LIKE '%signing%'").fetchone()[0] == 0


def test_the_file_is_still_fully_readable_and_this_module_does_not_claim_otherwise(tmp_path):
    """The honest limit, as a test so it cannot quietly stop being said.

    Authentication gates the resolver. It does not gate the file. If this ever
    becomes false it will be because someone added encryption at rest, and this
    test failing is the right way to find out — it is the P3 stolen-device gate
    arriving, not a regression.
    """
    path = str(tmp_path / "corps.db")
    s = Store(path)
    s.auth = Authenticator(s.connection, iterations=CHEAP)
    s.auth.enroll("delacroix", SECRET, "roster-import")
    s.record_fact("rivera", int(Band.HEALTH), "clinic", payload="the diagnosis")
    s.connection.commit()

    outsider = sqlite3.connect(path)                 # no credential, no proof
    assert outsider.execute(
        "SELECT payload FROM facts WHERE band = ?", (int(Band.HEALTH),)
    ).fetchall() == [("the diagnosis",)]


# ── roles are still a claim, and this is the tripwire ────────────────────────

def test_a_role_still_buys_nothing_in_the_default_policy(armed):
    """The tripwire for the one thing this module does not fix.

    ``roles`` are asked for at authenticate time and checked against nothing —
    there is no roles table. Signing them stops them being *added* to a token,
    which is the tamper case; it does not make them true. That is survivable only
    while the default policy grants nothing on the basis of a role.

    So: a principal holding every role this app mentions sees exactly what a
    principal holding none sees. **The day that stops being true, this test fails
    and the fix is a roles table, not a change to this assertion.**
    """
    plain = armed.auth.authenticate("delacroix", SECRET)
    decorated = armed.auth.authenticate(
        "delacroix", SECRET,
        roles=frozenset({"director", "caption_head", "program_coordinator",
                         "safeguarding_lead", "admin"}))
    assert armed.count(decorated) == armed.count(plain)
    assert ([f.id for f in armed.visible(decorated)]
            == [f.id for f in armed.visible(plain)])
    assert armed.subjects(decorated) == armed.subjects(plain)


def test_issue_is_the_one_door_that_hands_out_authority(armed):
    """Named to be conspicuous, and tested so its behaviour is on the record: it
    mints a valid proof with no secret. A review that finds a call to it outside
    a host's login path has found the bug, and that is the only protection it
    has — which is why it is not called anywhere in this package."""
    who = armed.auth.issue("hayes")
    armed.auth.verify(who)                                   # valid, no secret given
    package = Path(__file__).resolve().parents[1] / "marching_arts"
    callers = [p.name for p in package.glob("*.py")
               if ".issue(" in p.read_text() and p.name != "auth.py"]
    assert callers == [], f"issue() called inside the package by {callers}"


# ── it does not break P2 ─────────────────────────────────────────────────────

def test_opening_a_roster_on_an_armed_database_still_converts(tmp_path):
    """The majority sweep runs on open, takes no principal, and holds the
    connection — it is an operator action, not a read. Arming must not stop a
    corps from opening their own file, which is what would happen if the sweep
    had been routed through the resolver.
    """
    from marching_arts.consent import ConsentedRoster

    path = str(tmp_path / "corps.db")
    roster = ConsentedRoster(Store(path))
    today = datetime.now(timezone.utc).date()
    roster.register_member("kid", today.replace(year=today.year - 17).isoformat(), "t")
    roster.register_guardian("parent", "kid", "child", "t")
    roster.seal("kid", "leader", int(Band.CRAFT), "parent", "t")
    roster.store.auth = Authenticator(roster.connection, iterations=CHEAP)
    roster.store.auth.enroll("kid", SECRET, "roster-import")
    roster.connection.execute(
        "UPDATE people SET birthdate = ? WHERE person_id = 'kid'",
        (today.replace(year=today.year - 19).isoformat(),))
    roster.connection.commit()
    roster.connection.close()

    reopened = ConsentedRoster(Store(path))
    assert reopened.opened.converted == {"kid": ["leader"]}
    assert reopened.store.auth.required is True


def test_a_rosters_reads_are_gated_like_the_stores(tmp_path):
    """``ConsentedRoster`` forwards ``visible``/``count``/``subjects`` to the
    store so a caller never reaches past it to the connection. That forwarding
    must carry the proof requirement with it."""
    from marching_arts.consent import ConsentedRoster

    roster = ConsentedRoster(Store(":memory:"))
    roster.store.auth = Authenticator(roster.connection, iterations=CHEAP)
    roster.store.record_fact("delacroix", int(Band.CRAFT), "t", payload="own")
    roster.store.auth.enroll("delacroix", SECRET, "roster-import")
    with pytest.raises(AuthError):
        roster.count(Principal("delacroix"))
    who = roster.store.auth.authenticate("delacroix", SECRET)
    assert roster.count(who) == 1
