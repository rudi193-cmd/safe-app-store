# b17: 8D95C  ΔΣ=42
import sqlite3

DEFAULT_CATEGORIES = [
    ("Food & Dining", 400.0),
    ("Housing", 1500.0),
    ("Transportation", 200.0),
    ("Utilities", 150.0),
    ("Entertainment", 100.0),
    ("Healthcare", 100.0),
    ("Shopping", 300.0),
    ("Income", None),
    ("Other", None),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    type       TEXT NOT NULL DEFAULT 'checking',
    balance    REAL NOT NULL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledger_categories (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL UNIQUE,
    budget REAL
);

CREATE TABLE IF NOT EXISTS ledger_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER REFERENCES ledger_accounts(id),
    date        TEXT NOT NULL,
    amount      REAL NOT NULL,
    description TEXT NOT NULL,
    category    TEXT DEFAULT 'Other',
    notes       TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ledger_tx_date ON ledger_transactions(date DESC);
"""


def init_ledger(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    for name, budget in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO ledger_categories (name, budget) VALUES (?,?)",
            (name, budget),
        )
    conn.commit()
    conn.close()
