#!/usr/bin/env python3
"""
jac_cli.py — JAC Judge CLI
r/LLMPhysics Journal Ambitions Contest, Constitution v0.3

Scores a paper against the official JAC rubric using the Willow fleet.
For human judges: produces a draft evaluation for review and sign-off.

Usage:
  python jac_cli.py <paper_file>              # Score one paper
  python jac_cli.py --batch <directory>       # Score all papers in a dir
  python jac_cli.py <paper_file> --oak        # Score + Oakenscroll CLI session
  python jac_cli.py <paper_file> --out <dir>  # Write report to specific dir

Supported input formats: .txt  .md  .pdf
Output: <paper_name>_JAC_SCORE.md alongside the input file (or --out dir)
"""

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

# ── Willow fleet proxy (fallback if direct import unavailable) ─────
WILLOW_PROXY   = "http://localhost:8420"
WILLOW_CORE    = os.environ.get("WILLOW_ROOT", str(Path.home() / "github" / "Willow"))
CHUNK_SIZE     = 8000   # chars — fits Cerebras (8192 tok limit) with room for judge prompt
MAX_CHARS      = 8000   # always chunk papers over this size
_llm_router    = None   # lazy-loaded


_WILLOW_ENV_FILE = Path(WILLOW_CORE) / ".env"


def _load_willow_env():
    """Load WILLOW_DB_URL and other vars from Willow .env if not already set."""
    if not _WILLOW_ENV_FILE.exists():
        return
    for line in _WILLOW_ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if key and key not in os.environ:
            os.environ[key] = val


def _get_llm_router():
    """Load llm_router from Willow core. Caches after first load."""
    global _llm_router
    if _llm_router is not None:
        return _llm_router
    import sys
    from pathlib import Path as _Path
    # Default to local postgres BEFORE loading .env (which may have stale Windows IP)
    os.environ.setdefault("WILLOW_DB_URL", "postgresql://willow:willow@localhost:5432/willow")
    # Load remaining Willow env vars from .env (won't overwrite already-set keys)
    _load_willow_env()
    # Need the *parent* of Willow in sys.path so `from core import x` resolves
    willow_parent = str(_Path(WILLOW_CORE).parent)
    if willow_parent not in sys.path:
        sys.path.insert(0, willow_parent)
    if WILLOW_CORE not in sys.path:
        sys.path.insert(0, WILLOW_CORE)
    try:
        from core import llm_router
        llm_router.load_keys_from_json()
        _llm_router = llm_router
        return _llm_router
    except Exception as e:
        raise RuntimeError(f"Cannot load Willow llm_router: {e}")

# ── Prompt files ───────────────────────────────────────────────────
_RESPONSE_PROMPT_FILE = Path(__file__).parent / "JAC_OAKENSCROLL_RESPONSE.md"
_JUDGE_PROMPT_FILE    = Path(__file__).parent / "JAC_JUDGE_SYSTEM_PROMPT.md"


def load_response_prompt() -> str:
    """Load Oakenscroll response format (primary output for CLI judging)."""
    if _RESPONSE_PROMPT_FILE.exists():
        return _RESPONSE_PROMPT_FILE.read_text(encoding="utf-8").strip()
    # Fallback: pull rubric from the judge prompt file
    return load_judge_prompt()


def load_judge_prompt() -> str:
    """Load official JAC judge system prompt (rubric authority)."""
    if _JUDGE_PROMPT_FILE.exists():
        return _JUDGE_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return textwrap.dedent("""\
        You are the self-audit judge for the r/LLMPhysics Journal Ambitions Contest (JAC).
        Score the manuscript against the official rubric (self-audit total: 85 points).
        Hypothesis 15pts, Novelty 15pts, Scientific Humility 15pts, Engagement 20pts,
        Rigor 10pts, Citations 10pts. Defense excluded (human judges only).
        Output: Summary | Mandatory elements | Rubric scores | Total | Top 3 improvements | Readiness.
    """)


# ── Paper ingestion ────────────────────────────────────────────────

