"""aristarchus.store — the decision store: rows, seals, edges, ledger.

Playground test-build of Nestor's docs/decision-memory.md, standalone on
purpose: nothing here imports Nestor. The design is proven (or falsified)
here first; what survives goes back to Nestor as evidence-backed core
changes (N2-N7), not speculation.

The schema is the design doc's, made literal:

  decisions   — one LIVE row per (question_norm, domain), enforced by a
                partial unique index (N3). Superseded rows fall out of the
                index and accumulate as history; `superseded_by` points at
                the row that replaced them. `reason` on the yes (N4).
  rejections  — the durable no: reason required, `reopen_when` optional
                (N5). Empty reopen_when means never; non-empty means
                not-yet, and the traversal surfaces it as a condition to
                check rather than a closed door.
  edges       — signed relations between decisions (N6): supersedes |
                refines | depends_on | contradicts. An edge is itself a
                ratifiable claim, so it carries its own signature.

Every seal, rejection, and edge is HMAC-signed with a key the store never
persists (ARISTARCHUS_SEAL_KEY), and re-verified on read: a row that merely
*says* sealed is not served as sealed. Every write appends to a hash-chained
JSONL ledger; `ledger_verify` walks the chain and refuses a tampered one.

Paths are injected — both db_path and ledger_path are constructor arguments
with no home-rooted defaults (vault rule D8: the caller decides where data
lives, never this module).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SEAL_KEY_ENV = "ARISTARCHUS_SEAL_KEY"

EDGE_KINDS = ("supersedes", "refines", "depends_on", "contradicts")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    question      TEXT NOT NULL,
    question_norm TEXT NOT NULL,
    domain        TEXT NOT NULL DEFAULT 'decision',
    commitment    TEXT NOT NULL,
    reason        TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',
    author        TEXT NOT NULL DEFAULT '',
    verifier      TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    seal_sig      TEXT NOT NULL DEFAULT '',
    superseded_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rejections (
    id            TEXT PRIMARY KEY,
    question_norm TEXT NOT NULL,
    domain        TEXT NOT NULL DEFAULT 'decision',
    option        TEXT NOT NULL,
    reason        TEXT NOT NULL,
    reopen_when   TEXT NOT NULL DEFAULT '',
    verifier      TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    reject_sig    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS edges (
    id         TEXT PRIMARY KEY,
    src_id     TEXT NOT NULL,
    dst_id     TEXT NOT NULL,
    kind       TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    verifier   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    edge_sig   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_rejections_key ON rejections(question_norm, domain);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id, kind);
"""

# N3, kept outside _SCHEMA the way Nestor keeps _UNIQUE_KEY out of its schema
# script: the partial index is the one-live-row concurrency guard, and it must
# be creatable (or fail loudly) on its own, not brick an idempotent init.
_LIVE_KEY = ("CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_live "
             "ON decisions(question_norm, domain) WHERE superseded_by = ''")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class SealKeyMissing(RuntimeError):
    """No ARISTARCHUS_SEAL_KEY in the environment. Ratification is signed or
    it is not ratification — there is no unsigned fallback (fail closed)."""


class CovenantViolation(ValueError):
    """The machine tried to do the human's half: seal without a verifier,
    verifier == author, or an overwrite that would destroy a live decision."""


class LedgerBroken(RuntimeError):
    """The hash chain does not verify. The store refuses further decisions
    on a broken chain rather than appending to a lie."""


def _seal_key() -> bytes:
    key = os.environ.get(SEAL_KEY_ENV, "")
    if not key:
        raise SealKeyMissing(f"{SEAL_KEY_ENV} is not set - refusing to sign")
    return key.encode()


def sign(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(_seal_key(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_sig(payload: dict[str, Any], sig: str) -> bool:
    if not sig:
        return False
    try:
        return hmac.compare_digest(sign(payload), sig)
    except SealKeyMissing:
        # No key present: nothing can be verified, so nothing is served as
        # sealed. Absence of the key downgrades reads, it never upgrades them.
        return False


def _seal_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in
            ("id", "question_norm", "domain", "commitment", "reason",
             "author", "verifier", "created_at")}


def _reject_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in
            ("id", "question_norm", "domain", "option", "reason",
             "reopen_when", "verifier", "created_at")}


def _edge_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in
            ("id", "src_id", "dst_id", "kind", "reason", "verifier",
             "created_at")}


