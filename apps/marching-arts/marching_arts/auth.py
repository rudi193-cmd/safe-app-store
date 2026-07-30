"""Who is asking, and the proof that they are.

Until this module existed, ``Principal("delacroix")`` was an unverified string.
The predicate compiled from it was correct, per-record and mutation-tested — and
a perfect predicate over an unauthenticated principal is theatre, because
anything that can construct a ``Principal`` can construct any ``Principal``.
Every guarantee in this app was conditional on a claim nothing checked.

**The boundary is the store, not the front door.** A login function that returns
a plain dataclass closes the honest-mistake case and nothing else: the next
feature to need a principal constructs one inline and it works. So a `Principal`
carries a `proof` — an HMAC over the identity it asserts — and
:meth:`Store.predicate` verifies it on every read. A caller that fabricates a
principal, or reaches past :meth:`Authenticator.authenticate` entirely, produces a
token the store refuses. That is the same shape as the rest of the schema: the
module can be bypassed, the gate cannot.

WHAT THIS IS NOT, and the distinction is the whole honesty of the module.

**It is not confidentiality.** Anyone holding the file opens it with `sqlite3`
and reads every row, with no credential and no proof. This gates the
*application's resolver*; it does not gate the *file*. Encryption at rest is a
different mechanism and it needs a cipher that exists nowhere in reach — see
P3's stolen-device gate in docs/BUILD_PLAN.md. Read this module as a seatbelt
against the app authorizing a claim nobody proved, never as a lock against an
adversary with the disk.

**The signing key is never written down.** It is generated per
:class:`Authenticator`, held in memory, and lost when the process exits. That is
deliberate and it is stronger than storing it: there is no key at rest to steal,
and a token from one process is meaningless in another. It also means tokens do
not survive a restart, which is correct for an app with no server — there is no
session to resume, only a database to reopen.

**Roles are still an unverified claim, and one test pins that.** A caller asks
for roles at authenticate time and there is no roles table to check them
against. Binding them into the proof stops them being *added afterwards*, which
is the tamper case; it does not make them true. That is survivable only because
the default :class:`~marching_arts.policy.Policy` grants nothing on the basis of
a role — `test_a_role_still_buys_nothing_in_the_default_policy` fails the day
that stops being true, which is the day this needs a roles table.

Stdlib only: `hashlib`, `hmac`, `secrets`, `datetime`. Nothing here opens a
socket and `tests/test_no_egress.py` walks the AST to say so.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .policy import Principal

#: The key derivation, named in the row rather than assumed by the reader.
#: Stored per credential so the cost can be raised for new enrolments without
#: invalidating the ones already on file — the same reason `band` and `source`
#: are on the fact table from migration 001 rather than retrofitted.
KDF = "pbkdf2_hmac_sha256"

#: OWASP's floor for PBKDF2-HMAC-SHA256 at time of writing. A *stored* number,
#: so raising this constant does not orphan an existing corps's credentials.
ITERATIONS = 600_000

#: PBKDF2 and not scrypt, and the reason is portability rather than taste.
#: `hashlib.scrypt` is in the Python standard library and is **not** in
#: WebCrypto, and the browser half of this app has to agree with this one by
#: differential. PBKDF2-HMAC-SHA256 is in both. Choosing the stronger primitive
#: here would have meant two different KDFs across two implementations that are
#: required to produce identical answers.
_SALT_BYTES = 16
_KEY_BYTES = 32

#: How long a proof is good for. Short, because it costs nothing to re-derive
#: on a local machine and a token with no expiry is a credential.
DEFAULT_TTL_SECONDS = 3600

#: Field separator for the signed message. Length-prefixed rather than
#: delimited, so a role containing the separator cannot shift the boundaries and
#: make two different identities sign the same bytes.
_DOMAIN = b"marching_arts/auth/v1"


class AuthError(Exception):
    """Authentication failed, or a proof did not verify.

    **One exception, one message, for every cause.** Wrong secret, unknown
    person, absent proof, forged proof, expired proof and wrong-process proof all
    raise this and say the same thing. Distinguishing them would build an
    oracle: "no such person" versus "wrong secret" tells an attacker which half
    to keep guessing, and "expired" versus "forged" tells them their forgery was
    structurally sound.
    """


def _signed_message(person_id: str, roles: "frozenset[str]", expires_at: str) -> bytes:
    """The exact bytes a proof covers.

    Length-prefixed, so no combination of identity, roles and expiry can be
    re-cut into a different combination that signs the same message. Delimiting
    with a separator instead would let a person_id of ``"a|director"`` collide
    with a person ``"a"`` holding the ``director`` role.
    """
    parts = [_DOMAIN, person_id.encode("utf-8"), expires_at.encode("utf-8")]
    parts.extend(role.encode("utf-8") for role in sorted(roles))
    out = bytearray()
    for part in parts:
        out.extend(len(part).to_bytes(4, "big"))
        out.extend(part)
    return bytes(out)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Authenticator:
    """Credential enrolment, authentication, and proof verification.

    Owns two things: the credential rows on the store's own connection (so a
    corps that backed up one file backed up its logins with it), and a signing
    key that exists only in this process's memory.

    Normally reached as :attr:`marching_arts.Store.auth` rather than constructed
    directly — the store makes one on the connection it already holds, which
    removes the ordering problem of having to build an authenticator before the
    store it verifies for.
    """

    def __init__(self, conn, *, key: "bytes | None" = None,
                 iterations: int = ITERATIONS) -> None:
        self._conn = conn
        # Random per process, never persisted. `key` is injectable for the
        # tests that need two authenticators to disagree, and for the ones that
        # need two to agree; there is no path that writes it anywhere.
        self._key = key if key is not None else secrets.token_bytes(32)
        self._iterations = int(iterations)

    # ── the armed / unarmed state, derived from the data ────────────────────
    #
    # Whether proofs are required is NOT a constructor flag. A flag is a second
    # copy of the truth and it is wrong the first time somebody opens the file
    # without setting it — the same objection migration 002 raised against an
    # `is_minor` column. It is derived from a row that the first enrolment
    # writes and that nothing can unwrite.
    #
    # THE DOWNGRADE IS THE INTERESTING HALF. The obvious phrasing is "require
    # proofs if any credential exists", and it is wrong: deleting the credential
    # rows would then re-open the database to unproven principals, which makes
    # `DELETE FROM credentials` a privilege escalation. So arming is recorded
    # separately and is one-way. Delete every credential from an armed database
    # and nobody can authenticate at all — which is the correct direction to
    # fail, and `test_deleting_every_credential_locks_everyone_out` is the gate.

    @property
    def required(self) -> bool:
        """True once this database has ever had a credential enrolled."""
        row = self._conn.execute(
            "SELECT required FROM auth_policy WHERE id = 1").fetchone()
        return bool(row and row[0])

    def _arm(self) -> None:
        self._conn.execute(
            "INSERT INTO auth_policy(id, required) VALUES (1, 1)"
            " ON CONFLICT(id) DO UPDATE SET required = 1")

    # ── enrolment ───────────────────────────────────────────────────────────
    def enroll(self, person_id: str, secret: str, source: str, *,
               rotating_from: "str | None" = None) -> None:
        """Give a person a credential. Arms the database on the first one.

        **The first enrolment is unauthenticated, and it has to be.** There is
        nobody to authenticate to yet; the person holding the file is the
        operator, exactly as they are when they open it. What is *not* allowed is
        the interesting case: **replacing a credential that already exists
        requires proving the old one**, via ``rotating_from``. Without that rule
        a section leader with the laptop re-enrols a member and reads their
        record, and enrolment would be the bypass rather than the gate.

        NOT ENFORCED BY A TRIGGER, and the gap is recorded rather than papered
        over: verifying a PBKDF2 secret is not something stock SQLite can do
        inside a ``BEFORE UPDATE``. So this rule holds against callers of this
        module and not against a writer who reaches past it to SQL — strictly
        weaker than every rule in migration 002, and the same asymmetry
        migration 004 records about its partition check. The schema does what it
        can: `credentials.person_id` is a primary key, so a *second* credential
        for one person cannot be inserted alongside the first, and an attacker
        rewriting the verifier by hand still cannot read the old secret.
        """
        if not (person_id and person_id.strip()):
            raise AuthError("a credential needs a person")
        if not secret:
            raise AuthError("a credential needs a secret")

        existing = self._conn.execute(
            "SELECT 1 FROM credentials WHERE person_id = ?", (person_id,)
        ).fetchone()
        if existing:
            if rotating_from is None:
                raise AuthError(
                    "this person already has a credential: rotate it by proving"
                    " the old one, do not replace it")
            self._check(person_id, rotating_from)

        salt = secrets.token_bytes(_SALT_BYTES)
        verifier = hashlib.pbkdf2_hmac(
            "sha256", secret.encode("utf-8"), salt, self._iterations, _KEY_BYTES)
        self._conn.execute(
            "INSERT INTO credentials(person_id, kdf, iterations, salt, verifier,"
            " source) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(person_id) DO UPDATE SET"
            "   kdf = excluded.kdf, iterations = excluded.iterations,"
            "   salt = excluded.salt, verifier = excluded.verifier,"
            "   source = excluded.source",
            (person_id, KDF, self._iterations, salt, verifier, source))
        self._arm()
        self._conn.commit()

    # ── authentication ──────────────────────────────────────────────────────
    def _check(self, person_id: str, secret: str) -> None:
        """Raise unless ``secret`` matches the stored verifier. No return value.

        A boolean return would invite ``if backend.check(...)`` and the one
        caller who forgets the ``not``. Raising has one correct usage.
        """
        row = self._conn.execute(
            "SELECT kdf, iterations, salt, verifier FROM credentials"
            " WHERE person_id = ?", (person_id,)).fetchone()
        if row is None:
            raise AuthError("authentication failed")
        kdf, iterations, salt, verifier = row
        if kdf != KDF:
            # An unknown KDF is not a reason to guess. A future migration adds a
            # second one by name; until then a row claiming one is corrupt or
            # forged, and either way it does not authenticate anybody.
            raise AuthError("authentication failed")
        candidate = hashlib.pbkdf2_hmac(
            "sha256", (secret or "").encode("utf-8"), salt, int(iterations),
            len(verifier))
        # compare_digest, not `==`. The comparison is over a derived key rather
        # than the secret, so a timing leak here is not catastrophic; it is also
        # free to do correctly and there is no version of this line worth
        # arguing about.
        if not hmac.compare_digest(candidate, verifier):
            raise AuthError("authentication failed")

    def authenticate(self, person_id: str, secret: str, *,
                     roles: "frozenset[str] | set | None" = None,
                     ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Principal:
        """Prove a secret and get a principal the store will accept.

        The returned principal carries a proof over its identity, its roles and
        its expiry. Change any of the three afterwards — including with
        ``dataclasses.replace`` — and the proof stops matching, because all three
        are inside the signed message.

        ``roles`` are asked for, not checked: there is no roles table. See the
        module docstring; the default policy grants nothing on a role and a test
        holds that line.
        """
        self._check(person_id, secret)
        return self.issue(person_id, roles=roles, ttl_seconds=ttl_seconds)

    def issue(self, person_id: str, *,
              roles: "frozenset[str] | set | None" = None,
              ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Principal:
        """Mint a proven principal **without** checking a secret.

        Separate from :meth:`authenticate` and named to be conspicuous. It exists
        for a host that authenticated by some other means it trusts more than a
        password — a platform keychain, a hardware token — and for the tests. It
        is the one function in this module that will hand out authority on
        request, so a review that finds a call to it outside a host's login path
        has found the bug.
        """
        roles = frozenset(roles or ())
        expires_at = (_now() + timedelta(seconds=int(ttl_seconds))).isoformat()
        message = _signed_message(person_id, roles, expires_at)
        proof = f"{expires_at}.{hmac.new(self._key, message, hashlib.sha256).hexdigest()}"
        return Principal(person_id, roles, proof=proof)

    # ── verification: what the store calls on every read ────────────────────
    def verify(self, principal: Principal) -> None:
        """Raise :class:`AuthError` unless this principal's proof is good.

        Called by :meth:`Store.predicate`, which every read goes through, so
        there is no second path — the same property the resolver itself has.
        Returns ``None``; see :meth:`_check` for why this is not a boolean.
        """
        proof = getattr(principal, "proof", None)
        if not proof or "." not in proof:
            raise AuthError("this principal carries no proof")
        expires_at, _, digest = proof.rpartition(".")

        expected = hmac.new(
            self._key,
            _signed_message(principal.person_id, principal.roles, expires_at),
            hashlib.sha256,
        ).hexdigest()
        # Verify the signature BEFORE reading the expiry as a date. The expiry
        # arrives inside the token, so trusting it enough to parse it before
        # checking who wrote it is backwards; a malformed one must fail as a bad
        # proof and not as a crash in `fromisoformat`.
        if not hmac.compare_digest(expected, digest):
            raise AuthError("this principal's proof does not verify")
        try:
            deadline = datetime.fromisoformat(expires_at)
        except ValueError:
            raise AuthError("this principal's proof does not verify") from None
        if deadline.tzinfo is None or deadline <= _now():
            raise AuthError("this principal's proof does not verify")


def unproven(principal: Principal) -> Principal:
    """Strip the proof from a principal. For tests, and for nothing else.

    Exported so a test can express "the same principal, without its proof"
    without reaching into the dataclass, and named so that a call to it in
    application code reads as the mistake it is.
    """
    return replace(principal, proof=None)


__all__ = [
    "AuthError",
    "Authenticator",
    "DEFAULT_TTL_SECONDS",
    "ITERATIONS",
    "KDF",
    "unproven",
]
