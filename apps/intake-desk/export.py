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
        "SELECT c.*, s.narrator_id, s.taker_id, s.session_id, s.captured_at,"
        " s.medium, s.consent_ref"
        " FROM claims c JOIN statements s ON s.id = c.statement_id"
        " WHERE c.state = 'published' ORDER BY c.id"
    ))


def _docket_subjects(conn: sqlite3.Connection, claim_id: str) -> set[str]:
    """Every narrator named by a claim's docket, not just the claim's own.

    The router writes other people into an excerpt — "slappy says 1998;
    the-colonel says 1999" — and the docket travels with the export. Checking
    consent only for the narrators of the published claims meant a person who
    had revoked both scopes still left the vault by name, inside somebody
    else's record. Consent has to be asked of everyone the export mentions.
    """
    subjects: set[str] = set()
    for row in conn.execute(
        "SELECT source_ref FROM docket_entries WHERE claim_id=? AND source_ref LIKE 'claim:%'",
        (claim_id,),
    ):
        other = conn.execute(
            "SELECT s.narrator_id FROM claims c JOIN statements s ON s.id = c.statement_id"
            " WHERE c.id = ?",
            (row["source_ref"].split("claim:", 1)[1],),
        ).fetchone()
        if other is not None:
            subjects.add(other["narrator_id"])
    return subjects


def gather(conn: sqlite3.Connection, *, consent_store: Path | str) -> list[dict]:
    """Collect what may leave, or refuse the whole set.

    Rule 2 in one place: this raises before any caller can write a file, so
    there is no partial export to clean up and no way to get "most of it".
    """
    rows = _publishable(conn)
    if not rows:
        raise ExportRefused("nothing is published — there is nothing to export")

    mentioned = set()
    for row in rows:
        mentioned.add(row["narrator_id"])
        mentioned |= _docket_subjects(conn, row["id"])
    ungranted = {
        subject for subject in mentioned
        if not consent_mod.may_publish(consent_store, subject)
    }
    if ungranted:
        # The count, never the values. Naming who withheld consent in an error
        # message is itself a disclosure.
        raise ExportRefused(
            f"{len(ungranted)} narrator(s) in this selection have no verified "
            "publication grant. Nothing was written."
        )

    # Scoped to the narrators in this export. A global count told a recipient
    # how many times other people had withdrawn, which is a disclosure about
    # those people to someone with no relationship to them.
    placeholders = ",".join("?" * len(mentioned))
    withheld = conn.execute(
        "SELECT COUNT(*) AS n FROM claims c JOIN statements s ON s.id = c.statement_id"
        f" WHERE c.state = 'withheld' AND s.narrator_id IN ({placeholders})",
        tuple(sorted(mentioned)),
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
            # Rule 1 — the scope travels with the data, read from the
            # statement's stored consent_ref rather than re-derived, so the
            # exported block is the record rather than a restatement of it.
            "consent": {
                "subject": row["consent_ref"],
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

    if withheld:
        out.append({"_note": f"{withheld} claim(s) withheld and not exported"})
    return out


def _note_export(conn: sqlite3.Connection, consent_store, records: list[dict]) -> None:
    """Append to the disclosure chain — after the write, not before.

    Recording the export first meant a failed write left a permanent record of
    an export that never happened.
    """
    counts: dict[str, int] = {}
    for rec in records:
        if "_note" in rec:
            continue
        counts[rec["narrator"]] = counts.get(rec["narrator"], 0) + 1
    for narrator, n in sorted(counts.items()):
        consent_mod.note_disclosure(consent_store, narrator, "exported", f"{n} claim(s)")


def to_json(conn: sqlite3.Connection, *, consent_store: Path | str, path: Path | str) -> Path:
    records = gather(conn, consent_store=consent_store)
    dest = Path(path)
    dest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    _note_export(conn, consent_store, records)
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
    _note_export(conn, consent_store, records)
    return dest
