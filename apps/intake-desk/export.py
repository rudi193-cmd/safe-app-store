"""Egress — and the thing that must not happen.

A corpus of consented, sourced, human-narrated testimony is the most valuable
training asset there is, and the moment a desk works someone will offer to buy
it. `stores/README.md` already answers this — *the capability travels; the
corpus does not* — but a README enforces nothing. This module is where that
sentence becomes a gate.

Four rules (spec §9):

  1. Consent scope travels inside the export. A format that cannot carry it
     is not offered.
  2. Bulk export fails closed. One claim without a verified publication grant
     refuses the WHOLE export, and names the count — never the values.
  3. `withheld` never exports. Checked here, at egress, not at ruling time.
  4. Every export appends to the disclosure chain a narrator can read.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import consent as consent_mod
from desk import quoted


class ExportRefused(Exception):
    """Fail-closed. The desk declines the whole export rather than part of it."""


def _publishable(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT c.*, s.narrator_id, s.taker_id, s.session_id, s.captured_at, s.medium"
        " FROM claims c JOIN statements s ON s.id = c.statement_id"
        " WHERE c.state = 'published' ORDER BY c.id"
    ))


def gather(conn: sqlite3.Connection, *, consent_store: Path | str) -> list[dict]:
    """Collect what may leave, or refuse the whole set.

    Rule 2 in one place: this raises before any caller can write a file, so
    there is no partial export to clean up and no way to get "most of it".
    """
    rows = _publishable(conn)
    if not rows:
        raise ExportRefused("nothing is published — there is nothing to export")

    ungranted = {
        row["narrator_id"] for row in rows
        if not consent_mod.may_publish(consent_store, row["narrator_id"])
    }
    if ungranted:
        # The count, never the values. Naming who withheld consent in an error
        # message is itself a disclosure.
        raise ExportRefused(
            f"{len(ungranted)} narrator(s) in this selection have no verified "
            "publication grant. Nothing was written."
        )

    withheld = conn.execute(
        "SELECT COUNT(*) AS n FROM claims WHERE state = 'withheld'"
    ).fetchone()["n"]

    out = []
    for row in rows:
        out.append({
            "claim_id": row["id"],
            "assertion": row["assertion"],
            "quoted": quoted(conn, row["id"]),
            "narrator": row["narrator_id"],
            "taker": row["taker_id"],
            "ruled_by": row["ruled_by"],
            "ruled_at": row["ruled_at"],
            "confidence": row["confidence"],
            "source_type": row["source_type"],
            "occurred_at": row["occurred_at"],
            "place": row["place"],
            "corrections": json.loads(row["corrections"]),
            # Rule 1 — the scope travels with the data.
            "consent": {
                "subject": row["narrator_id"],
                "scope": consent_mod.PUBLICATION,
                "verified_at_export": True,
            },
            "docket": [
                {"relation": d["relation"], "source_kind": d["source_kind"],
                 "source_ref": d["source_ref"], "excerpt": d["excerpt"]}
                for d in conn.execute(
                    "SELECT * FROM docket_entries WHERE claim_id=? ORDER BY created_at",
                    (row["id"],))
            ],
        })

    for narrator in {row["narrator_id"] for row in rows}:
        consent_mod.note_disclosure(
            consent_store, narrator, "exported",
            f"{sum(1 for r in rows if r['narrator_id'] == narrator)} claim(s)",
        )
    if withheld:
        out.append({"_note": f"{withheld} claim(s) withheld and not exported"})
    return out


def to_json(conn: sqlite3.Connection, *, consent_store: Path | str, path: Path | str) -> Path:
    records = gather(conn, consent_store=consent_store)
    dest = Path(path)
    dest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return dest


def to_markdown(conn: sqlite3.Connection, *, consent_store: Path | str, path: Path | str) -> Path:
    """Readable, cited. A format that strips provenance is a different product."""
    records = gather(conn, consent_store=consent_store)
    lines = ["# Testimony", ""]
    for rec in records:
        if "_note" in rec:
            lines += [f"> {rec['_note']}", ""]
            continue
        lines += [
            f"## {rec['assertion']}",
            "",
            f"> {rec['quoted']}",
            "",
            f"— **{rec['narrator']}**"
            + (f", {rec['occurred_at']}" if rec["occurred_at"] else "")
            + (f", {rec['place']}" if rec["place"] else ""),
            "",
            f"Confidence: `{rec['confidence']}` · witnessed by `{rec['ruled_by']}` "
            f"· source type: `{rec['source_type']}`",
            "",
        ]
        for d in rec["docket"]:
            lines.append(f"- *{d['relation']}* ({d['source_kind']}): {d['source_ref'] or ''}")
        if rec["docket"]:
            lines.append("")
    dest = Path(path)
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest
