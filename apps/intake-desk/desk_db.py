"""Storage for the intake desk.

Local-first SQLite. The schema (schema.sql) carries the invariants as
triggers, so they hold for anything that opens the file.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from vault_paths import resolve  # shared vault-rooted resolver (box audit A5)

SCHEMA = Path(__file__).with_name("schema.sql")

#: Every trigger the vault must be carrying. Checked on open — a trigger that
#: was dropped is restored by CREATE TRIGGER IF NOT EXISTS, but one *replaced*
#: with a neutered body (WHEN 0) survives that, so the names alone are not
#: enough and connect() compares the stored SQL against this file's.
REQUIRED_TRIGGERS = (
    "statements_write_once",
    "statements_never_deleted",
    "claims_never_deleted",
    "claims_span_resolves_insert",
    "claims_span_frozen",
    "claims_witness_gate_update",
    "claims_witness_gate_insert",
    "claims_publish_needs_ruling_update",
    "claims_publish_needs_ruling_insert",
    "claims_withheld_is_final",
)


class VaultTampered(Exception):
    """The vault is not carrying the gates it is supposed to. Fail closed."""


def default_db() -> Path:
    """Where a desk keeps its vault.

    Derived from the vault root, never a hardcoded home path (installer design
    D7/D8). A desk is somebody's desk — there is no central pile — so the
    operator can point this anywhere with INTAKE_DESK_DB.
    """
    return resolve("intake-desk", "desk.sqlite3", env_vars=("INTAKE_DESK_DB",))


def body_digest(body: str) -> str:
    """The digest recorded for a verbatim statement.

    On its own this is a checksum, not a witness: it lives in the same row as
    the body, so anything that can rewrite one can rewrite the other.
    `desk.file_statement` also writes it into the subject's hash-chained
    disclosure record, and `verify_bodies` compares the two.

    Read the limit of that precisely. The chain lives outside this *file*; it
    does not live outside this *trust boundary*. Both sit on one disk, written
    by one process, under one set of permissions — so an attacker who can
    rewrite a row can rewrite the chain, and two records that agree prove only
    that one hand wrote both. willow-mcp's governance ledger (#280) states the
    degraded case exactly: without an externally-held head, "someone else
    remembers" becomes "someone else has a copy that will agree with whatever
    it now says."

    Two records catch a CARELESS rewrite. Only `chain_heads()`, pinned
    somewhere this process cannot reach, catches a careful one.
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _expected_trigger_sql() -> dict[str, str]:
    """The trigger bodies this file defines, normalised for comparison."""
    out: dict[str, str] = {}
    text = SCHEMA.read_text(encoding="utf-8")
    for chunk in text.split("CREATE TRIGGER IF NOT EXISTS ")[1:]:
        name = chunk.split()[0]
        body = chunk.split("END;")[0]
        out[name] = " ".join(body.split())
    return out


def connect(db_path: Path | str | None = None, *, check: bool = True) -> sqlite3.Connection:
    """Open (creating if needed) a desk vault with the schema applied."""
    path = Path(db_path) if db_path is not None else default_db()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")
    # Without this, INSERT OR REPLACE does not fire the delete triggers, so a
    # REPLACE quietly destroys a statement or forges a ruling on an existing
    # claim. It is the single line that closes that whole class.
    conn.execute("PRAGMA recursive_triggers = ON")
    if check:
        verify_gates(conn)
    return conn


def verify_gates(conn: sqlite3.Connection) -> None:
    """Refuse a vault whose gates have been removed or neutered."""
    expected = _expected_trigger_sql()
    stored = {
        row["name"]: " ".join((row["sql"] or "").split())
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'")
    }
    for name in REQUIRED_TRIGGERS:
        if name not in stored:
            raise VaultTampered(f"missing gate: {name}")
        want = expected.get(name, "")
        if want and want.split("BEGIN")[0] not in stored[name]:
            raise VaultTampered(f"gate has been altered: {name}")
    for pragma, want in (("recursive_triggers", 1), ("foreign_keys", 1)):
        got = conn.execute(f"PRAGMA {pragma}").fetchone()[0]
        if got != want:
            raise VaultTampered(f"PRAGMA {pragma} is {got}, expected {want}")


def verify_bodies(conn: sqlite3.Connection, consent_store=None) -> list[str]:
    """Ids of statements whose body no longer matches its recorded digest.

    With `consent_store`, the digest is compared against the one in the
    subject's disclosure chain — which is hash-chained, anchored against
    truncation, and lives outside this database. That is what makes tampering
    detectable at all: an attacker who rewrites a body and its neighbouring
    digest leaves the row self-consistent, and only the external record
    disagrees.

    Without it, this compares the row against itself and catches a careless
    rewrite only. Callers that care should pass the store.
    """
    bad: list[str] = []
    chain: dict[str, set[str]] = {}
    if consent_store is not None:
        from subject_consent import read_disclosures
        for row in conn.execute("SELECT DISTINCT narrator_id FROM statements"):
            for entry in read_disclosures(consent_store, row["narrator_id"]) or []:
                detail = entry.get("detail", "")
                if "sha256=" in detail:
                    sid = detail.split("id=")[1].split()[0]
                    chain.setdefault(sid, set()).add(detail.split("sha256=")[1].split()[0])

    for row in conn.execute("SELECT id, body, body_sha256 FROM statements"):
        actual = body_digest(row["body"])
        if actual != row["body_sha256"]:
            bad.append(row["id"])
        elif chain and (row["id"] not in chain or actual not in chain[row["id"]]):
            bad.append(row["id"])
    return bad


