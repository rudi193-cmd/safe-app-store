"""Pull Emerging Rule lessons from GitHub and normalize to segment JSONL."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
from typing import Iterator

REPO = "Emerging-Rule/community"
LESSONS_DIR = "lessons"

# Spanish function words as a cheap language detector (EN/ES corpus only)
_ES_MARKERS = {
    "el", "la", "los", "las", "de", "del", "en", "con", "que", "una",
    "es", "se", "para", "por", "como", "sus", "al", "tu", "mi", "lo",
    "este", "esta", "pero", "más", "sin", "nos", "un", "su", "son",
}


def _detect_lang(text: str) -> str:
    words = re.findall(r"\b[a-záéíóúüñ]+\b", text.lower())
    if not words:
        return "en"
    es_hits = sum(1 for w in words if w in _ES_MARKERS)
    return "es" if es_hits / len(words) > 0.12 else "en"


def _extract_meta(lines: list[str]) -> dict:
    meta: dict[str, str] = {}
    for line in lines[:20]:
        m = re.match(r"\*\*(.+?):\*\*\s*(.+)", line)
        if m:
            key = m.group(1).lower().replace(" ", "_")
            meta[key] = m.group(2).strip()
    return meta


def _strip_md(text: str) -> str:
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"^[-*>]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    return text.strip()


def _segments_from_content(content: str, lesson_id: str, meta: dict) -> Iterator[dict]:
    # Drop YAML-style frontmatter if present
    content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)

    paragraphs = re.split(r"\n{2,}", content)
    for i, para in enumerate(paragraphs):
        text = _strip_md(para).strip()
        if len(text) < 35:
            continue
        if text.startswith("```") or text.startswith("|"):
            continue
        yield {
            "id": f"{lesson_id}::{i}",
            "lesson": lesson_id,
            "grade": meta.get("grade_level", ""),
            "subject": meta.get("subject", ""),
            "is_bilingual": "bilingual" in lesson_id,
            "lang": _detect_lang(text),
            "text": text,
        }


def _gh_file_list() -> list[str]:
    result = subprocess.run(
        ["gh", "api", f"/repos/{REPO}/git/trees/HEAD?recursive=1",
         "--jq", ".tree[] | select(.type==\"blob\") | .path"],
        capture_output=True, text=True, check=True,
    )
    return [
        p for p in result.stdout.splitlines()
        if p.startswith(f"{LESSONS_DIR}/") and p.endswith(".md")
    ]


def _gh_file_content(path: str) -> str:
    result = subprocess.run(
        ["gh", "api", f"/repos/{REPO}/contents/{path}", "--jq", ".content"],
        capture_output=True, text=True, check=True,
    )
    import base64
    return base64.b64decode(result.stdout.strip()).decode("utf-8")


def scrape(output_path: str = "data/corpus.jsonl", local_dir: str = "") -> list[dict]:
    """Scrape lessons into segment JSONL — from GitHub via gh, or a local clone
    via local_dir (a repo root or lessons/ directory; no network needed)."""
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if local_dir:
        root = pathlib.Path(local_dir)
        if (root / LESSONS_DIR).is_dir():
            root = root / LESSONS_DIR
        files = sorted(str(p) for p in root.glob("*.md"))
        print(f"Reading {len(files)} lesson files from {root}\n")
    else:
        print(f"Fetching file list from {REPO}...")
        files = _gh_file_list()
        print(f"Found {len(files)} lesson files\n")

    all_segments: list[dict] = []
    for path in files:
        lesson_id = pathlib.Path(path).stem
        try:
            if local_dir:
                content = pathlib.Path(path).read_text(encoding="utf-8")
            else:
                content = _gh_file_content(path)
            meta = _extract_meta(content.splitlines())
            segments = list(_segments_from_content(content, lesson_id, meta))
            all_segments.extend(segments)
            langs = {}
            for s in segments:
                langs[s["lang"]] = langs.get(s["lang"], 0) + 1
            lang_str = "  ".join(f"{k}:{v}" for k, v in sorted(langs.items()))
            print(f"  {lesson_id}: {len(segments)} segments  [{lang_str}]")
        except Exception as exc:
            print(f"  SKIP {lesson_id}: {exc}")

    with open(output_path, "w", encoding="utf-8") as f:
        for seg in all_segments:
            f.write(json.dumps(seg, ensure_ascii=False) + "\n")

    en = sum(1 for s in all_segments if s["lang"] == "en")
    es = sum(1 for s in all_segments if s["lang"] == "es")
    print(f"\nWrote {len(all_segments)} segments to {output_path}")
    print(f"  en: {en}  es: {es}  bilingual lessons: {sum(1 for s in all_segments if s['is_bilingual'] and s['lang'] == 'en')}")
    return all_segments
