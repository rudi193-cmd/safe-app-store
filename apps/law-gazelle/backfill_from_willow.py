"""
backfill_from_willow.py -- Seed the legal_gazelle schema with known case data.

Run once to populate initial cases, documents, events, and lattice cells.
Idempotent: checks for existing case_number before inserting.
"""

import sys
import os

# Ensure legal_db is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import legal_db


def _case_exists(conn, case_number: str) -> bool:
    """Check if a case with the given case_number already exists."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM cases WHERE case_number = %s", (case_number,))
    return cur.fetchone() is not None


def seed_workers_comp(conn) -> dict:
    """Seed WCA 00-00000: Trader Joe's back injury workers' comp claim."""
    if _case_exists(conn, "WCA 00-00000"):
        cur = conn.cursor()
        cur.execute("SELECT id FROM cases WHERE case_number = %s", ("WCA 00-00000",))
        return {"id": cur.fetchone()[0], "skipped": True}

    case = legal_db.add_case(
        conn,
        case_number="WCA 00-00000",
        case_type="workers_comp",
        title="Workers' Comp - Trader Joe's Back Injury",
        status="open",
        jurisdiction="Washington State Department of Labor & Industries",
        filed_date="2025-01-01",
        description="Workers' compensation claim for back injury sustained while employed at Trader Joe's. "
                    "Involves medical treatment, wage replacement, and potential permanent partial disability evaluation.",
    )
    cid = case["id"]

    # Documents
    legal_db.add_document(
        conn,
        case_id=cid,
        doc_type="research",
        title="Deep Dive Workers' Comp Legal Research.pdf",
        content_summary="Comprehensive legal research on Washington State workers' compensation law, "
                        "claim procedures, benefit calculations, and appeal processes.",
    )
    legal_db.add_document(
        conn,
        case_id=cid,
        doc_type="research",
        title="Healthcare and Workers' Comp Effects.pdf",
        content_summary="Analysis of healthcare impacts from workers' compensation injuries, "
                        "treatment protocols, and long-term health effects of back injuries.",
    )

    # Events
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="filing",
        event_date="2025-01-01",
        description="Initial workers' compensation claim filed with L&I",
        is_completed=True,
    )
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="mediation",
        event_date="2025-02-15",
        description="Mediation response deadline - employer response to claim",
        is_completed=True,
    )
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="decision",
        event_date="2025-03-01",
        description="Administrative closure notice review",
        is_completed=False,
    )

    # Lattice placements
    legal_db.place_in_lattice(conn, cid, "health", 5, "established",
                              "Back injury from workplace incident at Trader Joe's",
                              source="WCA 00-00000 filing", is_sensitive=True)
    legal_db.place_in_lattice(conn, cid, "work", 8, "established",
                              "Employment at Trader Joe's; injury during employment duties",
                              source="WCA 00-00000 filing")
    legal_db.place_in_lattice(conn, cid, "finance", 6, "evolving",
                              "Wage replacement and medical expense coverage under L&I",
                              source="WCA 00-00000 benefits", is_sensitive=True)
    legal_db.place_in_lattice(conn, cid, "crisis", 3, "recent",
                              "Active workers' comp claim; navigating claim process and medical treatment",
                              source="WCA 00-00000")

    return case


def seed_bankruptcy(conn) -> dict:
    """Seed bankruptcy case with March 11 schedule deadline."""
    if _case_exists(conn, "BK-2025-SCHED"):
        cur = conn.cursor()
        cur.execute("SELECT id FROM cases WHERE case_number = %s", ("BK-2025-SCHED",))
        return {"id": cur.fetchone()[0], "skipped": True}

    case = legal_db.add_case(
        conn,
        case_number="BK-2025-SCHED",
        case_type="bankruptcy",
        title="Bankruptcy Schedules Filing",
        status="pending",
        jurisdiction="US Bankruptcy Court",
        filed_date="2025-02-01",
        description="Bankruptcy petition with required schedules. "
                    "March 11 deadline for schedule completion and filing.",
    )
    cid = case["id"]

    # Events
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="deadline",
        event_date="2025-03-11",
        description="Bankruptcy schedules filing deadline",
        is_completed=True,
    )
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="filing",
        event_date="2025-02-01",
        description="Initial bankruptcy petition filed",
        is_completed=True,
    )

    # Lattice placements
    legal_db.place_in_lattice(conn, cid, "finance", 10, "immediate",
                              "Bankruptcy schedules: asset/liability disclosure required",
                              source="BK-2025-SCHED", is_sensitive=True)
    legal_db.place_in_lattice(conn, cid, "crisis", 7, "this_month",
                              "March 11 deadline for bankruptcy schedule completion",
                              source="BK-2025-SCHED")

    return case


def main():
    conn = legal_db.get_connection()
    try:
        legal_db.init_schema(conn)
        print("Schema legal_gazelle initialized.")

        wc = seed_workers_comp(conn)
        skip = wc.get("skipped", False)
        print(f"Workers' comp case WCA 00-00000: {'already exists' if skip else 'seeded'} (id={wc['id']})")

        bk = seed_bankruptcy(conn)
        skip = bk.get("skipped", False)
        print(f"Bankruptcy case BK-2025-SCHED: {'already exists' if skip else 'seeded'} (id={bk['id']})")

        print("Backfill complete.")
    finally:
        legal_db.release_connection(conn)


if __name__ == "__main__":
    main()
