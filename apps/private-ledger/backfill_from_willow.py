"""
backfill_from_willow.py -- Seed the private_ledger schema with known financial data.

Pulls context from Willow knowledge base and seeds accounts, obligations,
and lattice cells with known financial facts.

Run once after init_schema, or re-run (idempotent via upsert on lattice).
"""

import sys
from datetime import date

# Ensure ledger_db is importable from this directory
sys.path.insert(0, "/mnt/c/Users/Sean/Documents/GitHub/safe-app-private-ledger")
import ledger_db


def backfill(conn):
    """Seed known financial data into the private_ledger schema."""

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    citi = ledger_db.add_account(
        conn,
        name="Citi Credit Card",
        account_type="credit",
        institution="Citibank",
        status="active",
    )
    print(f"  Account: {citi['name']} (id={citi['id']})")

    workers_comp = ledger_db.add_account(
        conn,
        name="Workers Comp Benefits",
        account_type="other",
        institution="State Workers Compensation",
        status="active",
    )
    print(f"  Account: {workers_comp['name']} (id={workers_comp['id']})")

    ai_infra = ledger_db.add_account(
        conn,
        name="AI Infrastructure",
        account_type="other",
        institution="Multi-provider (14 free tier)",
        status="active",
    )
    print(f"  Account: {ai_infra['name']} (id={ai_infra['id']})")

    # ------------------------------------------------------------------
    # Transactions -- Book 3 publishing cost
    # ------------------------------------------------------------------

    book3_txn = ledger_db.add_transaction(
        conn,
        account_id=citi["id"],
        amount=800.00,
        transaction_type="expense",
        category="publishing",
        description="Book 3 publishing cost - Citi of Books. Status: blocked on funding.",
        transaction_date=date(2026, 3, 1),
    )
    print(f"  Transaction: Book 3 publishing ${book3_txn['amount']} (id={book3_txn['id']})")

    # ------------------------------------------------------------------
    # Obligations
    # ------------------------------------------------------------------

    bankruptcy_obl = ledger_db.add_obligation(
        conn,
        title="Bankruptcy filing deadline",
        obligation_type="debt",
        amount=0.00,
        frequency="one_time",
        due_date=date(2026, 3, 11),
        status="active",
    )
    print(f"  Obligation: {bankruptcy_obl['title']} (id={bankruptcy_obl['id']})")

    ai_cost_obl = ledger_db.add_obligation(
        conn,
        title="AI infrastructure cost target",
        obligation_type="subscription",
        amount=0.10,
        frequency="monthly",
        status="active",
    )
    print(f"  Obligation: {ai_cost_obl['title']} (id={ai_cost_obl['id']})")

    # ------------------------------------------------------------------
    # Lattice placements
    # ------------------------------------------------------------------

    # Book 3 -- finance domain, depth 5 (moderate detail), flagged temporal
    ledger_db.place_in_lattice(
        conn,
        entity_id=book3_txn["id"],
        entity_type="transaction",
        domain="finance",
        depth=5,
        temporal="flagged",
        content="Book 3 publishing cost $800 via Citi of Books. Blocked on funding. "
                "Critical creative milestone tied to financial constraint.",
        source="willow_knowledge",
        is_sensitive=True,
    )

    # Bankruptcy context -- finance domain, depth 10 (deep), immediate temporal
    ledger_db.place_in_lattice(
        conn,
        entity_id=bankruptcy_obl["id"],
        entity_type="obligation",
        domain="finance",
        depth=10,
        temporal="immediate",
        content="Bankruptcy filing deadline March 11, 2026. "
                "Impacts all financial planning and obligation priorities.",
        source="willow_knowledge",
        is_sensitive=True,
    )

    # Workers comp -- finance domain, depth 3 (surface), recurring temporal
    ledger_db.place_in_lattice(
        conn,
        entity_id=workers_comp["id"],
        entity_type="account",
        domain="finance",
        depth=3,
        temporal="recurring",
        content="Workers compensation benefits -- active payment stream. "
                "Payment logs referenced in Willow knowledge base.",
        source="willow_knowledge",
        is_sensitive=True,
    )

    # AI cost target -- meta domain, depth 1 (surface), established temporal
    ledger_db.place_in_lattice(
        conn,
        entity_id=ai_cost_obl["id"],
        entity_type="obligation",
        domain="meta",
        depth=1,
        temporal="established",
        content="AI infrastructure cost target: $0.10/month. "
                "14 free-tier providers rotating via llm_router. "
                "MCP-first, fleet for generation, Ollama local fallback.",
        source="willow_knowledge",
        is_sensitive=False,
    )

    # Cross-domain: bankruptcy in crisis domain
    ledger_db.place_in_lattice(
        conn,
        entity_id=bankruptcy_obl["id"],
        entity_type="obligation",
        domain="crisis",
        depth=8,
        temporal="immediate",
        content="Bankruptcy filing creates cascading constraints on "
                "publishing (Book 3), subscriptions, and debt obligations.",
        source="willow_knowledge",
        is_sensitive=True,
    )

    print("  Lattice cells placed.")
    print("Backfill complete.")


if __name__ == "__main__":
    conn = ledger_db.get_connection()
    try:
        ledger_db.init_schema(conn)
        print("Schema initialized.")
        backfill(conn)
    except Exception as e:
        print(f"Error during backfill: {e}")
        raise
    finally:
        ledger_db.release_connection(conn)
