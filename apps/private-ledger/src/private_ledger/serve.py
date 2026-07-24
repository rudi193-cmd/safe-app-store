# b17: PLSERVE  ΔΣ=42
"""
serve.py — the MACHINE-facing stdio seam for Private Ledger.

Pattern (web.py in spirit): the protocol is a PURE function —
dispatch(request, db, today, allow_write) -> response — so the whole command
surface is unit-testable without ever touching real stdio. run() adapts it to
line-delimited JSON over stdin/stdout for a model, an agent, or an MCP layer
that imports the same core. This is the "MCP imports the same core" seam: the
ops below are thin wrappers over db.py / subscriptions.py / willow_bridge.py —
no logic lives here that isn't already in the core.

Line protocol: one JSON request object per line in, one JSON response object per
line out. Blank lines are ignored; malformed JSON yields an error response
without crashing the loop; EOF exits cleanly.

  request:  {"id"?: any, "op": str, "params"?: {...}}
  response: {"id"?: any, "ok": true,  "result": ...}
        or  {"id"?: any, "ok": false, "error": str}

READS are always allowed. WRITES are gated: they run only when the process was
started with --allow-write. A model must never silently mutate a financial
ledger, so read-only is the default.

Usage:
  python3 -m private_ledger --serve                # read-only
  python3 -m private_ledger --serve --allow-write  # reads + writes
"""
from __future__ import annotations

import json
import sys
from datetime import date

from . import subscriptions, willow_bridge
from .db import LedgerDB

APP_ID = "private-ledger"


# ── Small helpers ─────────────────────────────────────────────────────────────

def _rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tx_ids(db: LedgerDB) -> set[int]:
    return {row["id"] for row in db.get_transactions(limit=1_000_000)}


# ── Read operations (always allowed) ──────────────────────────────────────────

