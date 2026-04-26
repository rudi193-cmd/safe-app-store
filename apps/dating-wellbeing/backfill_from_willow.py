"""
backfill_from_willow.py -- Seed the dating_wellbeing schema with known data.

Initializes the schema, creates platform entries, and seeds foundational patterns
from known personal context. All data is_sensitive=TRUE by default.

Run once, then use wellbeing_db.py functions for ongoing inserts.
"""

import sys
sys.path.insert(0, "/mnt/c/Users/Sean/Documents/GitHub/safe-app-dating-wellbeing")

from wellbeing_db import (
    get_connection, release_connection, init_schema,
    add_pattern, place_in_lattice
)


def backfill():
    conn = get_connection()
    try:
        # 1. Initialize schema (idempotent)
        init_schema(conn)
        print("[OK] Schema dating_wellbeing initialized.")

        # 2. Seed foundational patterns
        # -- Growth mission statement
        p1 = add_pattern(
            conn,
            pattern_type="growth_note",
            description="Desire vs knowing what's good for you: the central tension in dating. "
                        "What feels exciting is not always what builds a healthy relationship. "
                        "Growth means learning to align attraction with values.",
            confidence="high",
            source_context="Personal reflection, recurring theme across platforms"
        )
        print(f"[OK] Pattern {p1['id']}: growth mission statement")

        # Place in lattice: patterns domain, deep depth, evolving temporal
        place_in_lattice(
            conn,
            entity_id=p1["id"],
            entity_type="pattern",
            domain="patterns",
            depth=15,
            temporal="evolving",
            content="Desire vs knowing what's good for you — growth mission statement",
            source="backfill_from_willow.py"
        )

        # -- Family patterns affecting dating
        p2 = add_pattern(
            conn,
            pattern_type="growth_note",
            description="German immigrant survival mechanisms: stoicism, emotional suppression, "
                        "pragmatism over feeling. These patterns pass through generations and "
                        "manifest as difficulty with emotional expression, vulnerability avoidance, "
                        "and conflating emotional distance with strength.",
            confidence="high",
            source_context="Family history, genealogy research, self-awareness work"
        )
        print(f"[OK] Pattern {p2['id']}: family patterns affecting dating")

        # Place in lattice: history domain, deep depth, established temporal
        place_in_lattice(
            conn,
            entity_id=p2["id"],
            entity_type="pattern",
            domain="history",
            depth=20,
            temporal="established",
            content="German immigrant survival mechanisms — emotional suppression, "
                    "difficulty with vulnerability, generational pattern",
            source="backfill_from_willow.py"
        )

        # Also place in relationships domain
        place_in_lattice(
            conn,
            entity_id=p2["id"],
            entity_type="pattern",
            domain="relationships",
            depth=18,
            temporal="evolving",
            content="Family patterns affecting dating: stoicism misread as disinterest, "
                    "emotional distance as default, learning to override inherited responses",
            source="backfill_from_willow.py"
        )

        # 3. Seed platform awareness (as preference patterns, no actual profiles yet)
        platforms = ["feeld", "hinge", "tinder", "match", "eharmony"]
        for plat in platforms:
            p = add_pattern(
                conn,
                pattern_type="preference",
                description=f"Active or historical presence on {plat.title()}. "
                            f"Platform-specific dynamics and user behavior tracked separately.",
                confidence="high",
                source_context=f"Known platform usage: {plat}"
            )
            print(f"[OK] Pattern {p['id']}: platform awareness — {plat}")

        print("\n[DONE] Backfill complete. 2 growth patterns + 5 platform preferences seeded.")
        print("       All data is_sensitive=TRUE. No actual profile data stored yet.")
        print("       Use wellbeing_db.add_profile() to add specific profiles when ready.")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Backfill failed: {e}")
        raise
    finally:
        release_connection(conn)


if __name__ == "__main__":
    backfill()