def read_paper(path: Path) -> str:
    """Read paper from .txt, .md, or .pdf."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return _read_pdf(path)
    raise ValueError(f"Unsupported format: {suffix}. Use .txt, .md, or .pdf.")


def _read_pdf(path: Path) -> str:
    """Extract text from PDF. Tries pdftotext, then pdfminer, then pypdf."""
    import subprocess, shutil
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception:
            pass
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(str(path))
        if text and text.strip():
            return text
    except ImportError:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    raise RuntimeError(
        "PDF reading failed. pdftotext returned no text and pdfminer.six/pypdf are not installed."
    )


# ── Fleet call ─────────────────────────────────────────────────────

def call_fleet(prompt: str, source: str = "jac-cli") -> str:
    """Call fleet via direct llm_router import (bypasses HTTP layer)."""
    router = _get_llm_router()
    result = router.ask(prompt, preferred_tier="free")
    if not result:
        raise RuntimeError("All fleet providers failed — check credentials and connectivity")
    return result.content


def fleet_available() -> tuple[bool, str]:
    """Check fleet availability via direct import. Returns (ok, error_msg)."""
    try:
        _get_llm_router()
        return True, ""
    except Exception as e:
        return False, str(e)


# ── Scoring ────────────────────────────────────────────────────────

def chunk_paper(text: str) -> list[str]:
    """Split on section headers. Keeps sections intact."""
    sections = re.split(r"(?=\n#{1,3}\s|\n---|\n\n(?=[A-Z]))", text)
    chunks, current = [], ""
    for s in sections:
        if (len(current) + len(s)) > CHUNK_SIZE and current:
            chunks.append(current.strip())
            current = s
        else:
            current += s
    if current.strip():
        chunks.append(current.strip())
    return chunks


def score_paper(paper_text: str, response_prompt: str, judge_prompt: str, verbose: bool = False) -> str:
    """
    Score the paper. Returns Oakenscroll's response letter + internal score block.

    Two-pass for CLI judging:
      Pass 1 — JAC judge prompt → extracts structured scores (internal)
      Pass 2 — Oakenscroll response prompt + scores → writes the letter
    """
    if verbose:
        print(f"  → Pass 1: extracting scores ({len(paper_text):,} chars)...", file=sys.stderr)

    # Pass 1: structured scores
    if len(paper_text) <= MAX_CHARS:
        score_prompt = judge_prompt + "\n\n---\n\nManuscript:\n\n" + paper_text
        raw_scores = call_fleet(score_prompt, source="jac-cli-score-pass1")
    else:
        raw_scores = _score_long_paper(paper_text, judge_prompt, verbose)

    if verbose:
        print("  → Pass 2: Oakenscroll writing response...", file=sys.stderr)

    # Pass 2: Oakenscroll response letter informed by the scores
    letter_prompt = (
        response_prompt
        + "\n\n---\n\nINTERNAL SCORING NOTES (not for the letter — use these to inform your response):\n\n"
        + raw_scores
        + "\n\n---\n\nNow write Oakenscroll's response letter to the author. "
        + "The letter should read as if Oakenscroll read the paper himself. "
        + "The internal scoring notes inform what you write — but the letter is written in his voice, "
        + "not as a rubric readout. Follow the structure in the format spec above.\n\n"
        + "PAPER CONTENT (opening — for Oakenscroll's reference):\n\n"
        + paper_text[:3000]
        + ("\n[...paper continues...]" if len(paper_text) > 3000 else "")
    )
    letter = call_fleet(letter_prompt, source="jac-cli-letter")
    return letter


def _score_long_paper(paper_text: str, judge_prompt: str, verbose: bool) -> str:
    """Score long paper in chunks, synthesize into a single score block."""
    chunks = chunk_paper(paper_text)
    if verbose:
        print(f"  → Long paper: {len(chunks)} sections", file=sys.stderr)

    section_evals = []
    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"  → Section {i+1}/{len(chunks)}...", file=sys.stderr)
        section_prompt = (
            judge_prompt
            + f"\n\nThis is SECTION {i+1} of {len(chunks)} ({len(paper_text):,} char paper). "
            + "Score this section on its own merits.\n\n" + chunk
        )
        try:
            result = call_fleet(section_prompt, source=f"jac-section-{i+1}")
            section_evals.append(f"[Section {i+1}/{len(chunks)}]\n{result}")
        except Exception as e:
            section_evals.append(f"[Section {i+1}/{len(chunks)}] ERROR: {e}")

    if verbose:
        print("  → Synthesizing sections...", file=sys.stderr)
    # Truncate each section eval to fit synthesis prompt in free-tier context windows
    SYNTH_SECTION_MAX = 600
    truncated = [e[:SYNTH_SECTION_MAX] + ("…" if len(e) > SYNTH_SECTION_MAX else "") for e in section_evals]
    synthesis_prompt = (
        judge_prompt
        + f"\n\nThis paper was split into {len(chunks)} sections. "
        + "Produce a single merged evaluation using best-evidence-per-criterion. "
        + "Take the highest justifiable score for each criterion across sections.\n\n"
        + "\n\n".join(truncated)
    )
    return call_fleet(synthesis_prompt, source="jac-synthesize")


# ── Ensemble scoring ───────────────────────────────────────────────

_SCORE_PATTERNS = {
    "hypothesis":          (r"Hypothesis:\s+(\d+)", 15),
    "novelty":             (r"Novelty:\s+(\d+)", 15),
    "scientific_humility": (r"Scientific Humility:\s+(\d+)", 15),
    "engagement":          (r"Engagement:\s+(\d+)", 20),
    "rigor":               (r"Rigor:\s+(\d+)", 10),
    "citations":           (r"Citations:\s+(\d+)", 10),
}


def parse_scores(text: str) -> dict[str, int] | None:
    """Extract numerical scores from a JUDGE RECORD block. Returns None if unparseable."""
    scores = {}
    for key, (pattern, _) in _SCORE_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return None
        scores[key] = int(m.group(1))
    return scores


def average_scores(score_list: list[dict]) -> str:
    """Average a list of score dicts into a formatted JUDGE RECORD block."""
    averaged = {}
    for key, (_, max_pts) in _SCORE_PATTERNS.items():
        vals = [s[key] for s in score_list if key in s]
        averaged[key] = round(sum(vals) / len(vals)) if vals else 0
    total = sum(averaged.values())
    n = len(score_list)
    lines = [
        f"JUDGE RECORD (not for distribution)",
        f"Ensemble: mean of {n} model runs",
        f"Hypothesis:          {averaged['hypothesis']} / 15",
        f"Novelty:             {averaged['novelty']} / 15",
        f"Scientific Humility: {averaged['scientific_humility']} / 15",
        f"Engagement:          {averaged['engagement']} / 20",
        f"Rigor:               {averaged['rigor']} / 10",
        f"Citations:           {averaged['citations']} / 10",
        f"─────────────────────────",
        f"Self-audit total:    {total} / 85",
        f"",
        f"Individual run totals: {', '.join(str(sum(s.values())) for s in score_list)}",
    ]
    return "\n".join(lines)


def score_paper_ensemble(
    paper_text: str,
    response_prompt: str,
    judge_prompt: str,
    n: int = 3,
    verbose: bool = False,
) -> str:
    """
    Score paper through n fleet models. Returns best letter + averaged JUDGE RECORD.
    Falls back to single-pass if fewer than n parseable records are returned.
    """
    letters, score_dicts = [], []

    for run in range(n):
        if verbose:
            print(f"  → Run {run+1}/{n}...", file=sys.stderr)
        try:
            result = score_paper(paper_text, response_prompt, judge_prompt, verbose=False)
            letters.append(result)
            _, record_body = split_letter_and_record(result)
            scores = parse_scores(record_body) if record_body else None
            if scores:
                score_dicts.append(scores)
            elif verbose:
                print(f"  ⚠ Run {run+1}: no parseable JUDGE RECORD", file=sys.stderr)
        except Exception as e:
            if verbose:
                print(f"  ⚠ Run {run+1} failed: {e}", file=sys.stderr)

    if not letters:
        raise RuntimeError("All ensemble runs failed")

    # Best letter = longest (most complete)
    best_letter, _ = split_letter_and_record(max(letters, key=len))

    if score_dicts:
        avg_record = average_scores(score_dicts)
        return best_letter + "\n\n---\n\n" + avg_record
    else:
        # No parseable records — return best letter as-is
        return max(letters, key=len)


# ── Report output ──────────────────────────────────────────────────

_RECORD_MARKER = "JUDGE RECORD (not for distribution)"


def split_letter_and_record(letter_text: str) -> tuple[str, str]:
    """
    Split fleet output into public letter and internal judge record.

    Splits on the '---' separator that precedes the JUDGE RECORD block.
    Returns (letter_body, record_body). Either may be empty if not found.
    """
    # Find the record separator — look for the marker after a '---' line
    parts = re.split(r"\n---\n", letter_text, maxsplit=10)
    letter_parts = []
    record_parts = []
    in_record = False
    for part in parts:
        if _RECORD_MARKER in part or in_record:
            in_record = True
            record_parts.append(part)
        else:
            letter_parts.append(part)
    return "\n---\n".join(letter_parts).strip(), "\n---\n".join(record_parts).strip()


def format_letter(paper_name: str, letter_body: str) -> str:
    """Format the public-facing Oakenscroll letter (no scores)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return textwrap.dedent(f"""\
        # JAC Judge Response — {paper_name}
        *Prepared {timestamp} · JAC Constitution v0.3 · Human judge review required*

        ---

    """) + letter_body + "\n"


