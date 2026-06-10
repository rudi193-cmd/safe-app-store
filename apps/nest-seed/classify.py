"""
nest-seed/classify.py — heuristic fragment classifier.

Given extracted text from a file, returns a list of Fragment dicts.
No LLM required — pure regex/keyword heuristics. Good enough for a
first-pass Nest seed; Willow KB promotion handles the second pass.

Fragment types: person, date, location, event, document, receipt, note, unknown
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
    r"|\w+ \d{1,2},? \d{4}"
    r"|\d{4}[/\-\.]\d{2}[/\-\.]\d{2})\b"
)
_PERSON_PREFIXES = re.compile(
    r"\b(mr\.?|mrs\.?|ms\.?|dr\.?|prof\.?|rev\.?)\s+([A-Z][a-z]+ [A-Z][a-z]+)",
    re.IGNORECASE,
)
_CAPITALIZED_NAME = re.compile(r"\b([A-Z][a-z]{2,} [A-Z][a-z]{2,})\b")
_LOCATION_WORDS = re.compile(
    r"\b(street|st\.|avenue|ave\.|blvd|road|rd\.|city|town|county|state|"
    r"country|province|district|zip|postal)\b",
    re.IGNORECASE,
)
_RECEIPT_WORDS = re.compile(
    r"\b(total|subtotal|receipt|invoice|tax|paid|amount due|"
    r"credit card|cash|change|qty|quantity)\b",
    re.IGNORECASE,
)
_EVENT_WORDS = re.compile(
    r"\b(birthday|anniversary|wedding|graduation|funeral|ceremony|"
    r"appointment|meeting|event|conference|born|died|married)\b",
    re.IGNORECASE,
)


@dataclass
class Fragment:
    fragment_type: str
    content: str
    label: str = ""
    confidence: str = "uncertain"
    date_ref: str = ""


def classify(text: str, filename: str = "") -> list[Fragment]:
    if not text.strip():
        return []

    frags: list[Fragment] = []
    name_lower = filename.lower()

    if _RECEIPT_WORDS.search(text):
        frags.append(Fragment(fragment_type="receipt", content=text[:500],
                              label=filename, confidence="likely"))
        for m in _DATE_RE.finditer(text):
            frags.append(Fragment(fragment_type="date", content=m.group(),
                                  label="receipt_date", confidence="likely", date_ref=m.group()))
        return frags

    event_matches = _EVENT_WORDS.findall(text)
    if event_matches:
        frags.append(Fragment(fragment_type="event", content=text[:800],
                              label=", ".join(set(m.lower() for m in event_matches[:3])),
                              confidence="uncertain"))

    seen_names: set[str] = set()
    for m in _PERSON_PREFIXES.finditer(text):
        name = m.group(2)
        if name not in seen_names:
            seen_names.add(name)
            frags.append(Fragment(fragment_type="person", content=name,
                                  label=m.group(1).rstrip(".").lower(), confidence="likely"))
    for m in _CAPITALIZED_NAME.finditer(text):
        name = m.group(1)
        if name not in seen_names and not any(
            w in name.lower() for w in ("the", "this", "that", "dear", "from", "with")
        ):
            seen_names.add(name)
            frags.append(Fragment(fragment_type="person", content=name, confidence="speculative"))

    for m in _DATE_RE.finditer(text):
        frags.append(Fragment(fragment_type="date", content=m.group(),
                              confidence="likely", date_ref=m.group()))

    if _LOCATION_WORDS.search(text):
        for s in re.split(r"[.!?\n]", text):
            if _LOCATION_WORDS.search(s) and len(s.strip()) > 10:
                frags.append(Fragment(fragment_type="location", content=s.strip()[:300],
                                      confidence="speculative"))
                break

    if any(name_lower.endswith(x) for x in (".jpg", ".jpeg", ".png", ".tiff", ".webp")):
        frags.append(Fragment(fragment_type="photo",
                              content=text[:400] if text.strip() else f"[image: {filename}]",
                              label=filename,
                              confidence="confirmed" if text.strip() else "uncertain"))

    if not frags:
        frags.append(Fragment(fragment_type="document", content=text[:600],
                              label=filename, confidence="uncertain"))

    return frags
