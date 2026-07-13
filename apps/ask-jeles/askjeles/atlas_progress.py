"""Bridge: Ask Jeles learning history -> The Catalog (Atlas) completion.

The Catalog (web/atlas/) colors a course node gold when its id is in the
browser's `knowledge-map.completed.v1` set. This module reads the user's
*local* Ask Jeles history and produces the seed for that set:

  learning_events/*.jsonl  ──▶  matched course ids  ──▶  + prereq closure
  milestones.json          ──▶  stats (context only)

and writes web/atlas/data/jeles-progress.json, which the companion
js/jeles-progress.js loads at runtime and unions into completion.

Design notes
------------
- The match is deliberately *conservative*. Learning events are searches and
  study notes, not exam passes — so we only claim a subject when the event
  text clearly names it (the full course title appears, or every significant
  title word appears, or a distinctive topic phrase appears). Better to
  under-claim and let the user click a node than to paint the atlas gold on a
  stray query.
- Prerequisite closure: if you have clearly studied a subject, its whole
  prerequisite chain is marked too, matching the Catalog's own invariant that
  a completed course has all its prerequisites completed.
- Everything stays on the user's machine. The output file is gitignored; the
  hosted Catalog simply never sees it and behaves as vanilla upstream.
- Milestones (milestones.json) carry no per-course signal — only counters —
  so they inform the `stats` block, not node coloring.

Run it:

    python -m askjeles.atlas_progress            # writes the progress file
    python -m askjeles.atlas_progress --dry-run  # print a summary, write nothing
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from askjeles.jeles_paths import app_data as _app_data

SCHEMA = "ask_jeles.atlas_progress.v1"

# Tokens too generic to carry a subject on their own. Note we deliberately do
# NOT strip qualifier words like "advanced"/"introduction"/"general" — they
# distinguish course levels (Quantum Mechanics vs Advanced Quantum Mechanics),
# so requiring them literally keeps a broad query from completing a narrower or
# more advanced course it never named.
_STOP = {
    "the", "and", "for", "with", "into", "from", "your", "you", "our", "their",
    "theory", "studies", "study", "science", "sciences", "engineering",
    "systems", "methods", "analysis",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _repo_root() -> Path:
    """The ask-jeles app directory (parent of this package)."""
    return Path(__file__).resolve().parents[1]


def _courses_json() -> Path:
    return _repo_root() / "web" / "atlas" / "data" / "courses.json"


def _progress_json() -> Path:
    return _repo_root() / "web" / "atlas" / "data" / "jeles-progress.json"


def _events_dir() -> Path:
    return _app_data() / "learning_events"


def _milestones_path() -> Path:
    return _app_data() / "milestones.json"


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens as a set."""
    return set(_TOKEN_RE.findall((text or "").lower()))


def significant_tokens(title: str) -> list[str]:
    """Distinctive words of a course title (>=4 chars, not a stopword)."""
    return [t for t in _TOKEN_RE.findall((title or "").lower())
            if len(t) >= 4 and t not in _STOP]


def event_text(event: dict[str, Any]) -> str:
    """Flatten the searchable/pedagogical text of one learning event."""
    parts: list[str] = [str(event.get("query", "")), str(event.get("query_class", ""))]
    ped = event.get("pedagogy")
    if isinstance(ped, dict):
        parts.append(json.dumps(ped, ensure_ascii=False))
    elif ped:
        parts.append(str(ped))
    rs = event.get("result_summary")
    if isinstance(rs, dict):
        parts.append(json.dumps(rs, ensure_ascii=False))
    for src in event.get("sources_used") or []:
        parts.append(str(src))
    return " ".join(parts)


def match_course(text_lc: str, tokens: set[str], course: dict[str, Any]) -> bool:
    """Conservative decision: does this text clearly name this *subject*?

    We match on the course title only, never on `topics`: topics like
    "Reaction mechanisms" or "Free will" are shared across many courses, so a
    topic mention brushes subjects the user never studied. Completion should
    mean "you named this subject," so:

    - the full title appears verbatim (e.g. "organic chemistry"), or
    - every distinctive word of a multi-word title appears (e.g. "quantum"
      AND "mechanics"). Single-word titles rely on the verbatim check, so a
      lone common word ("philosophy") can't complete "Philosophy of Science".
    """
    title = (course.get("title") or "").lower().strip()
    if len(title) >= 5 and title in text_lc:
        return True

    sig = significant_tokens(course.get("title", ""))
    if len(sig) >= 2 and all(t in tokens for t in sig):
        return True

    return False


def match_courses(text: str, courses: list[dict[str, Any]]) -> set[str]:
    """Course ids clearly named by one blob of text."""
    text_lc = (text or "").lower()
    tokens = tokenize(text)
    hits: set[str] = set()
    for c in courses:
        if match_course(text_lc, tokens, c):
            hits.add(c["id"])
    return hits


def prereq_closure(ids: Iterable[str], by_id: dict[str, dict[str, Any]]) -> set[str]:
    """Add the transitive prerequisites of every id in `ids`."""
    out: set[str] = set()
    stack = list(ids)
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        node = by_id.get(cur)
        if node:
            for req in node.get("requires") or []:
                if req not in out:
                    stack.append(req)
    return out


def build_progress(
    events: Iterable[dict[str, Any]],
    courses: list[dict[str, Any]],
    milestones: Optional[dict[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Assemble the progress payload from parsed events + course index."""
    by_id = {c["id"]: c for c in courses}
    direct: set[str] = set()
    scanned = 0
    for ev in events:
        scanned += 1
        direct |= match_courses(event_text(ev), courses)

    closed = prereq_closure(direct, by_id)
    ms = milestones or {}
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()

    return {
        "schema": SCHEMA,
        "generated_at": ts,
        "source": "ask-jeles learning_events + milestones",
        "completed_course_ids": sorted(closed),
        "matched_directly": sorted(direct),
        "stats": {
            "events_scanned": scanned,
            "matched_directly": len(direct),
            "completed_with_prereqs": len(closed),
            "questions_asked": int(ms.get("questions_asked", 0) or 0),
            "seed_planted": bool(ms.get("seed_planted", False)),
        },
        "notes": (
            "Heuristic mapping from your local Ask Jeles history. Conservative "
            "by design — click a node to add or Reset to clear."
        ),
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_courses(path: Optional[Path] = None) -> list[dict[str, Any]]:
    p = path or _courses_json()
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("courses", [])


def iter_events(dirpath: Optional[Path] = None) -> Iterator[dict[str, Any]]:
    d = dirpath or _events_dir()
    if not d.exists():
        return
    for f in sorted(d.glob("*.jsonl")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        except OSError:
            continue


def load_milestones(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or _milestones_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_progress(payload: dict[str, Any], path: Optional[Path] = None) -> Path:
    p = path or _progress_json()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Seed The Catalog from Ask Jeles learning history.")
    ap.add_argument("--dry-run", action="store_true", help="Summarize without writing the progress file.")
    args = ap.parse_args(argv)

    try:
        courses = load_courses()
    except FileNotFoundError:
        print("courses.json not found — run: node web/atlas/scripts/export-courses.js")
        return 1

    payload = build_progress(iter_events(), courses, load_milestones())
    s = payload["stats"]
    print(
        f"Scanned {s['events_scanned']} learning event(s): "
        f"{s['matched_directly']} subject(s) named, "
        f"{s['completed_with_prereqs']} marked with prerequisites."
    )
    if args.dry_run:
        print("(dry run — nothing written)")
        return 0

    out = write_progress(payload)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
