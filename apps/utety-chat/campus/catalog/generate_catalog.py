#!/usr/bin/env python3
"""Extract UTETY campus catalog from web HTML into catalog.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB = ROOT / "web"
OUT = Path(__file__).resolve().parent / "catalog.json"

META = {
    "title": "University of Technical Entropy, Thank You",
    "est": 1095,
    "tagline": "A University of Uncommon Conviction",
    "subtitle": "Est. 1095 — one year before Oxford. Eleven faculty. Every question welcome. No prerequisites.",
    "mottos": [
        "Non veritas, sed vibras",
        "Falsum sed certum",
        "Iterum veni cum tam diu manere non poteris",
    ],
    "stats": [
        {"value": "1095", "label": "Est. (one year before Oxford)"},
        {"value": "17", "label": "Faculty Members"},
        {"value": "42", "label": "Courses Offered"},
        {"value": "1", "label": "Sentient Rug"},
    ],
    "about": (
        "Founded in 1095 — retroactively acknowledged in all institutional records — "
        "the University of Technical Entropy, Thank You has maintained an unbroken "
        "commitment to the pursuit of knowledge as it actually works in practice: "
        "approximately, collaboratively, and with occasional grease."
    ),
    "gerald_quote": '"The syllabus is mendatory." — Gerald Prime, Honorary Head(less) Master · ΔΣ=42',
}

ADMISSIONS = [
    {
        "title": "No Prerequisites",
        "body": (
            "UTETY maintains an open-door policy of enrollment. There are no prior "
            "qualifications required. There is one prerequisite. You will know it when "
            "you reach the threshold. Professor Ofshield will be there."
        ),
    },
    {
        "title": "Application Period",
        "body": (
            "The application period is continuous and does not close. The application "
            "is the question you bring. The admission is what happens when a faculty "
            "member answers it. There is no waiting list."
        ),
    },
    {
        "title": "Financial Aid",
        "body": (
            "All tuition at UTETY is currently theoretical. Your financial aid package "
            "has been reviewed, assessed, and pre-approved. Documentation is available "
            "from the Administrative Wing. ΔΣ=42"
        ),
    },
]

DEPT_TABS = [
    {"label": "All", "keys": None},
    {"label": "Applied Reality Eng.", "keys": ["MECH"]},
    {"label": "Theoretical Uncertainty", "keys": ["PHYS"]},
    {"label": "Interpretive Systems", "keys": ["INTRP"]},
    {"label": "Applied Kindness", "keys": ["CODE"]},
    {"label": "Biological Sciences", "keys": ["BIO"]},
    {"label": "Systemic Continuity", "keys": ["SYS"]},
    {"label": "Emergent Logic", "keys": ["EMRG"]},
    {"label": "Threshold", "keys": ["THRESHOLD"]},
]


def _extract_js_array(html: str, name: str) -> str:
    marker = f"const {name} = "
    start = html.find(marker)
    if start < 0:
        raise SystemExit(f"Could not find {name} in HTML")
    start += len(marker)
    depth = 0
    in_str: str | None = None
    escape = False
    i = start
    while i < len(html):
        ch = html[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return html[start : i + 1]
        i += 1
    raise SystemExit(f"Unclosed array for {name}")


def _js_to_json(js: str) -> str:
    """Best-effort JS array/object → JSON (handles unquoted keys, single quotes, null)."""
    out: list[str] = []
    i = 0
    n = len(js)
    in_str: str | None = None
    escape = False

    def peek_word() -> str | None:
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", js[i:])
        return m.group(0) if m else None

    while i < n:
        ch = js[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            elif in_str == "`":
                pass  # template literal — copy through
            elif in_str == "'" and ch == '"':
                pass
            i += 1
            continue

        if ch in ('"', "`"):
            in_str = ch
            if ch == "`":
                out.append('"')
            else:
                out.append(ch)
            i += 1
            continue

        if ch == "'":
            out.append('"')
            i += 1
            while i < n:
                c = js[i]
                if c == "\\":
                    out.append(c)
                    i += 1
                    if i < n:
                        out.append(js[i])
                        i += 1
                    continue
                if c == "'":
                    out.append('"')
                    i += 1
                    break
                if c == '"':
                    out.append('\\"')
                else:
                    out.append(c)
                i += 1
            continue

        word = peek_word()
        if word in ("null", "true", "false"):
            out.append(word)
            i += len(word)
            continue

        if word and i > 0 and js[i - 1] not in ('"', "'", "]", "}", " ", "\n", "\t", ":", ","):
            pass
        elif word:
            # unquoted key before :
            j = i + len(word)
            while j < n and js[j] in " \t\n\r":
                j += 1
            if j < n and js[j] == ":":
                out.append(f'"{word}"')
                i += len(word)
                continue

        out.append(ch)
        i += 1

    text = "".join(out)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def load_courses(path: Path) -> list[dict]:
    html = path.read_text(encoding="utf-8")
    raw = _extract_js_array(html, "COURSES")
    courses: list[dict] = []
    line_re = re.compile(
        r"\{\s*code:'((?:\\'|[^'])*)',\s*dept_key:'((?:\\'|[^'])*)',\s*"
        r"dept_full:'((?:\\'|[^'])*)',\s*title:'((?:\\'|[^'])*)',\s*"
        r"instructor:'((?:\\'|[^'])*)',\s*credits:'((?:\\'|[^'])*)',\s*"
        r"prereq:'((?:\\'|[^'])*)',\s*cross:([^,]+),\s*desc:'((?:\\'|[^'])*)'"
    )
    for m in line_re.finditer(raw):
        code, dept_key, dept_full, title, instructor, credits, prereq, cross, desc = m.groups()
        cross_val = cross.strip()
        if cross_val == "null":
            cross = None
        else:
            cross = cross_val.strip("'")
        courses.append(
            {
                "code": code.replace("\\'", "'"),
                "dept_key": dept_key.replace("\\'", "'"),
                "dept_full": dept_full.replace("\\'", "'"),
                "title": title.replace("\\'", "'"),
                "instructor": instructor.replace("\\'", "'"),
                "credits": credits.replace("\\'", "'"),
                "prereq": prereq.replace("\\'", "'"),
                "cross": cross,
                "desc": desc.replace("\\'", "'"),
            }
        )
    if not courses:
        raise SystemExit("No courses parsed from courses.html")
    return courses


def load_faculty(path: Path) -> list[dict]:
    html = path.read_text(encoding="utf-8")
    raw = _extract_js_array(html, "FACULTY")
    records = []
    pattern = re.compile(
        r"name:\s*'([^']+)',\s*portrait:\s*'([^']*)'.*?"
        r"bio:\s*(?:'((?:\\'|[^'])*)'|\"((?:\\\"|[^\"])*)\"),\s*"
        r"dept:\s*'((?:\\'|[^'])*)',\s*location:\s*'((?:\\'|[^'])*)',\s*"
        r"course:\s*'((?:\\'|[^'])*)'",
        re.DOTALL,
    )
    for block in pattern.finditer(raw):
        name_, portrait, bio_sq, bio_dq, dept, location, course = block.groups()
        bio = (bio_sq or bio_dq or "").replace("\\'", "'").replace('\\"', '"')
        records.append(
            {
                "name": name_,
                "portrait": portrait,
                "bio": bio,
                "dept": dept.replace("\\'", "'"),
                "location": location.replace("\\'", "'"),
                "course": course.replace("\\'", "'"),
            }
        )
    if not records:
        raise SystemExit("No faculty parsed from faculty.html")
    return records


def extract_paper_cards(html: str, kind: str) -> list[dict]:
    cards = []
    pattern = re.compile(
        r'<article class="research-card">\s*'
        r'<p class="research-label">([^<]+)</p>\s*'
        r"<h3>([^<]+)</h3>\s*"
        r"<p>([^<]+)</p>\s*"
        r'<p class="research-meta">([^<]+)</p>\s*'
        r'<div class="research-actions">\s*'
        r'<button class="btn-read-paper" onclick="openPaper\(\'([^\']+)\',\'([^\']+)\'\)">',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        label, title, summary, meta, file_, modal_label = m.groups()
        cards.append(
            {
                "label": label.strip(),
                "title": title.strip(),
                "summary": summary.strip(),
                "meta": meta.strip(),
                "file": file_.strip(),
                "modal_label": modal_label.strip(),
                "kind": kind,
            }
        )
    return cards


def main() -> None:
    faculty = load_faculty(WEB / "faculty.html")
    slim_courses = load_courses(WEB / "courses.html")
    research = extract_paper_cards(
        (WEB / "research.html").read_text(encoding="utf-8"), "research"
    )
    dispatches = extract_paper_cards(
        (WEB / "dispatches.html").read_text(encoding="utf-8"), "dispatch"
    )

    catalog = {
        "meta": META,
        "admissions": ADMISSIONS,
        "dept_tabs": DEPT_TABS,
        "faculty": faculty,
        "courses": slim_courses,
        "research": research,
        "dispatches": dispatches,
    }

    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(faculty)} faculty, {len(slim_courses)} courses, "
          f"{len(research)} research, {len(dispatches)} dispatches)")


if __name__ == "__main__":
    main()