def missing_statements(conn: sqlite3.Connection, consent_store,
                       narrators: "list[str] | set[str]") -> list[str]:
    """Statement ids the disclosure chain records but the vault no longer holds.

    `connect()` runs CREATE TABLE IF NOT EXISTS, so a dropped table comes back
    as a pristine empty desk with nothing to say about it. The consent library
    solves exactly this for its own rows with an anchor — *emptied is not
    absent* — and this is that argument applied to the vault: the chain is the
    outside record of what was filed.

    The narrator roster is a required argument rather than read from the
    database, because a dropped table takes the in-database roster with it —
    which is precisely the case this exists to detect.
    """
    from subject_consent import read_disclosures
    held = {row["id"] for row in conn.execute("SELECT id FROM statements")}
    recorded: set[str] = set()
    for narrator in narrators:
        for entry in read_disclosures(consent_store, narrator) or []:
            if entry.get("action") == "statement_filed" and "id=" in entry.get("detail", ""):
                recorded.add(entry["detail"].split("id=")[1].split()[0])
    return sorted(recorded - held)


# ── the external anchor ───────────────────────────────────────────────────────
#
# A hash chain vouches for every line except the newest, and a chain whose
# writer can also rewrite the anchor vouches for nothing against that writer.
# The close is a head held somewhere this process cannot reach: a CI variable,
# a monitoring system, a printed page in a drawer. These two functions are the
# desk's side of that contract; where the head is kept is the operator's.
#
# Shape and failure semantics follow willow-mcp's governance_ledger.verify():
# a broken link and "internally consistent but not the chain you anchored" are
# reported DIFFERENTLY, because the second is what an edit-plus-repair looks
# like from outside and it must not read as ordinary corruption.


def chain_heads(consent_store, narrators: "list[str] | set[str]") -> dict[str, str]:
    """The anchored head hash per disclosure chain. Pin this OUTSIDE the box.

    Returns {narrator_id: head_hash}. A narrator with no chain is omitted
    rather than reported as empty — absent and emptied are different, and
    `verify_chains` is where that distinction is enforced.
    """
    from subject_consent.core import FileBackend, _disclosure_chain

    backend = FileBackend(consent_store) if not hasattr(consent_store, "read_anchor") \
        else consent_store
    out: dict[str, str] = {}
    for narrator in sorted(narrators):
        anchor = backend.read_anchor(_disclosure_chain(narrator))
        if anchor and anchor.get("hash"):
            out[narrator] = anchor["hash"]
    return out


def verify_chains(consent_store, narrators: "list[str] | set[str]",
                  expected: "dict[str, str] | None" = None) -> dict:
    """Walk each narrator's disclosure chain; optionally hold it to an anchor.

    Without `expected` this answers only "is this internally consistent" —
    which, per willow-mcp #280, internal consistency alone can never turn into
    "is this the same chain it was yesterday."

    With `expected` (a previous `chain_heads()` result, kept outside this
    machine) a silent relink becomes a detected one.

    Returns {"valid", "tampered": [...], "moved": {...}, "heads": {...}} where
    `tampered` is a broken or truncated chain and `moved` is a chain that
    verifies cleanly but no longer matches its anchor. They are separate keys
    on purpose: the second is the interesting one.
    """
    from subject_consent import ChainTamperError, verify_consent_chain  # noqa: F401
    from subject_consent.core import FileBackend, _disclosure_chain, _verify

    backend = FileBackend(consent_store) if not hasattr(consent_store, "read_anchor") \
        else consent_store
    tampered: list[str] = []
    heads: dict[str, str] = {}

    for narrator in sorted(narrators):
        chain = _disclosure_chain(narrator)
        rows = backend.read_rows(chain)
        if rows is None:
            continue                      # absent: never written, not evidence
        if not _verify(rows, backend.read_anchor(chain)):
            tampered.append(narrator)     # includes the emptied-chain case
            continue
        heads[narrator] = rows[-1]["hash"]

    moved: dict[str, dict] = {}
    if expected is not None:
        for narrator, want in expected.items():
            got = heads.get(narrator)
            if got != want:
                moved[narrator] = {"expected": want, "found": got}

    return {"valid": not tampered and not moved, "tampered": tampered,
            "moved": moved, "heads": heads}
