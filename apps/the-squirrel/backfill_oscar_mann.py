"""
backfill_oscar_mann.py -- Insert the Oscar Mann family into the squirrel database.

Uses db.persons to populate persons, relationships, lattice cells, and sources.
Idempotent: checks for existing persons by name before inserting.
"""

import sap.core.gate
import db.persons as persons_db
from db import get_connection, release_connection


def _get_or_create(conn, **kwargs):
    """Return existing person dict if name matches, otherwise create new."""
    existing = persons_db.search_persons(conn, kwargs["full_name"])
    exact = [p for p in existing if p["full_name"] == kwargs["full_name"]]
    if exact:
        return exact[0]
    return persons_db.add_person(conn, **kwargs)


def main():
    conn = get_connection()
    try:
        persons_db.init_schema(conn)

        _bypass = "trusted backfill: Oscar Mann family from FindAGrave memorial 273702757"
        with sap.core.gate.bypass(_bypass):

            # ------------------------------------------------------------------
            # Persons
            # ------------------------------------------------------------------

            oscar = _get_or_create(
                conn,
                full_name="Oscar William Mann",
                birth_date="1929-01-11",
                birth_place="Willmar, Minnesota",
                death_date="2024-09-09",
                death_place="Albuquerque, New Mexico",
                burial_place="Santa Fe National Cemetery, Santa Fe, New Mexico",
                memorial_id="273702757",
                memorial_url="https://www.findagrave.com/memorial/273702757/oscar-william-mann",
                bio=(
                    "Oscar William Mann, born January 11, 1929, in Willmar, Minnesota. "
                    "Son of William M. Mann and Meta D. Johnson. Married Grace for 69 years. "
                    "Served in the military, traveled all 50 US states and 34 countries. "
                    "Moved to Albuquerque in 1973. The surname Mau was changed to Mann at Ellis Island. "
                    "Died September 9, 2024, in Albuquerque, New Mexico."
                ),
            )

            grace = _get_or_create(
                conn,
                full_name="Grace Mann",
                bio="Wife of Oscar William Mann. Married 69 years.",
            )

            william = _get_or_create(
                conn,
                full_name="William M. Mann",
                bio="Father of Oscar William Mann. Surname originally Mau, changed to Mann at Ellis Island.",
            )

            meta = _get_or_create(
                conn,
                full_name="Meta D. Johnson",
                bio="Mother of Oscar William Mann.",
            )

            siblings = []
            for i in range(1, 9):
                sib = _get_or_create(
                    conn,
                    full_name=f"Sibling {i} of Oscar Mann",
                    bio=f"Sibling #{i} of Oscar William Mann. One of 8 siblings.",
                )
                siblings.append(sib)

            karl = _get_or_create(
                conn, full_name="Karl Mann",
                bio="Son of Oscar William Mann and Grace Mann.",
            )
            kristine = _get_or_create(
                conn, full_name="Kristine Mann",
                bio="Daughter of Oscar William Mann and Grace Mann.",
            )
            audrey = _get_or_create(
                conn, full_name="Audrey Mann",
                bio="Daughter of Oscar William Mann and Grace Mann.",
            )
            doris = _get_or_create(
                conn, full_name="Doris Mann",
                bio="Daughter of Oscar William Mann and Grace Mann.",
            )
            children = [karl, kristine, audrey, doris]

            # ------------------------------------------------------------------
            # Relationships
            # ------------------------------------------------------------------

            persons_db.add_relationship(conn, oscar["id"], grace["id"], "spouse")
            persons_db.add_relationship(conn, oscar["id"], william["id"], "child")
            persons_db.add_relationship(conn, william["id"], oscar["id"], "parent")
            persons_db.add_relationship(conn, oscar["id"], meta["id"], "child")
            persons_db.add_relationship(conn, meta["id"], oscar["id"], "parent")

            for sib in siblings:
                persons_db.add_relationship(conn, oscar["id"], sib["id"], "sibling")

            for child in children:
                persons_db.add_relationship(conn, oscar["id"], child["id"], "parent")
                persons_db.add_relationship(conn, child["id"], oscar["id"], "child")
                persons_db.add_relationship(conn, grace["id"], child["id"], "parent")
                persons_db.add_relationship(conn, child["id"], grace["id"], "child")

            # ------------------------------------------------------------------
            # Lattice cells
            # ------------------------------------------------------------------

            src = "FindAGrave memorial 273702757"

            persons_db.place_in_lattice(conn, oscar["id"], "identity", 1, "permanent",
                                        "Oscar William Mann", src)
            persons_db.place_in_lattice(conn, oscar["id"], "history", 1, "permanent",
                                        "Born 1929-01-11, Willmar MN. Died 2024-09-09, Albuquerque NM.", src)
            persons_db.place_in_lattice(conn, oscar["id"], "location", 1, "permanent",
                                        "Willmar, Minnesota (birthplace)", src)
            persons_db.place_in_lattice(conn, oscar["id"], "location", 2, "established",
                                        "Albuquerque, New Mexico (since 1973)", src)
            persons_db.place_in_lattice(conn, oscar["id"], "relationships", 1, "permanent",
                                        "Husband, father of 4, son, brother (8 siblings)", src)
            persons_db.place_in_lattice(conn, oscar["id"], "celebrations", 1, "permanent",
                                        "Married Grace for 69 years", src)
            persons_db.place_in_lattice(conn, oscar["id"], "history", 2, "archived",
                                        "Traveled all 50 US states and 34 countries", src)
            persons_db.place_in_lattice(conn, oscar["id"], "history", 3, "archived",
                                        "Surname Mau changed to Mann at Ellis Island", src)

            persons_db.place_in_lattice(conn, grace["id"], "identity", 1, "permanent", "Grace Mann")
            persons_db.place_in_lattice(conn, grace["id"], "relationships", 1, "permanent",
                                        "Wife of Oscar William Mann, mother of 4")
            persons_db.place_in_lattice(conn, grace["id"], "celebrations", 1, "permanent",
                                        "Married Oscar for 69 years")

            persons_db.place_in_lattice(conn, william["id"], "identity", 1, "permanent", "William M. Mann")
            persons_db.place_in_lattice(conn, william["id"], "relationships", 1, "permanent",
                                        "Father of Oscar William Mann")
            persons_db.place_in_lattice(conn, william["id"], "history", 1, "archived",
                                        "Surname originally Mau, changed to Mann at Ellis Island")

            persons_db.place_in_lattice(conn, meta["id"], "identity", 1, "permanent", "Meta D. Johnson")
            persons_db.place_in_lattice(conn, meta["id"], "relationships", 1, "permanent",
                                        "Mother of Oscar William Mann")

            for child in children:
                persons_db.place_in_lattice(conn, child["id"], "identity", 1, "permanent", child["full_name"])
                persons_db.place_in_lattice(conn, child["id"], "relationships", 1, "permanent",
                                            "Child of Oscar William Mann and Grace Mann")

            for sib in siblings:
                persons_db.place_in_lattice(conn, sib["id"], "identity", 1, "permanent", sib["full_name"])
                persons_db.place_in_lattice(conn, sib["id"], "relationships", 1, "permanent",
                                            "Sibling of Oscar William Mann")

            # ------------------------------------------------------------------
            # Sources
            # ------------------------------------------------------------------

            persons_db.add_source(
                conn,
                person_id=oscar["id"],
                source_type="findagrave",
                url="https://www.findagrave.com/memorial/273702757/oscar-william-mann",
                title="Oscar William Mann - Find a Grave Memorial",
                content="FindAGrave memorial #273702757 for Oscar William Mann (1929-2024)",
            )

            print(f"Backfill complete. Oscar id={oscar['id']}, "
                  f"{len(children)} children, {len(siblings)} siblings inserted.")

    finally:
        release_connection(conn)


if __name__ == "__main__":
    main()
