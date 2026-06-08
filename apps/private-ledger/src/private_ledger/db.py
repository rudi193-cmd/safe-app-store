# b17: 89FFA  ΔΣ=42
import sqlite3
from typing import Optional


class LedgerDB:
    def __init__(self, db_path: str):
        self.path = db_path

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Accounts ──────────────────────────────────────────────────────────────

    def get_accounts(self):
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM ledger_accounts ORDER BY name"
            ).fetchall()

    def add_account(self, name: str, type_: str, balance: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ledger_accounts (name, type, balance) VALUES (?,?,?)",
                (name, type_, balance),
            )

    # ── Transactions ──────────────────────────────────────────────────────────

    def get_transactions(self, limit: int = 100):
        with self._conn() as conn:
            return conn.execute(
                """
                SELECT t.*, a.name AS account_name
                FROM ledger_transactions t
                LEFT JOIN ledger_accounts a ON t.account_id = a.id
                ORDER BY t.date DESC, t.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def add_transaction(
        self,
        account_id: Optional[int],
        date: str,
        amount: float,
        description: str,
        category: str,
        notes: str = None,
    ):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO ledger_transactions
                   (account_id, date, amount, description, category, notes)
                   VALUES (?,?,?,?,?,?)""",
                (account_id, date, amount, description, category, notes),
            )
            if account_id:
                conn.execute(
                    "UPDATE ledger_accounts SET balance = balance + ? WHERE id = ?",
                    (amount, account_id),
                )

    def delete_transaction(self, tx_id: int):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT account_id, amount FROM ledger_transactions WHERE id=?",
                (tx_id,),
            ).fetchone()
            if row and row["account_id"]:
                conn.execute(
                    "UPDATE ledger_accounts SET balance = balance - ? WHERE id = ?",
                    (row["amount"], row["account_id"]),
                )
            conn.execute("DELETE FROM ledger_transactions WHERE id=?", (tx_id,))

    # ── Budget ────────────────────────────────────────────────────────────────

    def get_budget_summary(self, year: int, month: int) -> dict:
        month_str = f"{year:04d}-{month:02d}"
        with self._conn() as conn:
            spending = conn.execute(
                """
                SELECT category, SUM(amount) AS total
                FROM ledger_transactions
                WHERE date LIKE ? AND amount < 0
                GROUP BY category
                """,
                (f"{month_str}%",),
            ).fetchall()

            cat_budgets = conn.execute(
                "SELECT name, budget FROM ledger_categories WHERE budget IS NOT NULL"
            ).fetchall()

        result = {r["name"]: {"budget": r["budget"], "spent": 0.0} for r in cat_budgets}
        for row in spending:
            cat = row["category"] or "Other"
            spent = abs(row["total"])
            if cat in result:
                result[cat]["spent"] = spent
            elif cat:
                result[cat] = {"budget": None, "spent": spent}

        for v in result.values():
            b, s = v["budget"], v["spent"]
            v["pct"] = (s / b * 100) if b else 0.0

        return result

    def get_categories(self) -> list[str]:
        with self._conn() as conn:
            return [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM ledger_categories ORDER BY name"
                ).fetchall()
            ]

    def get_recent_transactions_text(self, limit: int = 30) -> str:
        rows = self.get_transactions(limit)
        lines = []
        for tx in rows:
            sign = "+" if tx["amount"] > 0 else ""
            lines.append(
                f"{tx['date']} | {tx['description']} | {tx['category']} | {sign}{tx['amount']:.2f}"
            )
        return "\n".join(lines) or "(no transactions yet)"
