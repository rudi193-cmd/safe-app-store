"""
ledger_db.py -- Personal financial tracking using the 23-cubed lattice structure.

PostgreSQL-only. Schema: private_ledger.
Each financial entity maps into a 23x23x23 lattice (12,167 cells per entity).

Lattice constants imported from Willow user_lattice.py.
DB connection follows the same pooled psycopg2 pattern as genealogy_db.py.
"""

import os
import sys
import threading
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

# Import 23-cubed lattice constants
_WILLOW_CORE = "/mnt/c/Users/Sean/Documents/GitHub/Willow/core"
if _WILLOW_CORE not in sys.path:
    sys.path.insert(0, _WILLOW_CORE)
from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()

SCHEMA = "private_ledger"

VALID_ACCOUNT_TYPES = frozenset({
    "checking", "savings", "credit", "investment", "debt", "other"
})
VALID_ACCOUNT_STATUSES = frozenset({"active", "closed", "frozen"})
VALID_TRANSACTION_TYPES = frozenset({"income", "expense", "transfer", "payment"})
VALID_OBLIGATION_TYPES = frozenset({
    "debt", "subscription", "alimony", "child_support", "rent", "utility", "medical"
})
VALID_OBLIGATION_FREQUENCIES = frozenset({
    "monthly", "weekly", "biweekly", "annual", "one_time"
})
VALID_OBLIGATION_STATUSES = frozenset({"active", "paid", "delinquent", "forgiven"})
VALID_ENTITY_TYPES = frozenset({"account", "transaction", "obligation"})


def _resolve_host() -> str:
    """Return localhost, falling back to WSL resolv.conf nameserver."""
    host = "localhost"
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    host = line.strip().split()[1]
                    break
    except FileNotFoundError:
        pass
    return host


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            import psycopg2.pool
            dsn = os.getenv("WILLOW_DB_URL", "")
            if not dsn:
                host = _resolve_host()
                dsn = f"dbname=willow user=willow host={host}"
            _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    return _pool


