"""ledger_sink.py — the-table's write path into an ai-game-master campaign box.

Walking skeleton. Writes append-only ledger rows (session_open / turn /
session_close) into an ai-game-master `campaign.db` and asks
ai-game-master's OWN `bootstrap/verify_ledger.py` whether the resulting
hash chain is honest. This module does not reimplement the chain — it
mirrors the exact hashing scheme ai-game-master already uses, so its rows
verify under ai-game-master's own verifier without modification there.

Reused, not reinvented — the hash scheme is copied byte-for-byte (comments
included) from two places in apps/ai-game-master, which must already agree
with each other:

  * docs/poc_vander_room.py, append_turn() (~line 44-60): the writer shape —
    SELECT the last row's hash (or the literal 'genesis' if the ledger is
    empty) as prev_hash, INSERT the row with hash='', then UPDATE it with
    the recomputed hash once the id is known.
  * bootstrap/verify_ledger.py, canonical_row()/row_hash() (~line 59-81):
    the one authority on the canonical form each row's `hash` covers —
    json.dumps({"id","ts","session","kind","note","state","prev_hash"},
    ensure_ascii=False) in exactly that key order, sha256 hex digest of the
    UTF-8 bytes. `state` is embedded as an already-serialized JSON *string*,
    not re-parsed — writer and verifier must agree without re-parsing it.

HARD CONSTRAINT: this sink never touches the `canon` table, never writes a
SEALED/REJECTED status, never signs a ruling. It writes only
kind IN ('session_open', 'turn', 'session_close') ledger rows — the
append-only record of what happened at the table. Sealing canon is a human
act (apps/ai-game-master/CLAUDE.md) and is out of scope here by design.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

GENESIS = "genesis"  # same empty-chain sentinel nestor.ledger.head()/verify() and
                      # ai-game-master's schema/verifier use.

# ── path resolution: the-table is a CONSUMER of ai-game-master, never an editor of it.
# apps/the-table/the_table/ledger_sink.py -> repo root is three directories up.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_DIR)))
AGM_ROOT = os.path.join(_REPO_ROOT, "apps", "ai-game-master")
AGM_SCHEMA_DIR = os.path.join(AGM_ROOT, "schema")
AGM_PROVISION_SH = os.path.join(AGM_ROOT, "bootstrap", "provision.sh")
AGM_VERIFY_PY = os.path.join(AGM_ROOT, "bootstrap", "verify_ledger.py")

# Same schema application order provision.sh uses. 05_corpus.reference.sql is
# deliberately NOT applied — provision.sh treats it as reference-only.
_SCHEMA_FILES = ("01_ledger.sql", "02_canon.sql", "03_entities.sql", "04_rulings.sql")


def _canonical_row(id_, ts, session, kind, note, state, prev_hash) -> str:
    """Byte-for-byte the same form as verify_ledger.py's canonical_row().

    Key order and separators matter: json.dumps default separators
    (", " / ": "), ensure_ascii=False, in exactly this key order.
    """
    obj = {
        "id": id_,
        "ts": ts,
        "session": session,
        "kind": kind,
        "note": note,
        "state": state,
        "prev_hash": prev_hash,
    }
    return json.dumps(obj, ensure_ascii=False)


def _row_hash(*args) -> str:
    return hashlib.sha256(_canonical_row(*args).encode("utf-8")).hexdigest()


class LedgerSink:
    """Append-only writer into an ai-game-master campaign.db, one box per game."""

    def __init__(self, box_dir: str):
        self.box_dir = os.path.abspath(box_dir)
        self.db_path = os.path.join(self.box_dir, "campaign.db")
        self._session_num = 0
        self._provision()
        self._con = sqlite3.connect(self.db_path)
        self._last_verify_output = ""

    # ── provisioning ─────────────────────────────────────────────────────────
    def _provision(self) -> None:
        """Provision (or open) the campaign box, reusing ai-game-master's own
        bootstrap/provision.sh when possible so this sink can't drift from it.
        """
        if os.path.exists(self.db_path):
            return  # already provisioned; open as-is (idempotent, like provision.sh)

        bash = shutil.which("bash")
        if bash and os.path.exists(AGM_PROVISION_SH):
            subprocess.run(
                [bash, AGM_PROVISION_SH, self.box_dir],
                check=True, capture_output=True, text=True,
            )
            return

        # Headless fallback: no bash on PATH. Apply the same schema/*.sql files,
        # in the same order provision.sh does, via Python's stdlib sqlite3 —
        # this mirrors provision.sh's own "no sqlite3 CLI" fallback, one layer up.
        os.makedirs(self.box_dir, exist_ok=True)
        for sub in ("corpus", "keys"):
            os.makedirs(os.path.join(self.box_dir, sub), exist_ok=True)
        con = sqlite3.connect(self.db_path)
        try:
            for ddl in _SCHEMA_FILES:
                with open(os.path.join(AGM_SCHEMA_DIR, ddl), "r") as f:
                    con.executescript(f.read())
            con.commit()
        finally:
            con.close()

    # ── the chain ────────────────────────────────────────────────────────────
    def _append(self, session: int, kind: str, note: str, state_obj: dict) -> tuple[int, str]:
        """Write one chained ledger row. Mirrors poc_vander_room.py append_turn()."""
        ts = datetime.now(timezone.utc).isoformat()
        state = json.dumps(state_obj, ensure_ascii=False)
        row = self._con.execute(
            "SELECT hash FROM ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev = row[0] if row else GENESIS
        cur = self._con.execute(
            "INSERT INTO ledger (ts, session, kind, note, state, prev_hash, hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, session, kind, note, state, prev, ""),
        )
        id_ = cur.lastrowid
        h = _row_hash(id_, ts, session, kind, note, state, prev)
        self._con.execute("UPDATE ledger SET hash=? WHERE id=?", (h, id_))
        self._con.commit()
        return id_, h

    # ── pinned sink interface ───────────────────────────────────────────────
    def open_session(self, session_id: str, meta: dict) -> None:
        """Append a kind='session_open' row. state = JSON of meta.

        The ledger schema's `session` column is an INTEGER counter (matching
        ai-game-master's own convention); the caller's string session_id is
        preserved verbatim in `note` so it is never lost, while `state`
        carries `meta` untouched, exactly as documented.
        """
        self._session_num += 1
        self._append(self._session_num, "session_open", str(session_id), meta)

    def snapshot(self, state: dict, note: str = "") -> None:
        """Append a kind='turn' row. state = JSON of state. Maintains the chain."""
        self._append(self._session_num, "turn", note, state)

    def close_session(self, result: dict) -> None:
        """Append a kind='session_close' row. state = JSON of result."""
        self._append(self._session_num, "session_close", "", result)

    def verify(self) -> bool:
        """Run ai-game-master's OWN verify_ledger.py against this db.

        Returns True iff the chain (and the never-write-canon covenant guard)
        verify clean. On failure, the verifier's stdout/stderr is surfaced on
        stderr and kept on self._last_verify_output for callers/tests to
        inspect.
        """
        self._con.commit()
        result = subprocess.run(
            [sys.executable, AGM_VERIFY_PY, self.db_path, "--canon"],
            capture_output=True, text=True,
        )
        self._last_verify_output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            print(self._last_verify_output, file=sys.stderr)
            return False
        return True

    def head(self) -> str:
        """Return the current chain head hash (GENESIS if the ledger is empty)."""
        row = self._con.execute(
            "SELECT hash FROM ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS

    def close(self) -> None:
        self._con.close()
