"""
Paperclip Cube DB Reader
========================
Read-only SQLite adapter for operation_paperclip_genealogy data.
Connects the genealogical receipts to modern defense contractors.
"""

import sqlite3
import sys
import os

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "paperclip_cube.db")


class PaperclipReader:
    """Read-only access to the Paperclip cube database."""

    def __init__(self, db_path=None):
        self.db_path = db_path or os.environ.get("PAPERCLIP_DB", DEFAULT_DB)
        self._conn = None

    def __enter__(self):
        uri = f"file:{self.db_path}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, *args):
        if self._conn:
            self._conn.close()
            self._conn = None

    def search_persons(self, name=None, employer=None, field=None, generation=None):
        """Search persons with flexible filters."""
        conditions = []
        params = []
        if name:
            conditions.append("(full_name LIKE ? OR last_name LIKE ?)")
            params.extend([f"%{name}%", f"%{name}%"])
        if employer:
            conditions.append("(employer LIKE ? OR notes LIKE ?)")
            params.extend([f"%{employer}%", f"%{employer}%"])
        if field:
            conditions.append("field LIKE ?")
            params.append(f"%{field}%")
        if generation is not None:
            conditions.append("generation = ?")
            params.append(generation)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT id, full_name, generation, field, occupation, employer,
                   current_location, birth_year, death_year, notes
            FROM pp_persons
            WHERE {where}
            ORDER BY full_name
        """
        try:
            rows = self._conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            print(f"[paperclip] search error: {e}", file=sys.stderr)
            return []

    def find_contractor_lineage(self, contractor_name):
        """Find Paperclip persons connected to a modern defense contractor.

        Searches through three paths:
        1. employer field on pp_persons
        2. pp_affiliations -> pp_institutions by name
        3. notes field mentioning the contractor
        """
        results = []

        # Path 1: Direct employer match
        employer_matches = self.search_persons(employer=contractor_name)
        for p in employer_matches:
            p["match_path"] = "employer"
        results.extend(employer_matches)

        # Path 2: Affiliation -> Institution match
        try:
            rows = self._conn.execute("""
                SELECT p.id, p.full_name, p.generation, p.field, p.occupation,
                       p.employer, p.current_location, p.birth_year, p.notes,
                       i.name as institution_name, a.role as affil_role
                FROM pp_persons p
                JOIN pp_affiliations a ON p.id = a.person_id
                JOIN pp_institutions i ON a.institution_id = i.id
                WHERE i.name LIKE ?
                ORDER BY p.full_name
            """, (f"%{contractor_name}%",)).fetchall()
            for r in rows:
                d = dict(r)
                d["match_path"] = "affiliation"
                # Deduplicate by person id
                if not any(x.get("id") == d["id"] for x in results):
                    results.append(d)
        except sqlite3.Error as e:
            print(f"[paperclip] affiliation search error: {e}", file=sys.stderr)

        # Path 3: Notes mention
        try:
            seen_ids = [r["id"] for r in results]
            if seen_ids:
                placeholders = ",".join("?" for _ in seen_ids)
                exclude_clause = f"AND id NOT IN ({placeholders})"
                params = [f"%{contractor_name}%"] + seen_ids
            else:
                exclude_clause = ""
                params = [f"%{contractor_name}%"]
            rows = self._conn.execute(f"""
                SELECT id, full_name, generation, field, occupation,
                       employer, current_location, birth_year, notes
                FROM pp_persons
                WHERE notes LIKE ? {exclude_clause}
            """, params).fetchall()
            for r in rows:
                d = dict(r)
                d["match_path"] = "notes"
                if not any(x.get("id") == d["id"] for x in results):
                    results.append(d)
        except sqlite3.Error as e:
            print(f"[paperclip] notes search error: {e}", file=sys.stderr)

        return results

    def get_institution_affiliates(self, institution_name):
        """Get all persons affiliated with a named institution."""
        try:
            rows = self._conn.execute("""
                SELECT p.id, p.full_name, p.generation, p.field,
                       a.role, a.affil_type, a.notes as affil_notes
                FROM pp_persons p
                JOIN pp_affiliations a ON p.id = a.person_id
                JOIN pp_institutions i ON a.institution_id = i.id
                WHERE i.name LIKE ?
                ORDER BY p.generation, p.full_name
            """, (f"%{institution_name}%",)).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            print(f"[paperclip] institution search error: {e}", file=sys.stderr)
            return []

    def stats(self):
        """Quick stats on the database."""
        try:
            counts = {}
            for table in ["pp_persons", "pp_institutions", "pp_affiliations", "pp_relations"]:
                row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = row[0]
            gen_counts = self._conn.execute(
                "SELECT generation, COUNT(*) FROM pp_persons GROUP BY generation"
            ).fetchall()
            counts["by_generation"] = {r[0]: r[1] for r in gen_counts}
            return counts
        except sqlite3.Error as e:
            print(f"[paperclip] stats error: {e}", file=sys.stderr)
            return {}