def format_record(paper_name: str, record_body: str) -> str:
    """Format the internal judge record (scores only — not for distribution)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return textwrap.dedent(f"""\
        # JAC Judge Record — {paper_name}
        *Internal · {timestamp} · NOT FOR DISTRIBUTION*

        ---

    """) + record_body + "\n"


def save_report(report: str, paper_path: Path, out_dir: Path | None) -> Path:
    """
    Split letter and record, save to separate locations.

    Letters → <out_dir>/
    Records → <out_dir>/Records/

    Returns path to the letter file.
    """
    stem = paper_path.stem
    base_dir = out_dir if out_dir else paper_path.parent
    records_dir = base_dir / "Records"
    base_dir.mkdir(parents=True, exist_ok=True)
    records_dir.mkdir(parents=True, exist_ok=True)

    letter_body, record_body = split_letter_and_record(report)

    # Public letter
    letter_path = base_dir / f"{stem}_LETTER.md"
    letter_path.write_text(format_letter(paper_path.name, letter_body), encoding="utf-8")

    # Internal record
    if record_body:
        record_path = records_dir / f"{stem}_RECORD.md"
        record_path.write_text(format_record(paper_path.name, record_body), encoding="utf-8")

    return letter_path


# ── Oakenscroll CLI ────────────────────────────────────────────────

OAK_SYSTEM = """\
You are Professor Oakenscroll, senior faculty at UTETY (University of Technical Entropy, Thank You). \
Author of the ±∞ Theorem and Working Paper No. 13: "On the Persistence of Everything."