def _op_ping(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    return {"app": APP_ID, "write_enabled": allow_write}


def _op_ops(params: dict, db: LedgerDB, today: date, allow_write: bool) -> list:
    return [{"op": name, "write": spec[1]} for name, spec in sorted(_OPS.items())]


def _op_get_balance(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    accounts = _rows_to_dicts(db.get_accounts())
    total = sum((a.get("balance") or 0.0) for a in accounts)
    return {
        "total": round(total, 2),
        "accounts": [
            {"name": a.get("name"), "type": a.get("type"),
             "balance": a.get("balance")}
            for a in accounts
        ],
    }


def _op_get_accounts(params: dict, db: LedgerDB, today: date, allow_write: bool) -> list:
    return _rows_to_dicts(db.get_accounts())


def _op_get_transactions(params: dict, db: LedgerDB, today: date, allow_write: bool) -> list:
    limit = params.get("limit", 100)
    if not _is_number(limit) or limit < 0:
        raise ValueError("limit must be a non-negative number")
    return _rows_to_dicts(db.get_transactions(limit=int(limit)))


def _op_get_budget(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    year = params.get("year", today.year)
    month = params.get("month", today.month)
    if not _is_number(year) or not _is_number(month):
        raise ValueError("year and month must be numbers")
    if not (1 <= int(month) <= 12):
        raise ValueError("month must be between 1 and 12")
    return db.get_budget_summary(int(year), int(month))


def _op_get_subscriptions(params: dict, db: LedgerDB, today: date, allow_write: bool) -> list:
    return subscriptions.from_db(db, today)


def _op_get_summary(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    return willow_bridge.build_summary_atom(db, today=today)


# ── Write operations (require --allow-write) ──────────────────────────────────

def _op_add_transaction(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    amount = params.get("amount")
    description = params.get("description")
    tx_date = params.get("date")
    if not _is_number(amount):
        raise ValueError("amount must be a number")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description is required")
    if not isinstance(tx_date, str) or not tx_date.strip():
        raise ValueError("date is required (YYYY-MM-DD)")

    account_id = params.get("account_id")
    if account_id is not None and not _is_number(account_id):
        raise ValueError("account_id must be a number or omitted")
    category = params.get("category") or "Other"

    before = _tx_ids(db)
    db.add_transaction(
        account_id=int(account_id) if account_id is not None else None,
        date=tx_date,
        amount=float(amount),
        description=description,
        category=str(category),
    )
    added = _tx_ids(db) - before
    result = {"added": True}
    if added:
        result["id"] = max(added)
    return result


def _op_add_account(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name is required")
    type_ = params.get("type") or "checking"
    balance = params.get("balance", 0.0)
    if not _is_number(balance):
        raise ValueError("balance must be a number")
    db.add_account(name, str(type_), float(balance))
    return {"added": True, "name": name}


def _op_delete_transaction(params: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    tx_id = params.get("id")
    if not _is_number(tx_id):
        raise ValueError("id must be a number")
    db.delete_transaction(int(tx_id))
    return {"deleted": True, "id": int(tx_id)}


# ── Op registry: name -> (handler, requires_write) ────────────────────────────

_OPS = {
    "ping": (_op_ping, False),
    "ops": (_op_ops, False),
    "get_balance": (_op_get_balance, False),
    "get_accounts": (_op_get_accounts, False),
    "get_transactions": (_op_get_transactions, False),
    "get_budget": (_op_get_budget, False),
    "get_subscriptions": (_op_get_subscriptions, False),
    "get_summary": (_op_get_summary, False),
    "add_transaction": (_op_add_transaction, True),
    "add_account": (_op_add_account, True),
    "delete_transaction": (_op_delete_transaction, True),
}


# ── Pure dispatch ─────────────────────────────────────────────────────────────

def dispatch(request: dict, db: LedgerDB, today: date, allow_write: bool) -> dict:
    """Route one request to the core and return a response dict.

    Never raises on bad input — a malformed request becomes an error response.
    Echoes an ``id`` field back when the request carried one.
    """
    response: dict = {}
    if isinstance(request, dict) and "id" in request:
        response["id"] = request["id"]

    if not isinstance(request, dict):
        response.update(ok=False, error="request must be a JSON object")
        return response

    op = request.get("op")
    if not isinstance(op, str) or not op:
        response.update(ok=False, error="missing 'op'")
        return response

    entry = _OPS.get(op)
    if entry is None:
        response.update(ok=False, error=f"unknown op: {op}")
        return response

    handler, requires_write = entry
    if requires_write and not allow_write:
        response.update(ok=False,
                        error="writes disabled — restart with --allow-write")
        return response

    params = request.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        response.update(ok=False, error="'params' must be an object")
        return response

    try:
        result = handler(params, db, today, allow_write)
    except Exception as exc:  # bad params / core errors -> error response, never a crash
        response.update(ok=False, error=str(exc) or exc.__class__.__name__)
        return response

    response.update(ok=True, result=result)
    return response


# ── stdio loop ────────────────────────────────────────────────────────────────

def run(db: LedgerDB | None = None, allow_write: bool = False,
        today: date | None = None, stdin=None, stdout=None) -> None:
    """Drive :func:`dispatch` over line-delimited JSON on stdin/stdout.

    Reads one JSON request per line, writes exactly one JSON response per line,
    flushing after each. Blank lines are skipped; malformed JSON produces an
    error response without stopping the loop; EOF exits cleanly. With ``db`` None
    the vault-rooted DB is resolved and initialized (as in web.serve()).
    """
    if today is None:
        today = date.today()
    if db is None:
        from . import pl_paths
        from .schema import init_ledger

        db_path = str(pl_paths.db_path())
        init_ledger(db_path)
        db = LedgerDB(db_path)

    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    def _write(obj: dict) -> None:
        stdout.write(json.dumps(obj, default=str) + "\n")
        stdout.flush()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except (ValueError, TypeError) as exc:
            _write({"ok": False, "error": f"malformed JSON: {exc}"})
            continue
        _write(dispatch(request, db, today, allow_write))
