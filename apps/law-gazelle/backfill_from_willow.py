"""
backfill_from_willow.py -- Seed the legal_gazelle schema with synthetic demo data.

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
    """Seed WCA 00-00000: synthetic workers' comp demo claim."""
    if _case_exists(conn, "WCA 00-00000"):
        cur = conn.cursor()
        cur.execute("SELECT id FROM cases WHERE case_number = %s", ("WCA 00-00000",))
        return {"id": cur.fetchone()[0], "skipped": True}

    case = legal_db.add_case(
        conn,
        case_number="WCA 00-00000",
        case_type="workers_comp",
        title="Workers' Comp - Demo Workplace Injury",
        status="open",
        jurisdiction="Example State Workers' Compensation Administration",
        filed_date="2099-01-01",
        description="Synthetic workers' compensation claim for demo workflow coverage.",
    )
    cid = case["id"]

    # Documents
    legal_db.add_document(
        conn,
        case_id=cid,
        doc_type="research",
        title="Deep Dive Workers' Comp Legal Research.pdf",
        content_summary="Synthetic legal research summary on example workers' compensation law, "
                        "claim procedures, benefit calculations, and appeal processes.",
    )
    legal_db.add_document(
        conn,
        case_id=cid,
        doc_type="research",
        title="Healthcare and Workers' Comp Effects.pdf",
        content_summary="Synthetic analysis of healthcare impacts from workers' compensation injuries.",
    )

    # Events
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="filing",
        event_date="2099-01-01",
        description="Synthetic workers' compensation claim filed",
        is_completed=True,
    )
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="mediation",
        event_date="2099-02-15",
        description="Synthetic mediation response deadline",
        is_completed=True,
    )
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="decision",
        event_date="2099-03-01",
        description="Administrative closure notice review",
        is_completed=False,
    )

    # Lattice placements
    legal_db.place_in_lattice(conn, cid, "health", 5, "established",
                              "Synthetic workplace injury fact",
                              source="WCA 00-00000 filing", is_sensitive=True)
    legal_db.place_in_lattice(conn, cid, "work", 8, "established",
                              "Synthetic employment relationship fact",
                              source="WCA 00-00000 filing")
    legal_db.place_in_lattice(conn, cid, "finance", 6, "evolving",
                              "Synthetic wage replacement and medical expense coverage",
                              source="WCA 00-00000 benefits", is_sensitive=True)
    legal_db.place_in_lattice(conn, cid, "crisis", 3, "recent",
                              "Synthetic workers' comp claim workflow",
                              source="WCA 00-00000")

    return case


def seed_bankruptcy(conn) -> dict:
    """Seed bankruptcy case with synthetic schedule deadline."""
    if _case_exists(conn, "BK-0000-DEMO"):
        cur = conn.cursor()
        cur.execute("SELECT id FROM cases WHERE case_number = %s", ("BK-0000-DEMO",))
        return {"id": cur.fetchone()[0], "skipped": True}

    case = legal_db.add_case(
        conn,
        case_number="BK-0000-DEMO",
        case_type="bankruptcy",
        title="Bankruptcy Schedules Filing",
        status="pending",
        jurisdiction="US Bankruptcy Court",
        filed_date="2099-02-01",
        description="Synthetic bankruptcy matter with required schedules.",
    )
    cid = case["id"]

    # Events
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="deadline",
        event_date="2099-03-11",
        description="Synthetic bankruptcy schedules filing deadline",
        is_completed=True,
    )
    legal_db.add_event(
        conn,
        case_id=cid,
        event_type="filing",
        event_date="2099-02-01",
        description="Synthetic bankruptcy petition filed",
        is_completed=True,
    )

    # Lattice placements
    legal_db.place_in_lattice(conn, cid, "finance", 10, "immediate",
                              "Synthetic bankruptcy schedules: asset/liability disclosure required",
                              source="BK-0000-DEMO", is_sensitive=True)
    legal_db.place_in_lattice(conn, cid, "crisis", 7, "this_month",
                              "Synthetic deadline for bankruptcy schedule completion",
                              source="BK-0000-DEMO")

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
        print(f"Bankruptcy case BK-0000-DEMO: {'already exists' if skip else 'seeded'} (id={bk['id']})")

        print("Backfill complete.")
    finally:
        legal_db.release_connection(conn)


if __name__ == "__main__":
    main()
