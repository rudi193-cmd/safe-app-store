"""P2's binding: ``subject-consent`` landed on the store's own SQLite connection.

The library decides *what consent is*. This module decides *where it lives* and
*who is allowed to ask* — and it puts both on the connection the domain data is
already on, so a corps backing up one file has backed up the grants, the
hash-chained disclosure log and the roster together, or has backed up none of
them. A consent record that can be restored out of step with the data it governs
is a consent record that will eventually authorise something nobody agreed to.

Three things are worth reading before changing anything here.

**The chain logic is not reimplemented.** Row hashing, prev-links and the head
anchor that makes tail truncation detectable all live once, in
``libs/subject-consent`` — the canonical copy. UTETY has a vendored fork and it
is a *worked example*, not a source: :class:`SqliteConsentBackend` takes its
atomicity lesson (append the row and write the anchor inside ONE transaction, or
a crash between the two wedges the chain) and nothing else.

**The count anchor is the point.** A plain hash chain detects an edited row and a
deleted middle row. It does not detect somebody deleting the *newest* rows, and
the newest rows are precisely the ones an attacker wants gone — the revocation,
the disclosure that names them. The anchor carries ``count`` as well as ``hash``,
so a truncated chain still links perfectly and still fails verification.

**Consent is never obtained by the person who benefits from it.** A section
leader asking their own squad for access is coercion with extra steps: the
asking is the pressure, and no amount of "it's voluntary" changes who signs the
rehearsal block. So the beneficiary cannot be the requester and cannot be the
signer, and that is a trigger in migration 002 rather than a rule in this file —
this module can be bypassed, the database cannot.

Stdlib plus the consent core, which is itself stdlib-only. Nothing here opens a
socket and ``tests/test_no_egress.py`` walks the AST to say so. This module is
deliberately *not* imported by ``marching_arts/__init__.py``: the core stays
importable with nothing on the path but the standard library, which is what
``test_import_is_stdlib_only`` checks, and what makes the browser port a port.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from .policy import GrantState, GrantVia, Principal
from .store import Store

# ── the canonical core, resolved ──────────────────────────────────────────────
# Prefer an installed subject_consent; fall back to the in-repo canonical source
# tree. Explicitly NOT UTETY's vendored fork — a second copy of a consent
# primitive is how two consumers end up disagreeing about what "revoked" means,
# and _refuse_a_fork() below turns that from a convention into a check.

_CANONICAL_SRC = (
    Path(__file__).resolve().parents[3] / "libs" / "subject-consent" / "src"
)

try:  # pragma: no cover - exercised by whichever branch this environment takes
    import subject_consent as _sc
except ImportError:  # pragma: no cover
    if _CANONICAL_SRC.is_dir():
        sys.path.insert(0, str(_CANONICAL_SRC))
    import subject_consent as _sc

from subject_consent import (  # noqa: E402
    RELATIONS,
    SCOPES,
    ChainTamperError,
    DeidentificationError,
    SubjectConsentError,
    deidentify,
)

#: The chain names the core addresses. Re-exported so the tamper tests can reach
#: the rows without duplicating the core's naming scheme.
CONSENT_CHAIN = _sc.core._CONSENT_CHAIN


def disclosure_chain(subject_id: str) -> str:
    """The chain name for one subject's disclosure log (the subject id is
    hashed by the core, so an opaque id never becomes a table key)."""
    return _sc.core._disclosure_chain(subject_id)


def consent_core_path() -> Path:
    """Where the consent core was loaded from. Used by the test that refuses a
    fork; useful in an incident when the question is *which copy is running*."""
    return Path(_sc.core.__file__).resolve()


# ── the backend: chains on the store's connection ─────────────────────────────

class SqliteConsentBackend:
    """A ``subject_consent.Backend`` over the store's own connection.

    Four methods, mapping each logical chain (``"consent"``, or
    ``"disclosure/<hash>"``) onto ``consent_chain`` rows keyed by ``(chain, seq)``
    and one ``consent_anchor`` row. The core supplies the chain names and rows
    that are already hashed and linked; this class only stores them.

    **Atomicity.** ``append_row`` does not commit and ``write_anchor`` does — so
    the row and the anchor that names it land together or not at all. The core
    calls the two in that order inside a single ``_append``, and this backend
    depends on exactly that contract. The file backend's two independent writes
    fail closed on a crash between them, but they fail closed *permanently*: the
    chain is then unextendable. One transaction is the difference between a
    crash you recover from and a consent log you have to rebuild by hand.

    That commit also closes any work the caller left open on the same connection
    — which is how :meth:`ConsentedRoster.revoke` gets a silent revocation and
    its ledger entry into one transaction.
    """

    def __init__(self, conn: "sqlite3.Connection | str" = ":memory:") -> None:
        self._conn = sqlite3.connect(conn) if isinstance(conn, str) else conn
        # Idempotent, and normally a no-op: migration 002 already made these.
        # Present so the backend also works against a bare connection.
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS consent_chain ("
            "  chain TEXT NOT NULL, seq INTEGER NOT NULL, row TEXT NOT NULL,"
            "  PRIMARY KEY (chain, seq));"
            "CREATE TABLE IF NOT EXISTS consent_anchor ("
            "  chain TEXT PRIMARY KEY, hash TEXT NOT NULL, count INTEGER NOT NULL);"
        )
        self._conn.commit()

    # ── Backend protocol ────────────────────────────────────────────────────
    def read_rows(self, chain: str) -> "list[dict] | None":
        rows = [
            json.loads(r[0]) for r in self._conn.execute(
                "SELECT row FROM consent_chain WHERE chain = ? ORDER BY seq",
                (chain,),
            )
        ]
        if rows:
            return rows
        # None means "no such chain", which the core treats differently from an
        # empty one — absent is not tampered, but emptied is. A backend that
        # returns None for both hands an attacker the complete truncation: delete
        # every row and the log reads as one that never existed.
        #
        # This backend can tell the two apart, and the file backend cannot,
        # because the anchor lives in the same store and survives the delete. An
        # orphaned anchor is positive evidence that rows were here. So: [] when
        # an anchor remains, which `_verify` rejects; None only when there is
        # genuinely nothing.
        return [] if self.read_anchor(chain) is not None else None

    def append_row(self, chain: str, row: dict) -> None:
        nxt = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM consent_chain WHERE chain = ?",
            (chain,),
        ).fetchone()[0]
        self._conn.execute(
            "INSERT INTO consent_chain(chain, seq, row) VALUES (?, ?, ?)",
            (chain, nxt, json.dumps(row, sort_keys=True)),
        )  # no commit: write_anchor commits the pair

    def read_anchor(self, chain: str) -> "dict | None":
        row = self._conn.execute(
            "SELECT hash, count FROM consent_anchor WHERE chain = ?", (chain,)
        ).fetchone()
        return {"hash": row[0], "count": row[1]} if row else None

    def write_anchor(self, chain: str, anchor: dict) -> None:
        self._conn.execute(
            "INSERT INTO consent_anchor(chain, hash, count) VALUES (?, ?, ?)"
            " ON CONFLICT(chain) DO UPDATE SET"
            "   hash = excluded.hash, count = excluded.count",
            (chain, anchor["hash"], int(anchor["count"])),
        )
        self._conn.commit()  # commits this write AND the preceding append_row


# ── the surface ───────────────────────────────────────────────────────────────

class ConsentedRoster:
    """P2: identity, roles and consent over a P1 :class:`~marching_arts.Store`.

    Two consent layers, deliberately not merged, because they answer different
    questions and a single "consented?" boolean would have to answer both wrong:

    * **band grants** (``grants``, from P1) — *who may see which row, to what
      band*. Per record, because every leader is also a member. Compiled into
      the one SQL predicate every read goes through.
    * **use-class consent** (subject-consent's ``SCOPES``) — *whether this
      subject's data may be put to this kind of use at all*, hash-chained and
      tamper-evident. ``person_inference`` is the one that matters most here:
      a coordinate is not a diagnosis, and the platform may hold the first
      without ever being allowed to derive the second.

    Every mutation on either layer appends to the subject's disclosure chain, in
    the same transaction as the mutation itself. That chain is where history
    lives — the grants table is a resolver index and is kept residue-free on
    purpose, so revocation can be silent.
    """

    def __init__(self, store: "Store | None" = None) -> None:
        self.store = store if store is not None else Store(":memory:")
        self.backend = SqliteConsentBackend(self.store.connection)

    # ── identity ────────────────────────────────────────────────────────────
    def register_member(self, person_id: str, birthdate: str, source: str) -> None:
        """Put a person on the roster with a birthdate. ``birthdate`` is ISO
        ``YYYY-MM-DD``; SQLite rejects anything that is not a real date."""
        self.store.record_person(person_id, birthdate, source)

    def register_guardian(self, guardian_id: str, subject_id: str,
                          relation: str, source: str) -> None:
        """Record who may consent for a minor.

        ``relation`` comes from subject-consent's ``RELATIONS`` minus ``self``:
        a guardianship over yourself is not a guardianship, and the schema says
        so with ``CHECK (guardian_id <> subject_id)``.
        """
        if relation not in RELATIONS or relation == "self":
            raise SubjectConsentError(f"unknown guardian relation: {relation!r}")
        self.store.record_guardianship(guardian_id, subject_id, relation, source)

    def is_minor(self, person_id: str) -> bool:
        return self.store.is_minor(person_id)

    def guardians_of(self, subject_id: str) -> "list[str]":
        return self.store.guardians_of(subject_id)

    # ── band grants ─────────────────────────────────────────────────────────
    def request(self, subject_id: str, grantee_id: str, band: int,
                requested_by: str, source: str) -> str:
        """Ask for access. Records a ``pending`` grant, which authorizes nothing.

        ``requested_by`` may not be ``grantee_id``. The refusal is a trigger, so
        it holds for every writer including the ones that never call this
        method; what this method adds is that the *asking* is on the record
        before the answer is, which is what lets anyone check afterwards whether
        the ask came from the person who wanted the access.
        """
        self.store.record_grant(
            subject_id, grantee_id, band, GrantState.PENDING.value, source,
            requested_by=requested_by, commit=False,
        )
        return self._disclose(
            subject_id, "grant.requested",
            f"band={int(band)} grantee={grantee_id} by={requested_by}",
        )

    def seal(self, subject_id: str, grantee_id: str, band: int,
             signed_by: str, source: str,
             requested_by: "str | None" = None) -> str:
        """Seal a grant — the only state that authorizes anything.

        ``granted_via`` is derived, never passed in: a subject the roster knows
        to be under the age of majority gets a *guardian* grant, and everyone
        else gets a *member* grant. A caller cannot declare a minor's consent to
        be their own, and cannot declare an adult's consent to be a guardian's.

        The guardian branch buys nothing permanent. The resolver honours a
        guardian grant only while the subject is still a minor, so this seal
        expires on a birthday with nothing scheduled — see
        :meth:`convert_at_majority` for the part that then asks the member.
        """
        via = GrantVia.GUARDIAN if self.is_minor(subject_id) else GrantVia.MEMBER
        try:
            self.store.record_grant(
                subject_id, grantee_id, band, GrantState.SEALED.value, source,
                sealed_by=signed_by, granted_via=via.value,
                requested_by=requested_by, commit=False,
            )
        except sqlite3.Error:
            self.store.connection.rollback()
            raise
        return self._disclose(
            subject_id, "grant.sealed",
            f"band={int(band)} grantee={grantee_id} via={via.value} by={signed_by}",
        )

    def revoke(self, subject_id: str, grantee_id: str, revoked_by: str,
               reason: str = "") -> None:
        """Withdraw a grant. Nothing notifies the grantee, and this returns
        nothing that could be read as an acknowledgement.

        The grant row is deleted rather than flagged, so the resolver sees no
        residue and a grantee cannot discover that they *used to* have access by
        the shape of what they can no longer see. The disclosure chain keeps the
        history, and it is the subject's record to read, not the grantee's.

        The delete and the ledger row commit as one transaction: a revocation
        that landed without its ledger entry would be an untraceable removal,
        and a ledger entry without its delete would be a lie in the opposite
        direction.
        """
        self.store.revoke(subject_id, grantee_id, commit=False)
        self._disclose(
            subject_id, "grant.revoked",
            f"grantee={grantee_id} by={revoked_by}"
            + (f" reason={reason}" if reason else ""),
        )
        return None

    def convert_at_majority(self, subject_id: str) -> "list[str]":
        """Turn a now-adult member's guardian grants into their own decision.

        Returns the grantees whose access was converted. The conversion is
        *not* what makes guardian access stop — the resolver already stopped
        honouring it on the birthday. This is the second half: the grant is
        rewritten to ``pending`` and member-granted, so the member is asked
        rather than quietly assumed to agree with what their guardian decided
        for them at fifteen.

        Idempotent, and a no-op while the subject is still a minor.
        """
        if self.is_minor(subject_id):
            return []
        grantees = [
            r[0] for r in self.store.connection.execute(
                "SELECT grantee_id FROM grants"
                " WHERE subject_id = ? AND granted_via = ?"
                " ORDER BY grantee_id",
                (subject_id, GrantVia.GUARDIAN.value),
            )
        ]
        for grantee in grantees:
            self.store.connection.execute(
                "UPDATE grants SET state = ?, granted_via = ?, sealed_by = NULL,"
                "                  requested_by = NULL"
                " WHERE subject_id = ? AND grantee_id = ?",
                (GrantState.PENDING.value, GrantVia.MEMBER.value,
                 subject_id, grantee),
            )
            self._disclose(
                subject_id, "grant.converted_at_majority",
                f"grantee={grantee} guardian_authority_ended",
            )
        return grantees

    # ── use-class consent (subject-consent's own vocabulary) ────────────────
    def grant_use(self, subject_id: str, scope: str, granted_by: str):
        """Record consent to a *kind of use* on the hash-chained consent log.

        For a minor this must come from a registered guardian, and migration
        003 refuses the insert otherwise — enforced inside the database, over
        the chain's own JSON, by joining it to the roster. That join is the
        whole reason this log lives here rather than in a file beside the app.
        """
        return _sc.grant(self.backend, subject_id, scope, granted_by)

    def revoke_use(self, subject_id: str, scope: str, revoked_by: str):
        """Withdraw consent to a kind of use. Denies from this moment on, and
        stays on the record permanently — the chain is append-only."""
        return _sc.revoke(self.backend, subject_id, scope, revoked_by)

    def permitted(self, subject_id: str, scope: str) -> bool:
        """Fail-closed. Absent, unparseable, broken, truncated, pending or
        revoked all answer the same way: ``False``."""
        return _sc.permitted(self.backend, subject_id, scope)

    def verify(self) -> None:
        """Raise :class:`ChainTamperError` if the consent chain is edited or
        truncated. The gate denies silently; this says why."""
        _sc.verify_consent_chain(self.backend)

    # ── the disclosure log ──────────────────────────────────────────────────
    def may_read_disclosures(self, subject_id: str, reader: str) -> bool:
        """The subject always; a registered guardian only while the subject is
        still a minor. Guardian authority over the *record of disclosures*
        expires on the same birthday as guardian authority over the data."""
        if reader == subject_id:
            return True
        return self.is_minor(subject_id) and reader in self.guardians_of(subject_id)

    def disclosures(self, subject_id: str, reader: str) -> "list[dict]":
        """The subject's own record of what was done with their data.

        Empty for a reader who may not have it — *the same* empty a subject who
        does not exist returns. Not an exception, because an exception is an
        answer: "there is a log here and it is not yours" is most of what a
        probing grantee wanted to know, and it would make every member who has
        ever been discussed identifiable by the shape of their own refusal.

        Raises rather than returning rows if the chain fails verification, for a
        reader who is entitled to it. A history that cannot prove its own
        integrity must announce that; quietly returning what survived is how a
        tampered log becomes a clean one.
        """
        if not self.may_read_disclosures(subject_id, reader):
            return []
        return _sc.read_disclosures(self.backend, subject_id)

    def disclose_text(self, subject_id: str, action: str, text: str,
                      identifiers: "list[str]") -> str:
        """De-identify or refuse, then record.

        The only thing that may cross a sharing boundary about a member is a
        de-identified derivative, and the scrub is *verified* before anything is
        written. If an identifier survives, :class:`DeidentificationError` is
        raised and it carries neither the identifier nor the text — an error
        message is a disclosure channel like any other.
        """
        return self._disclose(subject_id, action, deidentify(text, identifiers))

    def _disclose(self, subject_id: str, action: str, detail: str = "") -> str:
        return _sc.record_disclosure(self.backend, subject_id, action, detail)

    # ── reads, unchanged from P1 ────────────────────────────────────────────
    # There is no second read path in P2 either. These forward to the store so
    # that a caller holding a roster never needs to reach past it to the
    # connection, which is the shape a caller reaches for when a wrapper is
    # missing a method and how a query ends up bypassing the predicate.
    def visible(self, principal: Principal, **kw):
        return self.store.visible(principal, **kw)

    def count(self, principal: Principal, **kw) -> int:
        return self.store.count(principal, **kw)

    def subjects(self, principal: Principal) -> "list[str]":
        return self.store.subjects(principal)

    @property
    def connection(self) -> sqlite3.Connection:
        """One connection. Grants, chains and domain data are one file."""
        return self.store.connection


__all__ = [
    "CONSENT_CHAIN",
    "ChainTamperError",
    "ConsentedRoster",
    "DeidentificationError",
    "RELATIONS",
    "SCOPES",
    "SqliteConsentBackend",
    "SubjectConsentError",
    "consent_core_path",
    "deidentify",
    "disclosure_chain",
]
