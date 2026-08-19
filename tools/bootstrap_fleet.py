#!/usr/bin/env python3
"""bootstrap_fleet.py — feed fleet decisions into Nestor and Jeles.

The second boot tool (run after decisions_boot.py): reads all decision
sources across the fleet and feeds each question/commitment pair into:

  * Nestor — as draft finding→recommendation pairs via nestor_propose
    (proposes only; only a person may seal)
  * Jeles — as corpus nuggets via corpus_put for semantic search

Nestor's source_norm unique index and Jeles' nugget dedup make this
idempotent — running it twice is safe. New entries land; duplicates
are skipped.

Sources read:
  1. stores/decisions/fleet.json   — sealed decisions + standing rejections
  2. apps/*/docs/DECISION*.md      — app-level decision docs (Jeles only)
  3. Willow CONSTITUTION.md        — governance sections (Jeles only)

Usage:
  tools/bootstrap_fleet.py              # full bootstrap (Nestor + Jeles)
  tools/bootstrap_fleet.py --nestor     # Nestor only
  tools/bootstrap_fleet.py --jeles      # Jeles only
  tools/bootstrap_fleet.py --dry-run    # show what would be fed, don't feed
  tools/bootstrap_fleet.py --strict     # exit 1 if any feed fails
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FLEET_JSON = REPO_ROOT / "stores" / "decisions" / "fleet.json"

NESTOR_CMD = os.environ.get("NESTOR_CMD", "nestor")
NESTOR_DB = os.environ.get(
    "NESTOR_BOOTSTRAP_DB",
    str(REPO_ROOT / "data" / "nestor-audit.db"),
)
NESTOR_LEDGER = os.environ.get(
    "NESTOR_BOOTSTRAP_LEDGER",
    str(REPO_ROOT / "data" / "nestor-audit-ledger.jsonl"),
)

JELES_COLLECTION = os.environ.get("JELES_CORPUS_COLLECTION", "ask_jeles_corpus")
WILLOW_STORE_ROOT = os.environ.get(
    "WILLOW_STORE_ROOT",
    str(Path.home() / ".willow" / "store"),
)

APP_DECISION_DOCS = [
    (REPO_ROOT / "apps" / "ai-game-master" / "docs" / "DECISION.md",
     "ai-game-master"),
    (REPO_ROOT / "apps" / "homestead-health" / "docs" / "DECISION-living-lane-ledger.md",
     "homestead-health"),
]

CONSTITUTION_PATHS = []
for candidate in [
    Path("/workspace/rudi193-cmd/willow/CONSTITUTION.md"),
    Path("/workspace/rudi193-cmd/willow-2.0/CONSTITUTION.md"),
]:
    if candidate.exists():
        CONSTITUTION_PATHS.append(candidate)


# ── fleet.json parsing ─────────────────────────────────────────────────────

def load_fleet_decisions(path: Path = FLEET_JSON) -> list[dict]:
    """Extract (source_text, target_text, origin) triples from fleet.json."""
    record = json.loads(path.read_text())
    pairs = []

    for d in record.get("decisions", []):
        if d.get("superseded_by"):
            continue
        q = d.get("question", "")
        commitment = d.get("commitment", "")
        reason = d.get("reason", "")
        verifier = d.get("verified_by", "")
        date = d.get("date", "")
        rec = d.get("record", "")

        target = f"{commitment}\n\nReason: {reason}"
        if rec:
            target += f"\nRecord: {rec}"
        if verifier:
            target += f"\nSealed by: {verifier} ({date})"

        pairs.append({
            "source_text": q,
            "target_text": target,
            "origin": "fleet.json/decisions",
            "tags": ["fleet", "decision", "sealed"],
        })

    for r in record.get("rejections", []):
        q = r.get("question", "")
        option = r.get("option", "")
        reason = r.get("reason", "")
        reopen = r.get("reopen_when", "")
        verifier = r.get("verified_by", "")

        source = f"{q} — option: {option}"
        target = f"REJECTED. {reason}"
        if reopen:
            target += f"\nReopen when: {reopen}"
        else:
            target += "\nReopen when: never"
        if verifier:
            target += f"\nVerified by: {verifier}"

        pairs.append({
            "source_text": source,
            "target_text": target,
            "origin": "fleet.json/rejections",
            "tags": ["fleet", "rejection"],
        })

    return pairs


# ── markdown doc parsing (for Jeles) ───────────────────────────────────────

def chunk_markdown(text: str) -> list[dict]:
    """Split markdown into section-based chunks with headings as questions."""
    chunks = []
    lines = text.split("\n")
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading_match:
            if current_heading and current_body:
                body = "\n".join(current_body).strip()
                if len(body) > 50:
                    chunks.append({"question": current_heading, "answer": body})
            current_heading = heading_match.group(2).strip()
            current_body = []
        else:
            current_body.append(line)

    if current_heading and current_body:
        body = "\n".join(current_body).strip()
        if len(body) > 50:
            chunks.append({"question": current_heading, "answer": body})

    return chunks


# ── Nestor feed (direct Python API) ────────────────────────────────────────

def _feed_nestor(pairs: list[dict], dry_run: bool = False) -> dict:
    """Feed pairs into Nestor via memory.add_pair (direct Python API).

    Writes directly to tm_pairs as drafts so nestor_ask/nestor_match
    can find them immediately. Dedup is handled by Nestor's source_norm
    unique index — duplicates are silently skipped.
    """
    if dry_run:
        return {"ok": True, "fed": len(pairs), "skipped": 0, "errors": [],
                "reason": "dry-run"}

    sys.path.insert(0, str(Path(NESTOR_CMD).parent.parent))
    try:
        from nestor import memory
        from nestor.matcher import StringMatcher
        from nestor.sqlite_store import SqliteStore
    except ImportError:
        resolved = shutil.which(NESTOR_CMD)
        if resolved:
            pkg_root = str(Path(resolved).resolve().parents[1])
            sys.path.insert(0, pkg_root)
            try:
                from nestor import memory
                from nestor.matcher import StringMatcher
                from nestor.sqlite_store import SqliteStore
            except ImportError:
                return {"ok": False, "fed": 0, "skipped": 0,
                        "errors": ["nestor not importable"],
                        "reason": "nestor package not found"}
        else:
            return {"ok": False, "fed": 0, "skipped": 0,
                    "errors": ["nestor not importable or on PATH"],
                    "reason": "nestor package not found"}

    os.environ.setdefault("NESTOR_LEDGER", NESTOR_LEDGER)
    store = SqliteStore(NESTOR_DB)
    matcher = StringMatcher()

    fed = 0
    skipped = 0
    errors: list[str] = []

    for i, pair in enumerate(pairs):
        try:
            result = memory.add_pair(
                source_text=pair["source_text"],
                target_text=pair["target_text"],
                source_lang="finding",
                target_lang="recommendation",
                status="draft",
                origin=pair.get("origin", "fleet-bootstrap"),
                store=store,
                matcher=matcher,
                audit=False,
            )
            if isinstance(result, dict) and result.get("action") == "skip":
                skipped += 1
            else:
                fed += 1
        except Exception as exc:
            exc_str = f"{type(exc).__name__}: {exc}"
            if "unique" in exc_str.lower() or "duplicate" in exc_str.lower():
                skipped += 1
            else:
                errors.append(f"pair[{i}]: {exc_str}"[:140])

    return {"ok": len(errors) == 0, "fed": fed, "skipped": skipped,
            "errors": errors, "reason": "complete"}


# ── Jeles corpus feed (direct Python API) ──────────────────────────────────

def _feed_jeles(nuggets: list[dict], dry_run: bool = False) -> dict:
    """Feed nuggets into Jeles corpus via the Python API (corpus.put_nugget).

    Uses the same direct-import pattern as the existing
    scratchpad/bootstrap_jeles_corpus.py. Env vars WILLOW_STORE_ROOT and
    JELES_CORPUS_COLLECTION are set before import so the corpus module
    picks up the right store.
    """
    if dry_run:
        return {"ok": True, "fed": len(nuggets), "skipped": 0, "errors": [],
                "reason": "dry-run"}

    os.environ.setdefault("WILLOW_STORE_ROOT", WILLOW_STORE_ROOT)
    os.environ.setdefault("JELES_CORPUS_COLLECTION", JELES_COLLECTION)

    try:
        from jeles import corpus
    except ImportError:
        return {"ok": False, "fed": 0, "skipped": 0,
                "errors": ["jeles not importable"],
                "reason": "jeles package not installed"}

    fed = 0
    skipped = 0
    errors: list[str] = []

    for i, nugget in enumerate(nuggets):
        try:
            result = corpus.put_nugget(
                question=nugget["question"],
                answer=nugget["answer"],
                sources=nugget.get("sources", []),
                verified_by=nugget.get("verified_by", "fleet-bootstrap"),
                tags=nugget.get("tags"),
                verification_kind="asserted",
                written_by="bootstrap_fleet",
            )
            if isinstance(result, dict) and result.get("error"):
                err = result["error"]
                if "duplicate" in str(err).lower() or "exists" in str(err).lower():
                    skipped += 1
                else:
                    errors.append(f"nugget[{i}]: {str(err)[:120]}")
            elif isinstance(result, dict) and result.get("action") == "unchanged":
                skipped += 1
            else:
                fed += 1
        except Exception as exc:
            errors.append(f"nugget[{i}]: {type(exc).__name__}: {exc}"[:140])

    return {"ok": len(errors) == 0, "fed": fed, "skipped": skipped,
            "errors": errors, "reason": "complete"}


# ── source collection ──────────────────────────────────────────────────────

def collect_nestor_pairs() -> list[dict]:
    """All pairs destined for Nestor (finding→recommendation drafts)."""
    if not FLEET_JSON.exists():
        print(f"  WARN: {FLEET_JSON} not found", file=sys.stderr)
        return []
    return load_fleet_decisions(FLEET_JSON)


def collect_jeles_nuggets() -> list[dict]:
    """All nuggets destined for Jeles corpus."""
    nuggets: list[dict] = []

    # 1. fleet.json — structured decisions and rejections
    if FLEET_JSON.exists():
        record = json.loads(FLEET_JSON.read_text())
        for d in record.get("decisions", []):
            if d.get("superseded_by"):
                continue
            q = d["question"]
            commitment = d.get("commitment", "")
            reason = d.get("reason", "")
            rec = d.get("record", "")
            answer = f"Commitment: {commitment}\nReason: {reason}"
            if rec:
                answer += f"\nRecord: {rec}"
            if d.get("verified_by"):
                answer += f"\nSealed by: {d['verified_by']} ({d.get('date', '?')})"
            nuggets.append({
                "question": q,
                "answer": answer,
                "sources": ["stores/decisions/fleet.json"],
                "verified_by": d.get("verified_by", "fleet-bootstrap"),
                "tags": ["fleet", "decision", "sealed"],
            })

        for r in record.get("rejections", []):
            q = r["question"]
            option = r.get("option", "")
            reason = r.get("reason", "")
            reopen = r.get("reopen_when", "")
            answer = f"REJECTED option: {option}\nReason: {reason}"
            if reopen:
                answer += f"\nReopen when: {reopen}"
            else:
                answer += "\nReopen when: never"
            if r.get("verified_by"):
                answer += f"\nVerified by: {r['verified_by']}"
            nuggets.append({
                "question": f"{q} (rejected: {option})",
                "answer": answer,
                "sources": ["stores/decisions/fleet.json"],
                "verified_by": r.get("verified_by", "fleet-bootstrap"),
                "tags": ["fleet", "rejection"],
            })

    # 2. App DECISION docs
    for doc_path, repo in APP_DECISION_DOCS:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(errors="replace")
        chunks = chunk_markdown(text)
        rel = str(doc_path.relative_to(REPO_ROOT)) if doc_path.is_relative_to(REPO_ROOT) else str(doc_path)
        for chunk in chunks:
            if len(chunk["answer"]) > 4000:
                chunk["answer"] = chunk["answer"][:4000] + "\n... [truncated]"
            nuggets.append({
                "question": chunk["question"],
                "answer": chunk["answer"],
                "sources": [rel],
                "verified_by": "fleet-bootstrap",
                "tags": [repo, "decision-doc"],
            })

    # 3. Constitution sections
    for const_path in CONSTITUTION_PATHS:
        text = const_path.read_text(errors="replace")
        chunks = chunk_markdown(text)
        for chunk in chunks:
            if len(chunk["answer"]) > 4000:
                chunk["answer"] = chunk["answer"][:4000] + "\n... [truncated]"
            nuggets.append({
                "question": chunk["question"],
                "answer": chunk["answer"],
                "sources": [str(const_path)],
                "verified_by": "fleet-bootstrap",
                "tags": ["willow", "constitution"],
            })

    return nuggets


# ── main ───────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--nestor", action="store_true",
                   help="feed Nestor only")
    p.add_argument("--jeles", action="store_true",
                   help="feed Jeles only")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would be fed without feeding")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on any feed error")
    args = p.parse_args(argv)

    do_nestor = args.nestor or not args.jeles
    do_jeles = args.jeles or not args.nestor

    exit_code = 0

    if do_nestor:
        pairs = collect_nestor_pairs()
        print(f"Nestor: {len(pairs)} pairs to feed "
              f"({'dry-run' if args.dry_run else 'live'})")
        if args.dry_run:
            for pair in pairs:
                print(f"  [{pair.get('origin', '?')}] "
                      f"{pair['source_text'][:60]}")
        result = _feed_nestor(pairs, dry_run=args.dry_run)
        print(f"  fed={result['fed']}  skipped={result['skipped']}  "
              f"errors={len(result['errors'])}  ({result['reason']})")
        for err in result["errors"]:
            print(f"  ERROR: {err}", file=sys.stderr)
        if result["errors"] and args.strict:
            exit_code = 1

    if do_jeles:
        nuggets = collect_jeles_nuggets()
        print(f"Jeles: {len(nuggets)} nuggets to feed "
              f"({'dry-run' if args.dry_run else 'live'})")
        if args.dry_run:
            for nug in nuggets:
                print(f"  [{','.join(nug.get('tags', [])[:2])}] "
                      f"{nug['question'][:60]}")
        result = _feed_jeles(nuggets, dry_run=args.dry_run)
        print(f"  fed={result['fed']}  skipped={result['skipped']}  "
              f"errors={len(result['errors'])}  ({result['reason']})")
        for err in result["errors"]:
            print(f"  ERROR: {err}", file=sys.stderr)
        if result["errors"] and args.strict:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
