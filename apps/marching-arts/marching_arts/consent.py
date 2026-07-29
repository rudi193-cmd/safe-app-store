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

import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass, field
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


def _subject_key(subject_id: str) -> str:
    """The subject's opaque chain suffix — the same hashing the core uses for
    disclosure chains, so an opaque id never becomes a table key either way."""
    return hashlib.sha256(subject_id.encode("utf-8")).hexdigest()[:32]


def consent_chain(subject_id: str) -> str:
    """The chain name for one subject's consent log, as stored."""
    return f"{CONSENT_CHAIN}/{_subject_key(subject_id)}"


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

    def __init__(self, conn: "sqlite3.Connection | str" = ":memory:",
                 subject_id: "str | None" = None) -> None:
        self._conn = sqlite3.connect(conn) if isinstance(conn, str) else conn
        self._subject = subject_id
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

    # ── chain partitioning: one consent chain per subject ────────────────────
    #
    # The core addresses ONE global consent chain, `"consent"`, holding every
    # subject's transitions interleaved (disclosure chains are already
    # per-subject). That is fine until someone asks to be forgotten: their rows
    # are links in a chain the whole corps depends on, so removing them either
    # breaks consent for everybody or cannot be done at all. Neither is an
    # answer you can give a guardian.
    #
    # So this backend partitions at rest. A backend scoped to a subject rewrites
    # the core's `"consent"` to `"consent/<subject_hash>"`, and the core is none
    # the wiser — every consent operation it exposes (grant, revoke, permitted)
    # already names a subject, so a scoped view is the whole view for that call.
    # One member's chain can then be dropped without touching anyone else's.
    #
    # Done here rather than in `libs/subject-consent` deliberately: that copy is
    # canonical and UTETY vendors it, so re-chaining its data model is its own
    # change with its own blast radius. This needs no lib change at all.
    def for_subject(self, subject_id: str) -> "SqliteConsentBackend":
        """A view of the same connection scoped to one subject's consent chain."""
        if not (subject_id and subject_id.strip()):
            raise SubjectConsentError("subject_id required to scope a consent chain")
        return SqliteConsentBackend(self._conn, subject_id)

    def _key(self, chain: str) -> str:
        """Map the core's chain name onto the name used at rest."""
        if chain != CONSENT_CHAIN:
            return chain          # disclosure chains are already per-subject
        if self._subject is None:
            # Fail closed. An unscoped consent write would land in a global chain
            # and re-create exactly the entanglement this partitioning removes.
            raise SubjectConsentError(
                "the consent chain is per-subject; use for_subject(subject_id)"
            )
        return f"{CONSENT_CHAIN}/{_subject_key(self._subject)}"

    # ── Backend protocol ────────────────────────────────────────────────────
    def read_rows(self, chain: str) -> "list[dict] | None":
        chain = self._key(chain)
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
        chain = self._key(chain)
        # A row must land in the partition naming its own subject, or the
        # partition is a filing convention rather than a fact and deleting one
        # member's chain could silently take another member's consent with it.
        # This is the check migration 004 documents as living here: it cannot be
        # a trigger, because the partition key is a SHA-256 and stock SQLite has
        # no SHA-256. Weaker than the schema rules by exactly that much.
        subject = row.get("subject_id")
        if chain.startswith(f"{CONSENT_CHAIN}/") and subject:
            if chain != consent_chain(subject):
                raise SubjectConsentError(
                    "consent row does not belong to the chain it was written to"
                )
        nxt = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM consent_chain WHERE chain = ?",
            (chain,),
        ).fetchone()[0]
        self._conn.execute(
            "INSERT INTO consent_chain(chain, seq, row) VALUES (?, ?, ?)",
            (chain, nxt, json.dumps(row, sort_keys=True)),
        )  # no commit: write_anchor commits the pair

    def read_anchor(self, chain: str) -> "dict | None":
        chain = self._key(chain)
        row = self._conn.execute(
            "SELECT hash, count FROM consent_anchor WHERE chain = ?", (chain,)
        ).fetchone()
        return {"hash": row[0], "count": row[1]} if row else None

    def write_anchor(self, chain: str, anchor: dict) -> None:
        chain = self._key(chain)
        self._conn.execute(
            "INSERT INTO consent_anchor(chain, hash, count) VALUES (?, ?, ?)"
            " ON CONFLICT(chain) DO UPDATE SET"
            "   hash = excluded.hash, count = excluded.count",
            (chain, anchor["hash"], int(anchor["count"])),
        )
        self._conn.commit()  # commits this write AND the preceding append_row


class _ChainView(SqliteConsentBackend):
    """A backend pinned to one already-resolved chain name.

    The sweep in :meth:`ConsentedRoster.verify` walks stored chain names and has
    no subject id to scope by — the id is not recoverable from its own hash, by
    design. This maps the core's `"consent"` onto that one stored name.
    """

    def __init__(self, conn: "sqlite3.Connection", chain: str) -> None:
        super().__init__(conn)
        self._pinned = chain

    def _key(self, chain: str) -> str:
        return self._pinned if chain == CONSENT_CHAIN else chain


