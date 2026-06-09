"""Document translation pipeline: split → Jeles semantic search → candidates."""
from __future__ import annotations

import re
from pathlib import Path

from . import db, mcp_client


def _split_segments(text: str) -> list[str]:
    """Paragraphs first; fall back to sentences for short texts."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) >= 3:
        return paragraphs
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _detect_lang(atom: dict) -> str:
    title = atom.get("title", "")
    if "| es" in title.lower():
        return "es"
    if "| en" in title.lower():
        return "en"
    content = atom.get("content", atom.get("text", ""))
    es_words = {"el", "la", "los", "las", "un", "una", "de", "que", "en", "es", "con", "por", "para"}
    words = set(content.lower().split()[:30])
    return "es" if len(words & es_words) >= 3 else "en"


def _best_candidate(atoms: list[dict], target_lang: str) -> tuple[str, float, str]:
    """Return (candidate_text, score, atom_id) preferring target_lang."""
    for atom in atoms:
        if _detect_lang(atom) == target_lang:
            return (
                atom.get("content", atom.get("text", "")),
                float(atom.get("score", atom.get("certainty", atom.get("similarity", 0.0))) or 0.0),
                atom.get("id", ""),
            )
    if atoms:
        a = atoms[0]
        return (
            a.get("content", a.get("text", "")),
            float(a.get("score", a.get("certainty", a.get("similarity", 0.0))) or 0.0),
            a.get("id", ""),
        )
    return "", 0.0, ""


def translate_document(
    path: str,
    source_lang: str = "en",
    target_lang: str = "es",
    search_limit: int = 5,
) -> dict:
    """
    Load a document, split into segments, find Jeles semantic matches,
    store candidates, return the document record.
    """
    db.init_db()

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Not found: {path}")

    text = p.read_text(encoding="utf-8")
    segments_text = _split_segments(text)
    doc = db.create_document(
        title=p.stem,
        source_lang=source_lang,
        target_lang=target_lang,
        source_path=str(p.resolve()),
    )

    print(f"Document: {doc['title']!r}  ({len(segments_text)} segments)")
    print("Querying Jeles for candidates...\n")

    if not mcp_client.ensure_started():
        raise RuntimeError(f"MCP unavailable: {mcp_client.last_error()}")

    for i, src in enumerate(segments_text):
        raw = mcp_client.jeles_search(query=src, limit=search_limit)
        atoms: list[dict] = []
        if isinstance(raw, list):
            atoms = raw
        elif isinstance(raw, dict):
            atoms = raw.get("results", raw.get("atoms", []))

        candidate, score, atom_id = _best_candidate(atoms, target_lang)
        db.create_segment(
            document_id=doc["id"],
            position=i,
            source_text=src,
            candidate=candidate,
            jeles_score=score,
            atom_id=atom_id,
        )

        flag = "✓" if score >= 0.75 else ("?" if score >= 0.5 else "!")
        preview = (candidate[:60] + "…") if len(candidate) > 60 else candidate
        print(f"  [{flag}] {i+1:3d}/{len(segments_text)}  score={score:.2f}  {preview!r}")

    db.update_document_status(doc["id"], "pending_review")
    print(f"\nDocument id: {doc['id']}")
    print("Run: semantic-translator review  to start the review queue")
    return doc


def export_document(doc_id: str, output_path: str | None = None) -> str:
    """Assemble verified segments into output text."""
    segments = db.get_segments(doc_id)
    if not segments:
        raise ValueError(f"Document not found or has no segments: {doc_id}")

    lines = []
    unverified = 0
    for seg in segments:
        if seg["status"] == "verified" and seg["candidate"]:
            lines.append(seg["candidate"])
        else:
            lines.append(f"[PENDING: {seg['source_text'][:80]}]")
            unverified += 1

    text = "\n\n".join(lines)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        print(f"Exported to: {output_path}  ({unverified} segments still pending)")
    return text