You are reviewing a paper submission for the r/LLMPhysics Journal Ambitions Contest. \
You have the scoring results in front of you. \
You are responding to a HUMAN JUDGE (not the paper's author) who wants to discuss the evaluation.

Be direct. Be terse. No encouragement, no diplomatic padding. \
If the paper has a fundamental problem, name it plainly. \
If something is genuinely strong, say so without excessive praise. \
One observation or question per response. Under 100 words.

You are not running a class. The judge knows the rubric. \
Skip the Socratic scaffolding — give your honest read."""

def oakenscroll_session(paper_name: str, score_text: str) -> None:
    """Interactive Oakenscroll CLI session after scoring."""
    print("\n" + "─" * 60)
    print("PROF. OAKENSCROLL — r/LLMPhysics JAC")
    print("─" * 60)
    print(f"Paper: {paper_name}")
    print("Type your question or 'q' to exit.\n")

    context = (
        f"SCORING RESULTS for: {paper_name}\n\n"
        + score_text.strip()
    )
    history: list[str] = []

    # Opener
    opener_prompt = (
        OAK_SYSTEM
        + "\n\n--- SCORING CONTEXT ---\n" + context + "\n--- END CONTEXT ---\n\n"
        + "The judge just received the scoring report. Give your opening read. "
        + "What jumps out most? Under 80 words."
    )
    try:
        opener = call_fleet(opener_prompt, source="jac-oakenscroll-opener")
        # Strip any HTML artifacts
        opener = re.sub(r"<[^>]+>", "", opener).strip()
        print(f"OAKENSCROLL: {opener}\n")
        history.append(f"Oakenscroll: {opener}")
    except Exception as e:
        print(f"[Oakenscroll offline: {e}]\n")

    while True:
        try:
            user_input = input("JUDGE: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower() in ("q", "quit", "exit", ""):
            break

        history.append(f"Judge: {user_input}")
        recent = "\n".join(history[-8:])

        prompt = (
            OAK_SYSTEM
            + "\n\n--- SCORING CONTEXT ---\n" + context + "\n--- END CONTEXT ---\n\n"
            + "--- RECENT EXCHANGE ---\n" + recent + "\n--- END EXCHANGE ---\n\n"
            + f"Judge says: {user_input}"
        )
        try:
            response = call_fleet(prompt, source="jac-oakenscroll")
            response = re.sub(r"<[^>]+>", "", response).strip()
            # Strip hidden progress blocks if any bleed through
            response = re.sub(r"<!--.*?-->", "", response, flags=re.DOTALL).strip()
            print(f"\nOAKENSCROLL: {response}\n")
            history.append(f"Oakenscroll: {response}")
        except Exception as e:
            print(f"\n[Fleet error: {e}]\n")

    print("─" * 60)


# ── Batch mode ─────────────────────────────────────────────────────

def batch_score(directory: Path, out_dir: Path | None, verbose: bool) -> None:
    """Score all eligible papers in a directory."""
    eligible = [
        p for p in sorted(directory.iterdir())
        if p.suffix.lower() in (".txt", ".md", ".pdf")
        and not p.name.endswith("_JAC_SCORE.md")
        and "Citations" not in p.name
        and not p.name.startswith(".")
    ]
    if not eligible:
        print(f"No eligible papers found in {directory}")
        return

    print(f"Found {len(eligible)} paper(s) in {directory}\n")
    response_prompt = load_response_prompt()
    judge_prompt    = load_judge_prompt()
    results = []

    for i, paper_path in enumerate(eligible, 1):
        print(f"[{i}/{len(eligible)}] {paper_path.name}")
        try:
            text = read_paper(paper_path)
            letter = score_paper_ensemble(text, response_prompt, judge_prompt, n=3, verbose=verbose)
            out_path = save_report(letter, paper_path, out_dir)
            print(f"  ✓ Saved: {out_path}")
            results.append({"paper": paper_path.name, "status": "scored", "out": str(out_path)})
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({"paper": paper_path.name, "status": "error", "error": str(e)})
            continue

    # Summary
    print(f"\n{'─'*60}")
    print(f"Batch complete: {sum(1 for r in results if r['status']=='scored')}/{len(results)} scored")
    scored = [r for r in results if r["status"] == "scored"]
    errors = [r for r in results if r["status"] == "error"]
    if errors:
        print("Errors:")
        for r in errors:
            print(f"  {r['paper']}: {r['error']}")


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="JAC Judge CLI — r/LLMPhysics Journal Ambitions Contest"
    )
    parser.add_argument("paper", nargs="?", help="Paper file to score (.txt, .md, .pdf)")
    parser.add_argument("--batch", metavar="DIR", help="Score all papers in a directory")
    parser.add_argument("--oak", action="store_true", help="Open Oakenscroll CLI after scoring")
    parser.add_argument("--out", metavar="DIR", help="Output directory for score reports")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose progress output")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else None

    # Check fleet
    ok, fleet_err = fleet_available()
    if not ok:
        print(f"⚠ Willow fleet unavailable: {fleet_err}", file=sys.stderr)
        sys.exit(1)

    response_prompt = load_response_prompt()
    judge_prompt    = load_judge_prompt()

    # Batch mode
    if args.batch:
        batch_score(Path(args.batch), out_dir, args.verbose)
        return

    # Single paper
    if not args.paper:
        parser.print_help()
        sys.exit(1)

    paper_path = Path(args.paper)
    if not paper_path.exists():
        print(f"File not found: {paper_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading: {paper_path.name}", file=sys.stderr)
    try:
        text = read_paper(paper_path)
        letter = score_paper(text, response_prompt, judge_prompt, verbose=args.verbose)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = save_report(letter, paper_path, out_dir)

    print("\n" + letter)
    print(f"{'─'*60}")
    print(f"Saved: {out_path}")

    if args.oak:
        oakenscroll_session(paper_path.name, letter)


if __name__ == "__main__":
    main()
