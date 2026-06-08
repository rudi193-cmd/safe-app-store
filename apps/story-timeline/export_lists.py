"""Export portable book lists for library trips and reading apps."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import suggestion_store as suggestions
import timeline_db as db


GOODREADS_FIELDS = [
    "Title",
    "Author",
    "ISBN",
    "ISBN13",
    "My Rating",
    "Average Rating",
    "Publisher",
    "Number of Pages",
    "Year Published",
    "Date Read",
    "Date Added",
    "Bookshelves",
    "Exclusive Shelf",
    "My Review",
]


def _title(node: dict) -> str:
    fields = node.get("fields", {})
    return str(fields.get("title") or fields.get("name") or "").strip()


def _author(node: dict) -> str:
    return str(node.get("fields", {}).get("author") or "").strip()


def _clean_slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "books"


def _book_sort_key(node: dict) -> tuple[str, str]:
    return (_author(node).lower(), _title(node).lower())


def books_for_scope(scope: str, *, source_id: str = "") -> list[dict]:
    """Return book-like nodes for an export scope."""
    if scope == "all":
        books = db.get_nodes(type_="book")
    elif scope == "selected-source" and source_id:
        books = []
        for suggestion in suggestions.list_suggestions_for_source(
            source_id, status=suggestions.STATUS_PENDING
        ):
            fields = suggestion.get("fields", {})
            if fields.get("suggestion_kind") != "reading_recommendation":
                continue
            proposed = fields.get("proposed_fields") or {}
            title = str(proposed.get("title") or "").strip()
            if not title:
                continue
            books.append({
                "id": suggestion["id"],
                "type": "book",
                "fields": {
                    "title": title,
                    "author": str(proposed.get("author") or "").strip(),
                    "shelf": "to-read",
                    "tags": str(proposed.get("tags") or "").strip(),
                    "review": str(proposed.get("reason") or "").strip(),
                },
            })
        return sorted(books, key=_book_sort_key)
    else:
        books = [
            book for book in db.get_nodes(type_="book")
            if book.get("fields", {}).get("shelf") == "to-read"
        ]
    return sorted(books, key=_book_sort_key)


def _markdown_for_books(books: Iterable[dict], *, label: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Library Trip List: {label}",
        "",
        f"Generated: {now}",
        "",
    ]
    current_author = None
    count = 0
    for book in books:
        fields = book.get("fields", {})
        title = _title(book) or "Untitled"
        author = _author(book) or "Unknown author"
        if author != current_author:
            current_author = author
            lines += ["", f"## {author}", ""]
        extras = []
        year = str(fields.get("year") or "").strip()
        isbn = str(fields.get("isbn13") or fields.get("isbn") or "").strip()
        tags = str(fields.get("tags") or "").strip()
        if year:
            extras.append(year)
        if isbn:
            extras.append(f"ISBN {isbn}")
        if tags:
            extras.append(tags)
        suffix = f" ({'; '.join(extras)})" if extras else ""
        lines.append(f"- [ ] {title}{suffix}")
        reason = str(fields.get("review") or "").strip()
        if reason:
            lines.append(f"  - {reason}")
        count += 1
    if count == 0:
        lines.append("_No books matched this export scope._")
    return "\n".join(lines).strip() + "\n"


def _goodreads_row(book: dict) -> dict[str, str]:
    fields = book.get("fields", {})
    return {
        "Title": _title(book),
        "Author": _author(book),
        "ISBN": str(fields.get("isbn") or ""),
        "ISBN13": str(fields.get("isbn13") or ""),
        "My Rating": str(fields.get("rating") or "0"),
        "Average Rating": str(fields.get("avg_rating") or ""),
        "Publisher": str(fields.get("publisher") or ""),
        "Number of Pages": str(fields.get("pages") or ""),
        "Year Published": str(fields.get("year") or ""),
        "Date Read": str(fields.get("date_read") or ""),
        "Date Added": str(fields.get("date_added") or ""),
        "Bookshelves": str(fields.get("tags") or ""),
        "Exclusive Shelf": str(fields.get("shelf") or "to-read"),
        "My Review": str(fields.get("review") or ""),
    }


def export_bundle(
    books: list[dict],
    *,
    label: str,
    out_dir: Path | None = None,
) -> dict[str, str | int]:
    """Write a Markdown list and Goodreads-style CSV for a set of books."""
    out_dir = out_dir or Path(__file__).resolve().parent / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _clean_slug(label)
    md_path = out_dir / f"{stamp}-{slug}-library-list.md"
    csv_path = out_dir / f"{stamp}-{slug}-goodreads.csv"

    md_path.write_text(_markdown_for_books(books, label=label), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GOODREADS_FIELDS)
        writer.writeheader()
        for book in books:
            writer.writerow(_goodreads_row(book))

    return {
        "count": len(books),
        "markdown": str(md_path),
        "csv": str(csv_path),
    }
