"""Ingest scraped segments into Jeles via MCP."""
from __future__ import annotations

import json
import pathlib
import time

from . import mcp_client


def ingest(
    corpus_path: str = "data/corpus.jsonl",
    log_path: str = "data/ingest_log.jsonl",
    delay: float = 0.15,
) -> dict:
    if not mcp_client.ensure_started():
        raise RuntimeError(f"MCP unavailable: {mcp_client.last_error()}")

    corpus = pathlib.Path(corpus_path)
    if not corpus.exists():
        raise FileNotFoundError(f"Corpus not found: {corpus_path}  — run: scrape first")

    file_size = corpus.stat().st_size
    corpus_abs = str(corpus.resolve())

    print(f"Registering corpus ({file_size:,} bytes)...")
    reg = mcp_client.jeles_register(
        jsonl_path=corpus_abs,
        session_id="semantic-translator-ingest-001",
        file_size=file_size,
    )
    jsonl_id = reg.get("id") if isinstance(reg, dict) else str(reg)
    print(f"  jsonl_id: {jsonl_id}\n")

    segments: list[dict] = []
    with open(corpus, encoding="utf-8") as f:
        for line in f:
            segments.append(json.loads(line))

    log_path_obj = pathlib.Path(log_path)
    log_path_obj.parent.mkdir(parents=True, exist_ok=True)

    passed = 0
    blocked = 0
    errors = 0

    with open(log_path, "w", encoding="utf-8") as log:
        for i, seg in enumerate(segments):
            # Frame each atom with full context so the gate has provenance
            content = (
                f"[{seg['lang'].upper()}] Lesson: {seg['lesson']}\n"
                f"Grade: {seg.get('grade', 'N/A')}  Subject: {seg.get('subject', 'N/A')}\n"
                f"Bilingual: {seg['is_bilingual']}\n\n"
                f"{seg['text']}"
            )
            entry: dict = {"seg_id": seg["id"], "jsonl_id": jsonl_id}
            try:
                result = mcp_client.jeles_extract(
                    jsonl_id=jsonl_id,
                    content=content,
                    title=f"{seg['lesson']} | {seg['lang']}",
                    domain="translation",
                    certainty=0.95,
                    depth=1,
                )
                is_blocked = isinstance(result, dict) and result.get("blocked")
                entry["blocked"] = is_blocked
                entry["result"] = result
                if is_blocked:
                    blocked += 1
                    entry["failed"] = result.get("failed_conditions", []) if isinstance(result, dict) else []
                else:
                    passed += 1
            except Exception as exc:
                entry["blocked"] = True
                entry["error"] = str(exc)
                errors += 1

            log.write(json.dumps(entry) + "\n")
            log.flush()

            if (i + 1) % 20 == 0:
                pct = (i + 1) / len(segments) * 100
                print(f"  {i+1}/{len(segments)} ({pct:.0f}%) — passed:{passed} blocked:{blocked} errors:{errors}")

            time.sleep(delay)

    print(f"\nDone: {passed} passed  {blocked} blocked  {errors} errors")
    print(f"Log: {log_path}")
    return {"passed": passed, "blocked": blocked, "errors": errors, "jsonl_id": jsonl_id}
