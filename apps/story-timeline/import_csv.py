"""
import_csv.py — Import reading history into story-timeline from CSV exports.

Supported sources (auto-detected from headers):
  - Goodreads  (File > Export Library)
  - StoryGraph (Export Data)
  - LibraryThing (Export > Tab-delimited)

Usage:
  python3 import_csv.py <file.csv>
  python3 import_csv.py <file.csv> --source goodreads
  python3 import_csv.py <file.csv> --authors       # also create Author nodes + edges
  python3 import_csv.py <file.csv> --dry-run       # preview without writing

Dedup: re-running is safe. Books are keyed by hash(title+author) — duplicates skipped.
"""
import argparse
import csv
import hashlib
import sys
from pathlib import Path
from typing import Optional

import timeline_db as db
import willow_edges


# ── Shelf normalisation ───────────────────────────────────────────────────────

_SHELF_MAP = {
    # Goodreads
    "read": "read",
    "currently-reading": "currently-reading",
    "to-read": "to-read",
    # StoryGraph
    "read": "read",
    "currently reading": "currently-reading",
    "to read": "to-read",
    "did not finish": "dnf",
    # LibraryThing collections
    "currently reading": "currently-reading",
    "to read": "to-read",
    "read but unowned": "read",
}


def _normalise_shelf(raw: str) -> str:
    return _SHELF_MAP.get(raw.strip().lower(), "read")


def _normalise_rating(raw: str) -> int:
    try:
        v = int(float(raw.strip()))
        return v if 1 <= v <= 5 else 0
    except (ValueError, AttributeError):
        return 0


def _strip_isbn(raw: str) -> str:
    return raw.strip().strip("=").strip('"').strip("'")


def _import_id(title: str, author: str) -> str:
    key = f"{title.strip().lower()}|{author.strip().lower()}".encode()
    return "imported-" + hashlib.md5(key).hexdigest()[:16]


# ── Format detection ──────────────────────────────────────────────────────────

def detect_source(headers: list[str]) -> str:
    h = {h.strip().lower() for h in headers}
    if "exclusive shelf" in h or "bookshelves" in h:
        return "goodreads"
    if "read status" in h or "star rating" in h:
        return "storygraph"
    if "collections" in h and "date" in h:
        return "librarything"
    return "goodreads"  # fallback


# ── Row parsers ───────────────────────────────────────────────────────────────

def _parse_goodreads(row: dict) -> Optional[dict]:
    title = row.get("Title", "").strip()
    author = row.get("Author", "").strip()
    if not title:
        return None
    return {
        "title": title,
        "author": author,
        "isbn": _strip_isbn(row.get("ISBN", "")),
        "isbn13": _strip_isbn(row.get("ISBN13", "")),
        "rating": _normalise_rating(row.get("My Rating", "0")),
        "avg_rating": row.get("Average Rating", "").strip(),
        "publisher": row.get("Publisher", "").strip(),
        "pages": row.get("Number of Pages", "").strip(),
        "year": row.get("Year Published", "").strip(),
        "date_read": row.get("Date Read", "").strip(),
        "date_added": row.get("Date Added", "").strip(),
        "shelf": _normalise_shelf(row.get("Exclusive Shelf", "read")),
        "tags": row.get("Bookshelves", "").strip(),
        "review": row.get("My Review", "").strip(),
    }


def _parse_storygraph(row: dict) -> Optional[dict]:
    title = row.get("Title", "").strip()
    author = row.get("Authors", row.get("Author", "")).strip()
    if not title:
        return None
    return {
        "title": title,
        "author": author,
        "isbn": _strip_isbn(row.get("ISBN/UID", row.get("ISBN", ""))),
        "isbn13": "",
        "rating": _normalise_rating(row.get("Star Rating", "0")),
        "avg_rating": "",
        "publisher": "",
        "pages": row.get("Number of Pages", "").strip(),
        "year": "",
        "date_read": row.get("Last Date Read", row.get("Date Read", "")).strip(),
        "date_added": row.get("Date Added", "").strip(),
        "shelf": _normalise_shelf(row.get("Read Status", "read")),
        "tags": row.get("Tags", "").strip(),
        "review": row.get("Review", "").strip(),
    }