def get_connection():
    """Return a pooled Postgres connection with search_path = private_ledger, public."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(f"SET search_path = {SCHEMA}, public")
        cur.close()
        return conn
    except Exception:
        pool.putconn(conn)
        raise


def release_connection(conn):
    """Return a connection to the pool."""
    try:
        conn.rollback()
    except Exception:
        pass
    _get_pool().putconn(conn)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_lattice(domain: str, depth: int, temporal: str):
    if domain not in DOMAINS:
        raise ValueError(f"Invalid domain '{domain}'. Must be one of: {DOMAINS}")
    if not (DEPTH_MIN <= depth <= DEPTH_MAX):
        raise ValueError(f"Invalid depth {depth}. Must be {DEPTH_MIN}-{DEPTH_MAX}")
    if temporal not in TEMPORAL_STATES:
        raise ValueError(f"Invalid temporal '{temporal}'. Must be one of: {TEMPORAL_STATES}")


def _validate_enum(value: str, valid: frozenset, field_name: str):
    if value not in valid:
        raise ValueError(f"Invalid {field_name} '{value}'. Must be one of: {valid}")


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_schema(conn):
    """Create the private_ledger schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name         TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK (account_type IN (
                'checking', 'savings', 'credit', 'investment', 'debt', 'other'
            )),
            institution  TEXT,
            status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                'active', 'closed', 'frozen'
            )),
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted   BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            account_id       BIGINT NOT NULL REFERENCES accounts(id),
            amount           NUMERIC(12, 2) NOT NULL,
            transaction_type TEXT NOT NULL CHECK (transaction_type IN (
                'income', 'expense', 'transfer', 'payment'
            )),
            category         TEXT,
            description      TEXT,
            transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS obligations (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            title           TEXT NOT NULL,
            obligation_type TEXT NOT NULL CHECK (obligation_type IN (
                'debt', 'subscription', 'alimony', 'child_support', 'rent', 'utility', 'medical'
            )),
            amount          NUMERIC(12, 2) NOT NULL,
            frequency       TEXT NOT NULL CHECK (frequency IN (
                'monthly', 'weekly', 'biweekly', 'annual', 'one_time'
            )),
            due_date        DATE,
            status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                'active', 'paid', 'delinquent', 'forgiven'
            )),
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id   BIGINT NOT NULL,
            entity_type TEXT NOT NULL CHECK (entity_type IN (
                'account', 'transaction', 'obligation'
            )),
            domain      TEXT NOT NULL,
            depth       INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal    TEXT NOT NULL,
            content     TEXT NOT NULL,
            source      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT FALSE,
            UNIQUE(entity_id, entity_type, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_accounts_name ON accounts (name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts (account_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions (account_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions (transaction_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions (category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_type ON transactions (transaction_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obl_type ON obligations (obligation_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obl_status ON obligations (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obl_due ON obligations (due_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_entity ON lattice_cells (entity_id, entity_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_account(conn, *, name: str, account_type: str, institution: str = None,
                status: str = "active") -> Dict[str, Any]:
    """Insert an account. Returns a dict with the new row (including id)."""
    _validate_enum(account_type, VALID_ACCOUNT_TYPES, "account_type")
    _validate_enum(status, VALID_ACCOUNT_STATUSES, "status")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO accounts (name, account_type, institution, status)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, account_type, institution, status,
                  created_at, updated_at, is_deleted
    """, (name, account_type, institution, status))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_transaction(conn, *, account_id: int, amount, transaction_type: str,
                    category: str = None, description: str = None,
                    transaction_date: date = None) -> Dict[str, Any]:
    """Insert a transaction. Returns a dict with the new row (including id)."""
    _validate_enum(transaction_type, VALID_TRANSACTION_TYPES, "transaction_type")
    amount = Decimal(str(amount))
    if transaction_date is None:
        transaction_date = date.today()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (account_id, amount, transaction_type, category,
                                  description, transaction_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, account_id, amount, transaction_type, category,
                  description, transaction_date, created_at
    """, (account_id, amount, transaction_type, category, description, transaction_date))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_obligation(conn, *, title: str, obligation_type: str, amount,
                   frequency: str, due_date: date = None,
                   status: str = "active") -> Dict[str, Any]:
    """Insert an obligation. Returns a dict with the new row (including id)."""
    _validate_enum(obligation_type, VALID_OBLIGATION_TYPES, "obligation_type")
    _validate_enum(frequency, VALID_OBLIGATION_FREQUENCIES, "frequency")
    _validate_enum(status, VALID_OBLIGATION_STATUSES, "status")
    amount = Decimal(str(amount))
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO obligations (title, obligation_type, amount, frequency, due_date, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, title, obligation_type, amount, frequency, due_date, status,
                  created_at, updated_at
    """, (title, obligation_type, amount, frequency, due_date, status))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, entity_id: int, entity_type: str, domain: str,
                     depth: int, temporal: str, content: str,
                     source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a financial entity to a lattice cell.
    Upserts on (entity_id, entity_type, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_enum(entity_type, VALID_ENTITY_TYPES, "entity_type")
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (entity_id, entity_type, domain, depth, temporal,
                                   content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (entity_id, entity_type, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content,
                      source = EXCLUDED.source,
                      is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, entity_id, entity_type, domain, depth, temporal,
                  content, source, created_at, is_sensitive
    """, (entity_id, entity_type, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_financial_summary(conn) -> Dict[str, Any]:
    """Return a summary of all active accounts, recent transactions, and obligations.
    Immutable result -- all new dicts."""
    cur = conn.cursor()

    # Active accounts
    cur.execute("""
        SELECT * FROM accounts WHERE is_deleted = FALSE AND status = 'active'
        ORDER BY name
    """)
    acct_rows = cur.fetchall()
    acct_cols = [d[0] for d in cur.description]
    accounts = [dict(zip(acct_cols, r)) for r in acct_rows]

    # Recent transactions (last 30 days)
    cur.execute("""
        SELECT t.*, a.name AS account_name
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.transaction_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY t.transaction_date DESC
        LIMIT 100
    """)
    txn_rows = cur.fetchall()
    txn_cols = [d[0] for d in cur.description]
    transactions = [dict(zip(txn_cols, r)) for r in txn_rows]

    # Active obligations
    cur.execute("""
        SELECT * FROM obligations WHERE status IN ('active', 'delinquent')
        ORDER BY due_date NULLS LAST
    """)
    obl_rows = cur.fetchall()
    obl_cols = [d[0] for d in cur.description]
    obligations = [dict(zip(obl_cols, r)) for r in obl_rows]

    # Totals
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS total_income,
            COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN transaction_type = 'payment' THEN amount ELSE 0 END), 0) AS total_payments
        FROM transactions
        WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days'
    """)
    totals_row = cur.fetchone()
    totals_cols = [d[0] for d in cur.description]
    totals = dict(zip(totals_cols, totals_row))

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total_monthly_obligations
        FROM obligations
        WHERE status IN ('active', 'delinquent') AND frequency = 'monthly'
    """)
    obl_total = cur.fetchone()[0]

    return {
        "accounts": accounts,
        "recent_transactions": transactions,
        "obligations": obligations,
        "totals_30d": totals,
        "monthly_obligation_total": obl_total,
    }


def search_transactions(conn, *, query: str = None, category: str = None,
                        transaction_type: str = None, account_id: int = None,
                        date_from: date = None, date_to: date = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
    """Search transactions with optional filters. Returns list of dicts."""
    conditions = []
    params = []

    if query:
        conditions.append("(t.description ILIKE %s OR t.category ILIKE %s)")
        params.extend([f"%{query}%", f"%{query}%"])
    if category:
        conditions.append("t.category = %s")
        params.append(category)
    if transaction_type:
        _validate_enum(transaction_type, VALID_TRANSACTION_TYPES, "transaction_type")
        conditions.append("t.transaction_type = %s")
        params.append(transaction_type)
    if account_id is not None:
        conditions.append("t.account_id = %s")
        params.append(account_id)
    if date_from:
        conditions.append("t.transaction_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("t.transaction_date <= %s")
        params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    cur = conn.cursor()
    cur.execute(f"""
        SELECT t.*, a.name AS account_name
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        {where}
        ORDER BY t.transaction_date DESC
        LIMIT %s
    """, params)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# CLI bootstrap
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    conn = get_connection()
    try:
        init_schema(conn)
        print(f"Schema '{SCHEMA}' initialized. Lattice size: {LATTICE_SIZE}")
    finally:
        release_connection(conn)
