"""agm_head.py -- the ai-game-master ledger head, read from campaign.db (J9, R9).

``campaign.db`` stays (forge-convergence §9 row 11, settled; SPEC R9). Its
chain "vouches for every row except the last" and asks for a head kept outside
the box (``apps/ai-game-master/schema/01_ledger.sql:34-37``). That head goes
into the one-script record as ONE ``agm_head`` verdict row before the next
sealed tip, so the human's tip covers it.

``read(db_path)`` recomputes the head with ai-game-master's OWN
``bootstrap/verify_ledger.py`` (loaded by path, never edited, never imported
as a package): ``verify_chain`` first, then the last row's hash. Three states,
never collapsed (INVARIANTS §1):

  read         {"state": "read", "n": rows, "head": last hash, "db_sha": file hash}
  broken       {"state": "broken", "why": verify_ledger's detail}
  unreachable  {"state": "unreachable", "why": ...}  db absent, unreadable,
               or older than the chain (verify_ledger exit 2)

``row(db_path)`` is the ``agm_head`` row to hand one-script's
``table.agm_head``; a broken or unreachable ledger is never anchored.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sqlite3

#: ai-game-master's own verifier, loaded by path (never edited, never
#: imported as a package): the-table -> apps -> ai-game-master.
AGM_VERIFY_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ai-game-master", "bootstrap", "verify_ledger.py")
GENESIS = "genesis"  # ai-game-master's empty-chain sentinel (schema/01_ledger.sql)

_VERIFY = None


def _verify_ledger():
    global _VERIFY
    if _VERIFY is None:
        spec = importlib.util.spec_from_file_location("_agm_verify_ledger", AGM_VERIFY_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _VERIFY = mod
    return _VERIFY


def read(db_path: str) -> dict:
    if not os.path.isfile(db_path):
        return {"state": "unreachable", "why": f"no campaign.db at {db_path}"}
    vl = _verify_ledger()
    try:
        code, detail = vl.verify_chain(db_path)
    except sqlite3.Error as e:
        return {"state": "unreachable", "why": f"campaign.db unreadable: {e}"}
    if code == 2:
        return {"state": "unreachable", "why": detail}
    if code != 0:
        return {"state": "broken", "why": detail}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
            last = con.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        return {"state": "unreachable", "why": f"campaign.db unreadable: {e}"}
    return {"state": "read", "n": n, "head": last[0] if last else GENESIS,
            "db_sha": db_sha(db_path)}


def db_sha(db_path: str) -> str | None:
    try:
        with open(db_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def row(db_path: str) -> dict:
    """``{"n", "head", "db_sha", "db"}`` for ``table.agm_head``; raises
    ``ValueError`` on a ledger that is broken or unreachable (never
    anchored). ``db`` is where it was read (N4)."""
    got = read(db_path)
    if got["state"] != "read":
        raise ValueError(f"not anchored: the ledger is {got['state']}: {got.get('why')}")
    return {"n": got["n"], "head": got["head"], "db_sha": got["db_sha"],
            "db": os.path.abspath(db_path)}


def reader(db_path: str):
    """A ``read_head`` for one-script's ``table.check_agm_head``."""
    return lambda: read(db_path)