def _parse_librarything(row: dict) -> Optional[dict]:
    title = row.get("Title", "").strip()
    author = row.get("Author", row.get("Primary Author", "")).strip()
    if not title:
        return None
    collections = row.get("Collections", "").lower()
    if "currently reading" in collections:
        shelf = "currently-reading"
    elif "to read" in collections or "wishlist" in collections:
        shelf = "to-read"
    else:
        shelf = "read"
    return {
        "title": title,
        "author": author,
        "isbn": _strip_isbn(row.get("ISBN", "")),
        "isbn13": "",
        "rating": _normalise_rating(row.get("Rating", "0")),
        "avg_rating": "",
        "publisher": row.get("Publisher", "").strip(),
        "pages": row.get("Pages", "").strip(),
        "year": row.get("Date", row.get("Original Publication Date", "")).strip(),
        "date_read": row.get("Date Read", "").strip(),
        "date_added": row.get("Entry Date", "").strip(),
        "shelf": shelf,
        "tags": row.get("Tags", "").strip(),
        "review": row.get("Review", row.get("Private Comment", "")).strip(),
    }


_PARSERS = {
    "goodreads": _parse_goodreads,
    "storygraph": _parse_storygraph,
    "librarything": _parse_librarything,
}


# ── Existing import ID set ────────────────────────────────────────────────────

def _existing_import_ids() -> set:
    return {n["id"] for n in db.get_nodes() if n["id"].startswith("imported-")}


# ── Main import ───────────────────────────────────────────────────────────────

def run_import(
    csv_path: Path,
    source: Optional[str] = None,
    create_authors: bool = False,
    dry_run: bool = False,
    uuid: Optional[str] = None,
) -> dict:
    existing = _existing_import_ids()
    results = {"imported": 0, "skipped": 0, "errors": 0, "author_nodes": 0, "edges": 0}

    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        fmt = source or detect_source(headers)
        parser = _PARSERS.get(fmt, _parse_goodreads)

        for row in reader:
            try:
                parsed = parser(row)
            except Exception as e:
                sys.stderr.write(f"  error parsing row: {e}\n")
                results["errors"] += 1
                continue

            if not parsed:
                results["skipped"] += 1
                continue

            node_id = _import_id(parsed["title"], parsed["author"])

            if node_id in existing:
                results["skipped"] += 1
                continue

            fields = {k: v for k, v in parsed.items() if v not in ("", None, 0)}

            if not dry_run:
                db.add_node_with_id(node_id, type_="book", fields=fields)
                existing.add(node_id)
            results["imported"] += 1

            if create_authors and parsed.get("author"):
                author_id = _import_id(parsed["author"], "__author__")
                if author_id not in existing:
                    if not dry_run:
                        db.add_node_with_id(
                            author_id, type_="author",
                            fields={"name": parsed["author"]}
                        )
                        existing.add(author_id)
                    results["author_nodes"] += 1
                if not dry_run and uuid:
                    willow_edges.add_edge(node_id, author_id, "written_by", uuid=uuid)
                results["edges"] += 1

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import reading history from Goodreads/StoryGraph/LibraryThing CSV"
    )
    parser.add_argument("file", type=Path, help="CSV export file")
    parser.add_argument(
        "--source", choices=["goodreads", "storygraph", "librarything"],
        help="Force source format (auto-detected if omitted)"
    )
    parser.add_argument(
        "--authors", action="store_true",
        help="Also create Author nodes and written_by edges"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview import counts without writing anything"
    )
    args = parser.parse_args()

    if not args.file.exists():
        sys.exit(f"File not found: {args.file}")

    import safe_integration
    uuid = safe_integration.get_user_uuid()

    if args.dry_run:
        print("Dry run — nothing will be written.")

    results = run_import(
        csv_path=args.file,
        source=args.source,
        create_authors=args.authors,
        dry_run=args.dry_run,
        uuid=uuid,
    )

    print(f"Imported : {results['imported']} book(s)")
    print(f"Skipped  : {results['skipped']} (already present or empty)")
    print(f"Errors   : {results['errors']}")
    if args.authors:
        print(f"Authors  : {results['author_nodes']} node(s) created")
        print(f"Edges    : {results['edges']} written_by edge(s)")
    if args.dry_run:
        print("(Dry run — no changes made)")


if __name__ == "__main__":
    main()
