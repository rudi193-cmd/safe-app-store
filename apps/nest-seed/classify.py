"""
nest-seed/classify.py — hybrid fragment classifier.

Given extracted text (and optionally the file path) returns a list of
Fragment dicts.

Two modes:
  * use_llm=False (default) — pure regex/keyword heuristics. No network,
    no models. Good enough for a first-pass seed; Willow KB promotion
    handles the second pass. This is the original, portable behaviour.
  * use_llm=True — local AI via Ollama (see llm.py). A small text model
    assigns the fragment_type + topical category + a one-line summary;
    a vision model reads images. Regex still runs a cheap deterministic
    pre-pass (dates, receipts, titled names) to enrich the LLM verdict.
    If Ollama is unreachable or the model is missing, every file falls
    back to the regex path — so use_llm=True never *fails*, it degrades.

Fragment types: person, date, location, event, document, photo, note,
receipt, unknown. When the LLM is on, each document also carries a
topical `label` (legal, journal, knowledge, narrative, specs, code,
correspondence, financial, education, personal, media, config, data,
other) — this is what empties the "unknown" pile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:  # works both as a package (apps.nest_seed) and as a plain script dir
    from . import llm as _llm
except ImportError:
    import llm as _llm

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

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp")


@dataclass
class Fragment:
    fragment_type: str
    content: str
    label: str = ""
    confidence: str = "uncertain"
    date_ref: str = ""


# --- cheap deterministic extractors (reused by both modes) ------------------

def _date_fragments(text: str) -> list[Fragment]:
    return [
        Fragment(fragment_type="date", content=m.group(),
                 confidence="likely", date_ref=m.group())
        for m in _DATE_RE.finditer(text)
    ]


def _titled_person_fragments(text: str, seen: set[str]) -> list[Fragment]:
    frags: list[Fragment] = []
    for m in _PERSON_PREFIXES.finditer(text):
        name = m.group(2)
        if name not in seen:
            seen.add(name)
            frags.append(Fragment(fragment_type="person", content=name,
                                  label=m.group(1).rstrip(".").lower(), confidence="likely"))
    return frags


# --- main entry -------------------------------------------------------------

def classify(text: str, filename: str = "", path: "Path | None" = None,
             use_llm: bool = False, text_model: str | None = None,
             vision_model: str | None = None) -> list[Fragment]:
    name_lower = filename.lower()
    is_image = any(name_lower.endswith(x) for x in _IMAGE_EXTS)

    # An image with no OCR text but LLM on → vision describes it directly.
    if not text.strip() and not (is_image and use_llm):
        return []

    if use_llm:
        frags = _classify_llm(text, filename, path, is_image,
                              text_model=text_model, vision_model=vision_model)
        if frags is not None:
            return frags
        # LLM unreachable / model missing → fall through to regex.

    return _classify_regex(text, filename, name_lower, is_image)


# --- LLM path ---------------------------------------------------------------

def _classify_llm(text: str, filename: str, path: "Path | None", is_image: bool,
                  text_model: str | None, vision_model: str | None) -> "list[Fragment] | None":
    """Return fragments via local AI, or None if the model is unavailable."""
    frags: list[Fragment] = []

    if is_image and path is not None:
        verdict = _llm.describe_image(path, model=vision_model or _llm.DEFAULT_VISION_MODEL)
        if verdict is None and not text.strip():
            return None  # vision down and nothing to read → let caller fall back
        if verdict is not None:
            frags.append(Fragment(
                fragment_type="photo",
                content=verdict["summary"] or f"[image: {filename}]",
                label=verdict["category"],
                confidence=verdict["confidence"],
            ))
            frags.extend(_date_fragments(text))  # any OCR'd dates
            return frags
        # had OCR text but vision failed → classify that text below.

    verdict = _llm.classify_text(text, filename,
                                 model=text_model or _llm.DEFAULT_TEXT_MODEL)
    if verdict is None:
        return None

    content = verdict["summary"] or text[:300]
    frags.append(Fragment(
        fragment_type="photo" if is_image else verdict["fragment_type"],
        content=content,
        label=verdict["category"],
        confidence=verdict["confidence"],
    ))
    # Enrich with cheap, high-precision deterministic signals.
    frags.extend(_titled_person_fragments(text, set()))
    frags.extend(_date_fragments(text))
    return frags


# --- regex path (original behaviour, unchanged logic) -----------------------

def _classify_regex(text: str, filename: str, name_lower: str,
                    is_image: bool) -> list[Fragment]:
    if not text.strip():
        # Image with no OCR text and no LLM — record it as an opaque photo.
        if is_image:
            return [Fragment(fragment_type="photo",
                            content=f"[image: {filename}]",
                            label=filename, confidence="uncertain")]
        return []

    frags: list[Fragment] = []

    if _RECEIPT_WORDS.search(text):
        frags.append(Fragment(fragment_type="receipt", content=text[:500],
                              label=filename, confidence="likely"))
        frags.extend(_date_fragments(text))
        return frags

    event_matches = _EVENT_WORDS.findall(text)
    if event_matches:
        frags.append(Fragment(fragment_type="event", content=text[:800],
                              label=", ".join(set(m.lower() for m in event_matches[:3])),
                              confidence="uncertain"))

    seen_names: set[str] = set()
    frags.extend(_titled_person_fragments(text, seen_names))
    for m in _CAPITALIZED_NAME.finditer(text):
        name = m.group(1)
        if name not in seen_names and not any(
            w in name.lower() for w in ("the", "this", "that", "dear", "from", "with")
        ):
            seen_names.add(name)
            frags.append(Fragment(fragment_type="person", content=name, confidence="speculative"))

    frags.extend(_date_fragments(text))

    if _LOCATION_WORDS.search(text):
        for s in re.split(r"[.!?\n]", text):
            if _LOCATION_WORDS.search(s) and len(s.strip()) > 10:
                frags.append(Fragment(fragment_type="location", content=s.strip()[:300],
                                      confidence="speculative"))
                break

    if is_image:
        frags.append(Fragment(fragment_type="photo",
                              content=text[:400] if text.strip() else f"[image: {filename}]",
                              label=filename,
                              confidence="confirmed" if text.strip() else "uncertain"))

    if not frags:
        frags.append(Fragment(fragment_type="document", content=text[:600],
                              label=filename, confidence="uncertain"))

    return frags