# ── what opening the roster did ───────────────────────────────────────────────

@dataclass(frozen=True, eq=False)
class MajoritySweep:
    """The result of the conversion pass that runs when a roster is opened.

    An *operator's* view, not a principal's. It is the return value of opening
    the database on this device, and it names members — so it must never be
    handed to a grantee, rendered in a shared view, or written anywhere the
    resolver does not already govern. Nothing here reaches a caller who did not
    already hold the connection.

    ``unconvertible`` is the honest half. A conversion that could not complete
    is not an emergency — guardian authority already expired at the birthday,
    by predicate, so the un-converted record authorizes nothing either way — but
    it is a member who has not been asked, and a sweep that returned only its
    successes would be a sweep that quietly stopped asking.
    """

    #: subject id → the grantees whose guardian-sealed access became a question
    #: for that member. Absent entirely if nothing was due.
    converted: dict = field(default_factory=dict)

    #: subjects whose conversion could not be completed and were left alone.
    unconvertible: tuple = ()

    def __bool__(self) -> bool:
        return bool(self.converted or self.unconvertible)


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

    **Opening the roster converts.** Guardian authority *expires* by predicate
    and needs nothing to run; it *converts* by write, and a write needs a
    caller. Constructing a roster runs :meth:`convert_everyone_at_majority` —
    the same place ``Store.__init__`` runs the migrations — so a member who
    turned eighteen while the laptop was shut is asked the next time somebody
    opens the file. Pass ``convert_on_open=False`` to open without it; that is
    for tests and for tooling that must read the database exactly as it was
    written, and it is safe to skip only because skipping it grants nothing —
    the un-converted record already authorizes nobody.
    """

    def __init__(self, store: "Store | None" = None, *,
                 convert_on_open: bool = True) -> None:
        self.store = store if store is not None else Store(":memory:")
        self.backend = SqliteConsentBackend(self.store.connection)
        #: What :meth:`convert_everyone_at_majority` did on the way in. Kept so
        #: a host can render "three members need to be asked" without running
        #: the pass a second time.
        self.opened = (self.convert_everyone_at_majority() if convert_on_open
                       else MajoritySweep())

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

        **It asks; it does not answer.** ``pending`` with ``sealed_by`` NULL is
        the only landing state, because the alternative — carrying the seal
        across and relabelling it ``member`` — mints a grant nobody signed, and
        the schema would take it: the signer column would be full and the
        subject is no longer a minor, so no trigger fires. The one rule the
        whole schema exists to keep would be broken by the one write nobody
        checks. ``requested_by`` is NULL for the same reason in the other
        direction: nobody asked. An authority lapsed, and naming a requester
        would put a person's name on a question the system raised by itself.

        **Sealed grants only.** A ``draft`` guardian grant is something the
        system inferred and never acted on; turning it into a question put to
        the member *is* acting on it, and it would write
        ``guardian_authority_ended`` into a permanent log for authority that
        never existed. Draft and pending rows are left exactly where they are —
        they authorize nothing and never did.

        Each grantee's rewrite and its ledger row are one transaction, and a
        failure rolls the pair back rather than leaving a state change with no
        record of it. The safe state is the un-converted one: a guardian seal
        on an adult resolves to nothing, so a conversion that never happened
        costs the member an invitation, not their privacy.

        Idempotent, and a no-op while the subject is still a minor. Idempotence
        is not bookkeeping — it falls out of the fact that a converted grant is
        no longer ``granted_via = 'guardian'`` and so no longer matches.
        """
        if self.is_minor(subject_id):
            return []
        grantees = [
            r[0] for r in self.store.connection.execute(
                "SELECT grantee_id FROM grants"
                " WHERE subject_id = ? AND granted_via = ? AND state = ?"
                " ORDER BY grantee_id",
                (subject_id, GrantVia.GUARDIAN.value, GrantState.SEALED.value),
            )
        ]
        converted = []
        for grantee in grantees:
            try:
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
            except Exception:
                # The rewrite is open on the connection and its ledger row is
                # not. Leave it there and the next successful append on this
                # connection commits it as a side effect — an access change
                # with no record that it happened, which is the shape
                # `test_a_revocation_and_its_ledger_row_are_one_transaction`
                # refuses on the revocation path.
                self.store.connection.rollback()
                raise
            converted.append(grantee)
        return converted

    # ── the caller: lazy, on open ───────────────────────────────────────────
    #
    # Expiry needs no caller because it is a predicate. Conversion is a write,
    # so it needs one, and this app has no scheduler to be it: local-first,
    # offline, no server, and a corps laptop that is shut for eight months of
    # the year. A cron job would also be the wrong shape even if one existed —
    # the failure mode of a job that does not run is exactly the failure mode
    # migration 002 rejected when it chose a birthdate over an `is_minor` flag.
    #
    # So the caller is opening the roster, and it runs where migrations already
    # run: `Store.__init__` brings the schema up to date on construction, and
    # this brings consent state up to date on construction. Same idiom, same
    # place, nothing new for a host to remember.
    #
    # WHAT IS DELIBERATELY ABSENT is a "last opened" timestamp. The obvious
    # phrasing of this pass is "convert everyone who crossed majority since the
    # last open", and it is the same mistake as `is_minor`: a bookmark is a
    # second copy of the truth, and it is wrong after a restore from backup,
    # after a clock change, after a crash between the conversion and the
    # bookmark write, and after the file is opened by a second device. Every one
    # of those failures skips a member permanently and silently. The work set is
    # derived from the data on every open instead — guardian-sealed grants whose
    # subject is no longer a minor — so it is correct on a database this code
    # has never seen before, and it empties itself by doing the work.

    def _subjects_at_majority(self) -> "list[str]":
        """Members holding guardian-sealed grants who are no longer minors.

        Private on purpose. It is a list of members who have recently turned
        eighteen and once had a guardian, which is two L1 facts about each of
        them; it answers to whoever holds the connection, and there is no
        principal to check it against. The public surface is the sweep, whose
        result the host renders to the member.
        """
        still_a_minor = self.store.policy.still_a_minor("grants.subject_id")
        return [
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT grants.subject_id FROM grants"
                " WHERE grants.granted_via = ? AND grants.state = ?"
                f"   AND NOT {still_a_minor}"
                " ORDER BY grants.subject_id",
                (GrantVia.GUARDIAN.value, GrantState.SEALED.value),
            )
        ]

    def convert_everyone_at_majority(self) -> MajoritySweep:
        """Ask every member whose guardian's authority has lapsed. Runs on open.

        One subject's failure does not stop the pass. That is not tidiness: a
        disclosure chain that fails verification raises, chains are attacker-
        editable by anyone with the file, and a sweep that propagated the first
        raise would let one tampered chain stop the whole corps from opening
        the app. The failed subject is named in
        :attr:`MajoritySweep.unconvertible` and left untouched, and untouched is
        safe — their guardian's seal stopped resolving at the birthday and
        nothing here can bring it back.
        """
        converted: "dict[str, list[str]]" = {}
        unconvertible: "list[str]" = []
        for subject_id in self._subjects_at_majority():
            try:
                grantees = self.convert_at_majority(subject_id)
            except Exception:
                # Deliberately broad, and deliberately not re-raised. Every
                # exception reachable here — a tampered chain, a locked
                # database, a trigger — leaves the same safe state behind, and
                # `convert_at_majority` has already rolled its own write back.
                unconvertible.append(subject_id)
                continue
            if grantees:
                converted[subject_id] = grantees
        return MajoritySweep(converted, tuple(unconvertible))

    # ── use-class consent (subject-consent's own vocabulary) ────────────────
    def grant_use(self, subject_id: str, scope: str, granted_by: str):
        """Record consent to a *kind of use* on the hash-chained consent log.

        For a minor this must come from a registered guardian, and migration
        003 refuses the insert otherwise — enforced inside the database, over
        the chain's own JSON, by joining it to the roster. That join is the
        whole reason this log lives here rather than in a file beside the app.
        """
        return _sc.grant(self.backend.for_subject(subject_id), subject_id, scope, granted_by)

    def revoke_use(self, subject_id: str, scope: str, revoked_by: str):
        """Withdraw consent to a kind of use. Denies from this moment on, and
        stays on the record permanently — the chain is append-only."""
        return _sc.revoke(self.backend.for_subject(subject_id), subject_id, scope, revoked_by)

    def permitted(self, subject_id: str, scope: str) -> bool:
        """Fail-closed. Absent, unparseable, broken, truncated, pending or
        revoked all answer the same way: ``False``."""
        return _sc.permitted(self.backend.for_subject(subject_id), subject_id, scope)

    def verify(self, subject_id: "str | None" = None) -> None:
        """Raise :class:`ChainTamperError` if a consent chain is edited or
        truncated. The gate denies silently; this says why.

        One subject, or — with no argument — every subject who has a chain.
        Sweeping them all matters because the chains are now independent: a
        tampered chain no longer breaks anyone else's, which is the whole point
        of partitioning, and is also exactly how one could go unnoticed.
        """
        if subject_id is not None:
            _sc.verify_consent_chain(self.backend.for_subject(subject_id))
            return
        for (chain,) in self.connection.execute(
            "SELECT DISTINCT chain FROM consent_chain WHERE chain LIKE ?"
            " UNION SELECT chain FROM consent_anchor WHERE chain LIKE ?",
            (f"{CONSENT_CHAIN}/%", f"{CONSENT_CHAIN}/%"),
        ).fetchall():
            _sc.verify_consent_chain(_ChainView(self.connection, chain))

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
    "MajoritySweep",
    "RELATIONS",
    "SCOPES",
    "SqliteConsentBackend",
    "consent_chain",
    "SubjectConsentError",
    "consent_core_path",
    "deidentify",
    "disclosure_chain",
]
