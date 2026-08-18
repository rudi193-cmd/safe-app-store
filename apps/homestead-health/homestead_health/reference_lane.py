"""The reference lane — public knowledge, pinned, read but never joined to a child.

The records track holds *this household's* facts; the living lane holds a worry in
motion. This lane holds the third posture the extension names: **public knowledge** —
a household asking its own health questions, and asking how to talk about them, with
a doctor, a teen, an aging parent. That is retrieval against public reference, not
advice, and the whole of this module is the wall that keeps it so.

## H-7, and the wall against H-2

The reference lane is **H-5 widened**: from one pinned schedule to a pinned,
versioned, public-domain corpus, served by an **injected reader** — ship the reader,
the corpus stays with whoever grew it (the fleet's sealed rule). It **never dials**
(I-17): the bytes are here, frozen, and no link is resolved at runtime. It **holds no
subject**: the corpus is general knowledge, keyed by question, carrying no person, and
the reader takes a *question*, never a subject.

That last point is the wall against H-2 (*no symptom-checker, at any version*):
**the reference lane and a subject's record never meet on the same surface.** The
reader retrieves what the public source *says*; it never joins that text to *this
child's* record to interpret, triage, or recommend. Retrieval of public reference is
not the practice of medicine — composing it against a subject is. The wall is a seam
this module cannot cross rather than a disclaimer: there is no subject parameter
anywhere in it, and it imports nothing that carries one (no roster, no record, no
gate). It cannot join to a child because it never receives one.

## Attribution rides through

The corpus is assembled from public-domain and permissively-licensed parts, and the
attribution a part carries rides through to every answer that quotes it — a `source`
and `license` on the entry, surfaced on the `Result`, not a footnote someone can
forget. A CC-BY part's credit appears on every answer drawn from it, by construction.

## Not advice, and not exhaustive

Every entry is general health-literacy or conversation-prep reference, cited to a
public source. Nothing here is tailored to a person, and nothing recommends care
(H-2). Like H-5's schedule, this is a representative pinned snapshot the operator
verifies and grows against the cited sources — the almanac's catalog (face 3) is the
record of *where* the live sources live; this module pins only what it carries and
the date it pinned it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

__all__ = ["Entry", "Corpus", "Result", "Reader", "CORPUS"]


@dataclass(frozen=True)
class Entry:
    """One piece of public reference — a question, what a public source says, and
    the credit that source carries. Holds no person: the answer is the same for any
    household, which is what makes it public reference and keeps it clear of H-2."""

    question: str
    answer: str
    source: str
    license: str


@dataclass(frozen=True)
class Corpus:
    """A pinned snapshot of public reference, versioned and dated like H-5's schedule.

    `version`/`as_of` are required and `as_of` is a literal pin (a computed date would
    be a live feed in disguise — H-5's lesson). `entries` is the reference itself,
    keyed by question, holding no subject.
    """

    version: str
    as_of: date
    entries: tuple[Entry, ...]

    def citation(self) -> str:
        return f"{self.version}, pinned as of {self.as_of.isoformat()}"


#: The closed field sets — an allowlist, so the "holds no subject" guarantee is
#: structural (H-5's fix, carried here): a field added to either shape that could
#: carry a person fails the build, by name, rather than slipping past a denylist.
_ENTRY_FIELDS = frozenset({"question", "answer", "source", "license"})
_CORPUS_FIELDS = frozenset({"version", "as_of", "entries"})


def _check_no_subject_can_enter() -> None:
    entry = frozenset(Entry.__dataclass_fields__)
    corpus = frozenset(Corpus.__dataclass_fields__)
    if entry != _ENTRY_FIELDS:
        raise RuntimeError(
            f"Entry fields are {sorted(entry)}, not {sorted(_ENTRY_FIELDS)}. Public "
            "reference is keyed by question and carries a citation only; a field "
            "outside that set is where a subject would enter, and this lane holds "
            "none (H-7). Update the allowlist deliberately, with a reason that "
            "survives that wall."
        )
    if corpus != _CORPUS_FIELDS:
        raise RuntimeError(
            f"Corpus fields are {sorted(corpus)}, not {sorted(_CORPUS_FIELDS)}. A new "
            "field on the snapshot is where a subject would enter — the allowlist is "
            "the wall, updated deliberately, never by drift."
        )


_check_no_subject_can_enter()


def _entry(question: str, answer: str, source: str, license: str) -> Entry:
    return Entry(question=question, answer=answer, source=source, license=license)


#: The pinned corpus. A representative public-domain / permissively-licensed set of
#: health-literacy and conversation-prep reference — general, cited, not advice, and
#: not exhaustive. A new edition replaces this literal in a dated commit, never a
#: runtime fetch (H-5's operator act). ASCII-clean: the text may be quoted back to a
#: household, where a clean encoding is the safe default.
CORPUS = Corpus(
    version="Homestead Health reference corpus (public-domain health literacy)",
    as_of=date(2026, 8, 18),
    entries=(
        _entry(
            "How can I prepare for my child's checkup?",
            "Bring the immunization record and a list of current medications, write "
            "down the questions you want to ask beforehand, and note any changes you "
            "have observed since the last visit. Preparing questions ahead helps you "
            "cover what matters in a short appointment.",
            "U.S. Agency for Healthcare Research and Quality (AHRQ), Questions To Ask "
            "Your Doctor",
            "public domain",
        ),
        _entry(
            "What questions can I ask the doctor about a vaccine?",
            "You can ask what the vaccine protects against, when the next dose is due, "
            "which common reactions to expect, and which reactions are worth calling "
            "about. Asking about the schedule and about what to watch for are ordinary, "
            "expected questions.",
            "U.S. Centers for Disease Control and Prevention (CDC), Talking with "
            "Parents about Vaccines",
            "public domain",
        ),
        _entry(
            "How do I talk with a teenager about their own health?",
            "Offer privacy, listen more than you direct, and let them lead where they "
            "can — adolescents take on more of their own care over time, and a "
            "conversation that respects that tends to go further than one that does "
            "not. Ask what they already know before adding to it.",
            "U.S. National Institutes of Health (NIH), Talking With Your Teen",
            "public domain",
        ),
        _entry(
            "What does an immunization record show?",
            "An immunization record lists each vaccine given, the date of each dose, "
            "and which doses in a series are complete. It is the document a school or "
            "a new clinic typically asks for, and keeping your own copy means you are "
            "not waiting on someone else's.",
            "MedlinePlus (U.S. National Library of Medicine), Immunization Records",
            "public domain",
        ),
        _entry(
            "How can I prepare to help an aging parent at a medical visit?",
            "Agree in advance on what you are there to do, bring the medication list "
            "and the questions, and let them answer for themselves wherever they can. "
            "Being present is not the same as speaking for someone, and the difference "
            "matters to the person whose visit it is.",
            "U.S. National Institute on Aging (NIA), Going to the Doctor",
            "public domain",
        ),
        _entry(
            "Why keep household health records myself?",
            "A record you hold is one you can produce when a school, a new provider, or "
            "an urgent visit asks for it, without waiting on a portal or a transfer. "
            "Holding your own copy is a practical hedge, not a substitute for your "
            "clinician's records.",
            "Open Health Literacy Project, Keeping Your Own Records (example CC-BY part)",
            "CC-BY-4.0",
        ),
    ),
)


@dataclass(frozen=True)
class Result:
    """One answer the reader found, with its credit attached. `attribution` is the
    source and its license together — the credit that rides through to any surface
    that quotes the answer, so a CC-BY part is never quoted without it."""

    entry: Entry
    score: int

    @property
    def attribution(self) -> str:
        return f"{self.entry.source} ({self.entry.license})"


#: Words too common to carry a question's meaning — dropped before matching, so
#: overlap counts the terms that distinguish one question from another.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "for", "with", "about", "how", "what",
    "why", "when", "can", "i", "my", "do", "does", "is", "are", "in", "on", "at", "it",
    "this", "that", "you", "your", "me", "we", "our", "help", "ask", "asking",
})

_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1}


class Reader:
    """An injected reader over a pinned corpus. Takes a question, returns cited
    answers — and takes **no subject, ever.**

    The corpus is injected (defaulting to the pinned `CORPUS`), so a host could hand
    a larger one without changing the reader — ship the reader, the corpus stays with
    whoever grew it. The retrieval is a simple term overlap over public reference: no
    embeddings, no model, no network, no link resolved at runtime. When nothing
    overlaps, it returns nothing rather than improvising — a reference lane that
    invents an answer is the symptom-checker H-2 forbids.
    """

    def __init__(self, corpus: Corpus | None = None) -> None:
        self._corpus = corpus if corpus is not None else CORPUS

    @property
    def corpus(self) -> Corpus:
        return self._corpus

    def ask(self, question: str, *, limit: int = 3, min_confidence: float = 0.5) -> list[Result]:
        """Cited answers from the pinned corpus for a household's question.

        Two decisions, kept separate — the discipline Jeles's reader established
        (`docs/promotion/recon/jeles.md`): **ranking** and **answering** are not the
        same question. Each entry is *ranked* by how many distinguishing terms it
        shares with the question (`Result.score`); an entry only *answers* if its
        share of the question's own terms clears `min_confidence` (a recall gate —
        `matched / asked`). So a weak lexical brush-past — one common word floating a
        barely-related entry to the top — returns **nothing** rather than a
        misleading citation. That is the same "a reference lane that invents an
        answer is the symptom-checker H-2 forbids" instinct the lane already had for
        zero overlap, now extended to near-zero overlap. `min_confidence=0.0` restores
        the old any-overlap behaviour for a caller that wants raw ranking.

        There is no subject parameter and there never will be: joining public
        reference to a particular person is the wall this lane does not cross
        (H-7/H-2).
        """
        if not isinstance(question, str) or not question.strip():
            raise ValueError("ask() takes a question (a non-empty string)")
        asked = _terms(question)
        if not asked:
            return []
        scored: list[Result] = []
        for entry in self._corpus.entries:
            matched = len(asked & _terms(entry.question))
            if matched and matched / len(asked) >= min_confidence:
                scored.append(Result(entry=entry, score=matched))
        scored.sort(key=lambda r: (-r.score, r.entry.question))
        return scored[:limit]
