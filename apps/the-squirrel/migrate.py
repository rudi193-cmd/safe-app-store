"""
migrate.py -- One-shot schema init and source registry seed for The Squirrel.

Creates all tables in the_squirrel schema and seeds source_registry from
data/community_history_archives.json.

Safe to run multiple times (idempotent).
"""

from db import get_connection, release_connection
import db.persons as persons_db
import db.fragments as fragments_db
import db.sources as sources_db
import db.events as events_db
import db.media as media_db


def main():
    conn = get_connection()
    try:
        print("Creating schema: the_squirrel")
        persons_db.init_schema(conn)
        print("  ✓ persons, relationships, person_lattice_cells, person_sources")

        fragments_db.init_schema(conn)
        print("  ✓ fragments, tree_branches, fragment_lattice_cells")

        sources_db.init_schema(conn)
        print("  ✓ source_registry (FTS index)")

        events_db.init_schema(conn)
        print("  ✓ events")

        media_db.init_schema(conn)
        print("  ✓ media")

        print("\nSeeding source_registry from community_history_archives.json...")
        inserted = sources_db.seed_from_json(conn)
        print(f"  ✓ {inserted} new entries inserted")

        print("\nMigration complete.")
    finally:
        release_connection(conn)


if __name__ == "__main__":
    main()
