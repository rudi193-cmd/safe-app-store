#!/usr/bin/env python3
"""
extract.py — Model bake-off metadata harness
=============================================
Reusable extractor for same-task / many-model subagent experiments.

Given a set of Claude Code subagent transcripts (JSONL) and, optionally, the
git worktrees those agents ran in, this joins three legally-accessible sources
per run:

    {model, tokens, tool_uses, duration}   (from the transcript usage records)
  × {files changed, insertions, deletions} (from the worktree diff)
  × {ordered tool-call event stream}       (from the transcript content)

into two outputs:

    out/summary.csv   — one row per run (drop into a notebook)
    out/summary.json  — same rows, structured
    out/events.jsonl  — one line per tool call, with inter-call latency

Nothing here needs privileged access: it only reads this session's own
subagent transcripts and worktrees off disk. Transcripts are parsed
line-by-line and never loaded whole into any model's context.

Usage:
    python extract.py                       # auto-discover this project's runs
    python extract.py --transcripts-dir DIR # explicit transcript location
    python extract.py --worktrees-dir DIR   # explicit worktree location
    python extract.py --out DIR             # output directory
    python extract.py --since 2026-07-11    # only runs started on/after date

Auto-discovery walks, in order of preference:
  1. --transcripts-dir if given
  2. $CLAUDE_PROJECT_DIR/../subagents (when run inside a CC session)
  3. ~/.claude/projects/**/subagents/agent-*.jsonl
and resolves any *.output symlinks to their real .jsonl targets.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# ── transcript discovery ──────────────────────────────────────────

def _iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def discover_transcripts(explicit: str | None) -> list[Path]:
    """Return a de-duplicated list of agent-*.jsonl transcript paths."""
    candidates: list[str] = []
    if explicit:
        roots = [explicit]
    else:
        roots = []
        proj = os.environ.get("CLAUDE_PROJECT_DIR")
        if proj:
            roots.append(str(Path(proj).parent / "subagents"))
        roots.append(str(Path.home() / ".claude" / "projects"))

    for root in roots:
        p = Path(root)
        if not p.exists():
            continue
        candidates += glob.glob(str(p / "**" / "agent-*.jsonl"), recursive=True)
        candidates += glob.glob(str(p / "**" / "*.output"), recursive=True)
        if candidates:
            break  # first root that yields anything wins

    seen: dict[str, Path] = {}
    for c in candidates:
        real = Path(c).resolve()
        if real.suffix != ".jsonl" or not real.exists():
            continue
        seen[str(real)] = real
    return sorted(seen.values())


def agent_id_from_path(p: Path) -> str:
    stem = p.stem  # agent-<id>
    return stem[len("agent-"):] if stem.startswith("agent-") else stem


# ── transcript parsing ────────────────────────────────────────────

def _summarize_tool_input(name: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return ""
    for key in ("file_path", "path", "command", "pattern", "description"):
        if key in inp and isinstance(inp[key], str):
            v = inp[key].strip().replace("\n", " ")
            return v[:80]
    return ""


def parse_transcript(path: Path) -> dict:
    """Parse one subagent JSONL into a per-run record + event list."""
    agent_id = agent_id_from_path(path)
    model = None
    first_ts = last_ts = None
    turns = 0
    thinking_blocks = 0
    text_blocks = 0
    tool_events: list[dict] = []
    tool_errors = 0
    tok = Counter()  # input / output / cache_create / cache_read

    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = _iso(rec.get("timestamp", ""))
            if ts:
                first_ts = first_ts or ts
                last_ts = ts

            rtype = rec.get("type")
            msg = rec.get("message") or {}

            if rtype == "assistant":
                turns += 1
                model = msg.get("model") or model
                u = msg.get("usage") or {}
                tok["input"] += u.get("input_tokens", 0) or 0
                tok["output"] += u.get("output_tokens", 0) or 0
                tok["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
                tok["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
                for item in msg.get("content", []) or []:
                    itype = item.get("type")
                    if itype == "thinking":
                        thinking_blocks += 1
                    elif itype == "text":
                        text_blocks += 1
                    elif itype == "tool_use":
                        name = item.get("name", "?")
                        tool_events.append({
                            "run_id": agent_id,
                            "model": model,
                            "ts": ts.isoformat() if ts else None,
                            "tool": name,
                            "arg": _summarize_tool_input(name, item.get("input", {})),
                        })
            elif rtype == "user":
                for item in msg.get("content", []) or []:
                    if isinstance(item, dict) and item.get("type") == "tool_result" \
                            and item.get("is_error"):
                        tool_errors += 1

    # inter-call latency on the event stream
    prev = None
    for ev in tool_events:
        t = _iso(ev["ts"]) if ev["ts"] else None
        ev["dt_s"] = round((t - prev).total_seconds(), 2) if (t and prev) else None
        if t:
            prev = t

    duration = None
    if first_ts and last_ts:
        duration = round((last_ts - first_ts).total_seconds(), 1)

    tool_counts = Counter(ev["tool"] for ev in tool_events)

    record = {
        "run_id": agent_id,
        "model": model,
        "started": first_ts.isoformat() if first_ts else None,
        "ended": last_ts.isoformat() if last_ts else None,
        "duration_s": duration,
        "assistant_turns": turns,
        "thinking_blocks": thinking_blocks,
        "text_blocks": text_blocks,
        "tool_calls": len(tool_events),
        "tool_errors": tool_errors,
        "tokens_input": tok["input"],
        "tokens_output": tok["output"],
        "tokens_cache_create": tok["cache_create"],
        "tokens_cache_read": tok["cache_read"],
        "tool_breakdown": dict(tool_counts),
    }
    return {"record": record, "events": tool_events}


# ── worktree diff join ────────────────────────────────────────────

def discover_worktrees(explicit: str | None, repo: Path) -> dict[str, Path]:
    base = Path(explicit) if explicit else repo / ".claude" / "worktrees"
    out: dict[str, Path] = {}
    if not base.exists():
        return out
    for d in base.glob("agent-*"):
        if d.is_dir():
            out[d.name[len("agent-"):]] = d
    return out


def _git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
        ).stdout
    except Exception:
        return ""


def worktree_diff(wt: Path) -> dict:
    """Files/insertions/deletions in a worktree, including untracked files.

    Uses `add -A -N` (intent-to-add) so new files show in numstat, then clears
    the intent — never stages content, never mutates the working tree.
    """
    _git(["add", "-A", "-N"], wt)
    numstat = _git(["diff", "--numstat"], wt)
    _git(["reset", "-q"], wt)  # clear intent-to-add

    files = ins = dele = 0
    changed: list[str] = []
    for row in numstat.splitlines():
        parts = row.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        files += 1
        changed.append(path)
        ins += int(a) if a.isdigit() else 0
        dele += int(d) if d.isdigit() else 0
    return {
        "files_changed": files,
        "insertions": ins,
        "deletions": dele,
        "changed_files": changed,
    }


# ── output writers ────────────────────────────────────────────────

SUMMARY_COLUMNS = [
    "run_id", "model", "started", "ended", "duration_s",
    "assistant_turns", "thinking_blocks", "text_blocks",
    "tool_calls", "tool_errors",
    "tokens_input", "tokens_output", "tokens_cache_create", "tokens_cache_read",
    "files_changed", "insertions", "deletions",
]


def write_summary(rows: list[dict], out_dir: Path) -> None:
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2))
    with (out_dir / "summary.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_events(events: list[dict], out_dir: Path) -> None:
    with (out_dir / "events.jsonl").open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


# ── main ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Model bake-off metadata harness")
    ap.add_argument("--transcripts-dir", help="Dir containing agent-*.jsonl / *.output")
    ap.add_argument("--worktrees-dir", help="Dir containing agent-<id> worktrees")
    ap.add_argument("--repo", default=".", help="Repo root (for default worktree path)")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    ap.add_argument("--since", help="Only runs started on/after this ISO date (YYYY-MM-DD)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    transcripts = discover_transcripts(args.transcripts_dir)
    if not transcripts:
        print("No transcripts found. Pass --transcripts-dir.", file=sys.stderr)
        return 1

    worktrees = discover_worktrees(args.worktrees_dir, repo)
    since = _iso(args.since + "T00:00:00Z") if args.since else None

    rows: list[dict] = []
    all_events: list[dict] = []
    for t in transcripts:
        parsed = parse_transcript(t)
        rec = parsed["record"]
        if not rec["assistant_turns"]:
            continue  # empty / non-agent transcript
        if since and rec["started"]:
            st = _iso(rec["started"])
            if st and st < since:
                continue

        wt = worktrees.get(rec["run_id"])
        if wt:
            rec.update(worktree_diff(wt))
        else:
            rec.update({"files_changed": None, "insertions": None,
                        "deletions": None, "changed_files": []})

        rows.append(rec)
        all_events.extend(parsed["events"])

    rows.sort(key=lambda r: r.get("started") or "")
    write_summary(rows, out_dir)
    write_events(all_events, out_dir)

    if not args.quiet:
        print(f"Runs: {len(rows)}   Events: {len(all_events)}   Out: {out_dir}")
        hdr = f"{'model':<18}{'dur_s':>7}{'tools':>7}{'errs':>6}{'out_tok':>9}{'files':>7}{'+lines':>8}"
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            print(f"{str(r['model']):<18}{r['duration_s'] or 0:>7}"
                  f"{r['tool_calls']:>7}{r['tool_errors']:>6}"
                  f"{r['tokens_output']:>9}{str(r['files_changed']):>7}"
                  f"{str(r['insertions']):>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