class DecisionStore:
    """SQLite-backed store. Both paths are injected; ":memory:" works for
    the db, and the ledger always lives at an explicit file path."""

    def __init__(self, db_path: str, ledger_path: str | Path) -> None:
        self.db_path = db_path
        self.ledger_path = Path(ledger_path)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute(_LIVE_KEY)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- ledger -----------------------------------------------------------

    def _ledger_append(self, kind: str, detail: dict[str, Any]) -> None:
        """Append one hash-chained entry. Refuses to append to a chain that
        no longer verifies - a broken ledger stops the store, loudly."""
        if self.ledger_path.exists() and not self.ledger_verify():
            raise LedgerBroken(f"{self.ledger_path} failed verification - "
                               "refusing to append to a tampered chain")
        prev = "genesis"
        if self.ledger_path.exists():
            lines = self.ledger_path.read_text().splitlines()
            if lines:
                prev = json.loads(lines[-1])["hash"]
        entry = {"kind": kind, "at": _now(), "detail": detail, "prev": prev}
        body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        entry["hash"] = hashlib.sha256(body.encode()).hexdigest()
        with self.ledger_path.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def ledger_verify(self) -> bool:
        if not self.ledger_path.exists():
            return True
        prev = "genesis"
        for line in self.ledger_path.read_text().splitlines():
            entry = json.loads(line)
            claimed = entry.pop("hash", "")
            if entry.get("prev") != prev:
                return False
            body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(body.encode()).hexdigest() != claimed:
                return False
            prev = claimed
        return True

    # -- decisions --------------------------------------------------------

    def propose(self, question: str, question_norm: str, commitment: str,
                rationale: str = "", author: str = "",
                domain: str = "decision") -> dict[str, Any]:
        """The machine's half: insert a draft. Never sealed, never signed.
        Refused when a live row already holds this key - revision goes
        through supersede(), which keeps the lineage (N2's rule: destroying
        a prior decision quietly must not be a code path)."""
        live = self.live(question_norm, domain)
        if live is not None:
            raise CovenantViolation(
                f"a live decision already holds {question_norm!r} in "
                f"{domain!r} (id={live['id']}) - use supersede(), which "
                "keeps the lineage, not a second propose()")
        row = {"id": _uid(), "question": question,
               "question_norm": question_norm, "domain": domain,
               "commitment": commitment, "reason": rationale,
               "status": "draft", "author": author, "verifier": "",
               "created_at": _now(), "seal_sig": "", "superseded_by": ""}
        self._conn.execute(
            "INSERT INTO decisions (id, question, question_norm, domain, "
            "commitment, reason, status, author, verifier, created_at, "
            "seal_sig, superseded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["id"], row["question"], row["question_norm"], row["domain"],
             row["commitment"], row["reason"], row["status"], row["author"],
             row["verifier"], row["created_at"], "", ""))
        self._conn.commit()
        self._ledger_append("propose", {"id": row["id"],
                                        "question_norm": question_norm,
                                        "domain": domain, "author": author})
        return row

    def seal(self, decision_id: str, verifier: str,
             reason: str = "") -> dict[str, Any]:
        """The human's half: ratify a draft. Requires a verifier who is not
        the author (the covenant: proposing and ratifying never rest in the
        same hand), and a seal key (signed or it is not ratification)."""
        row = self.get(decision_id)
        if row is None:
            raise KeyError(decision_id)
        if not verifier:
            raise CovenantViolation("seal requires a verifier")
        if verifier == row["author"]:
            raise CovenantViolation(
                f"verifier {verifier!r} must differ from author - proposing "
                "and ratifying never rest in the same hand")
        if reason:
            row["reason"] = reason
        row["verifier"] = verifier
        row["status"] = "sealed"
        sig = sign(_seal_payload(row))
        self._conn.execute(
            "UPDATE decisions SET status='sealed', verifier=?, reason=?, "
            "seal_sig=? WHERE id=?",
            (verifier, row["reason"], sig, decision_id))
        self._conn.commit()
        self._ledger_append("seal", {"id": decision_id, "verifier": verifier})
        row["seal_sig"] = sig
        return row

    def supersede(self, old_id: str, commitment: str, reason: str,
                  verifier: str, author: str = "") -> dict[str, Any]:
        """Replace a live decision WITHOUT destroying it (N3): the old row
        gains superseded_by and falls out of the live index; the new row is
        sealed in its place; a signed `supersedes` edge links them. The
        lineage is what this store exists to keep."""
        old = self.get(old_id)
        if old is None:
            raise KeyError(old_id)
        if old["superseded_by"]:
            raise CovenantViolation(
                f"{old_id} is already superseded by {old['superseded_by']!r} "
                "- supersede the live row, not history")
        new = self.propose_over(old, commitment, reason, author)
        try:
            sealed = self.seal(new["id"], verifier, reason)
        except Exception:
            # Restore the old row to the live index and drop the orphan
            # draft: a failed supersede must leave the store exactly as it
            # found it, not with the live decision stranded in history.
            self._conn.execute("DELETE FROM decisions WHERE id=?",
                               (new["id"],))
            self._conn.execute(
                "UPDATE decisions SET superseded_by='' WHERE id=?",
                (old["id"],))
            self._conn.commit()
            raise
        self._conn.execute(
            "UPDATE decisions SET superseded_by=? WHERE id=?",
            (sealed["id"], old_id))
        self._conn.commit()
        self._ledger_append("supersede", {"old": old_id, "new": sealed["id"],
                                          "verifier": verifier})
        self.add_edge(sealed["id"], old_id, "supersedes", reason, verifier)
        return sealed

    def propose_over(self, old: dict[str, Any], commitment: str,
                     reason: str, author: str) -> dict[str, Any]:
        """Insert the successor draft for a supersede. Bypasses the live-row
        guard deliberately: the caller is about to retire the old row, and
        the partial index still holds because the new row goes live only as
        the old one leaves."""
        # The old row must leave the live index before the new one enters it,
        # or the partial unique index (correctly) refuses two live rows. Mark
        # first, insert second; supersede() then points superseded_by at the
        # real successor id.
        self._conn.execute(
            "UPDATE decisions SET superseded_by='pending' WHERE id=?",
            (old["id"],))
        row = {"id": _uid(), "question": old["question"],
               "question_norm": old["question_norm"], "domain": old["domain"],
               "commitment": commitment, "reason": reason,
               "status": "draft", "author": author, "verifier": "",
               "created_at": _now(), "seal_sig": "", "superseded_by": ""}
        self._conn.execute(
            "INSERT INTO decisions (id, question, question_norm, domain, "
            "commitment, reason, status, author, verifier, created_at, "
            "seal_sig, superseded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["id"], row["question"], row["question_norm"], row["domain"],
             row["commitment"], row["reason"], row["status"], row["author"],
             row["verifier"], row["created_at"], "", ""))
        self._conn.commit()
        return row

    # -- rejections -------------------------------------------------------

    def reject(self, question_norm: str, option: str, reason: str,
               verifier: str, reopen_when: str = "",
               domain: str = "decision") -> dict[str, Any]:
        """The durable no. `reason` is required - an unexplained rejection
        is the Aristarchus bug, eighteen centuries of it. Empty reopen_when
        means never; say so on purpose, not by omission of thought."""
        if not reason:
            raise CovenantViolation(
                "a rejection without a reason is the bug this store exists "
                "to fix - say why, even briefly")
        if not verifier:
            raise CovenantViolation("reject requires a verifier")
        row = {"id": _uid(), "question_norm": question_norm, "domain": domain,
               "option": option, "reason": reason,
               "reopen_when": reopen_when, "verifier": verifier,
               "created_at": _now()}
        row["reject_sig"] = sign(_reject_payload({**row, "reject_sig": ""}))
        self._conn.execute(
            "INSERT INTO rejections (id, question_norm, domain, option, "
            "reason, reopen_when, verifier, created_at, reject_sig) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (row["id"], row["question_norm"], row["domain"], row["option"],
             row["reason"], row["reopen_when"], row["verifier"],
             row["created_at"], row["reject_sig"]))
        self._conn.commit()
        self._ledger_append("reject", {"id": row["id"],
                                       "question_norm": question_norm,
                                       "domain": domain,
                                       "reopen_when": reopen_when})
        return row

    # -- edges ------------------------------------------------------------

    def add_edge(self, src_id: str, dst_id: str, kind: str,
                 reason: str, verifier: str) -> dict[str, Any]:
        """A signed relation (N6). The edge is itself a ratifiable claim -
        'this supersedes that' carries the same weight as a seal, so it
        carries its own signature and its own verifier."""
        if kind not in EDGE_KINDS:
            raise ValueError(f"unknown edge kind {kind!r}; "
                             f"one of {EDGE_KINDS}")
        if not verifier:
            raise CovenantViolation("an edge is a claim; claims are signed "
                                    "by someone - verifier required")
        for ref in (src_id, dst_id):
            if self.get(ref) is None:
                raise KeyError(ref)
        row = {"id": _uid(), "src_id": src_id, "dst_id": dst_id,
               "kind": kind, "reason": reason, "verifier": verifier,
               "created_at": _now()}
        row["edge_sig"] = sign(_edge_payload(row))
        self._conn.execute(
            "INSERT INTO edges (id, src_id, dst_id, kind, reason, verifier, "
            "created_at, edge_sig) VALUES (?,?,?,?,?,?,?,?)",
            (row["id"], row["src_id"], row["dst_id"], row["kind"],
             row["reason"], row["verifier"], row["created_at"],
             row["edge_sig"]))
        self._conn.commit()
        self._ledger_append("edge_seal", {"id": row["id"], "kind": kind,
                                          "src": src_id, "dst": dst_id})
        return row

    # -- reads (every read re-verifies) -----------------------------------

    @staticmethod
    def _check_seal(row: dict[str, Any]) -> dict[str, Any]:
        """A row that says sealed is served as sealed only when the seal
        verifies. One that does not is surfaced as tampered, never served -
        the row's claim about itself is exactly what the signature exists
        to distrust."""
        if row["status"] == "sealed" and not verify_sig(_seal_payload(row),
                                                        row["seal_sig"]):
            row = dict(row)
            row["status"] = "tampered"
        return row

    def get(self, decision_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM decisions WHERE id=?",
                                 (decision_id,))
        row = cur.fetchone()
        return self._check_seal(dict(row)) if row else None

    def live(self, question_norm: str,
             domain: str = "decision") -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM decisions WHERE question_norm=? AND domain=? "
            "AND superseded_by=''", (question_norm, domain))
        row = cur.fetchone()
        return self._check_seal(dict(row)) if row else None

    def all_questions(self, domain: str = "decision") -> list[dict[str, Any]]:
        """Every distinct question key in a domain, live rows and rejection
        keys both - the candidate set a fuzzy matcher scores against."""
        cur = self._conn.execute(
            "SELECT DISTINCT question_norm FROM decisions WHERE domain=? "
            "UNION SELECT DISTINCT question_norm FROM rejections "
            "WHERE domain=?", (domain, domain))
        return [r["question_norm"] for r in cur.fetchall()]

    def lineage(self, decision_id: str) -> list[dict[str, Any]]:
        """The chain of superseded predecessors, newest first, each with the
        reason it was replaced. This is what a merged-PR history gives git
        and what re-sealing destroyed in Nestor."""
        chain: list[dict[str, Any]] = []
        current = decision_id
        while True:
            cur = self._conn.execute(
                "SELECT * FROM decisions WHERE superseded_by=?", (current,))
            row = cur.fetchone()
            if row is None:
                return chain
            row = self._check_seal(dict(row))
            chain.append(row)
            current = row["id"]

    def rejections_for(self, question_norm: str,
                       domain: str = "decision") -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM rejections WHERE question_norm=? AND domain=?",
            (question_norm, domain))
        out = []
        for r in cur.fetchall():
            row = dict(r)
            if not verify_sig(_reject_payload({**row, "reject_sig": ""}),
                              row["reject_sig"]):
                row["tampered"] = True
            out.append(row)
        return out

    def edges_for(self, decision_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM edges WHERE src_id=? OR dst_id=?",
            (decision_id, decision_id))
        out = []
        for r in cur.fetchall():
            row = dict(r)
            if not verify_sig(_edge_payload({**row, "edge_sig": ""}),
                              row["edge_sig"]):
                row["tampered"] = True
            out.append(row)
        return out
