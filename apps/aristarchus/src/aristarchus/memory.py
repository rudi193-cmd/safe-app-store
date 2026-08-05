"""aristarchus.memory — the DecisionMemory recipe and the traversal.

The recipe mirrors Nestor's EntityResolver shape: a thin class over the
store, with the only domain-specific judgment - "when are two questions the
same decision?" - behind a two-method Matcher seam (N1). The unit of a
decision is whatever the matcher normalizes to the same key; a differently
worded question is the same decision iff the matcher says so. That makes the
unit tunable and measurable rather than an ontology frozen in a schema, and
it makes the matcher the load-bearing joint: N1's accuracy is a number to
bench, not an assumption (design doc, open question 2).

`constraints_on()` is the whole point. Not "what is the answer" but "what
does what we already committed to constrain about what I am proposing":
the live decision with its reason, the lineage with each replacement's
reason, the rejected alternatives with theirs, any rejection whose
reopen_when names a condition to re-check, and the graph neighbours.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .store import DecisionStore

SEAL_THRESHOLD = 0.90


class Matcher(Protocol):
    """The two-method seam. Everything domain-specific lives behind it."""

    def normalize(self, text: str) -> str: ...

    def score(self, a: str, b: str) -> float: ...


class StringMatcher:
    """Casefold, strip punctuation, collapse whitespace; score by character
    ratio. Deliberately the dumb baseline: the design doc names a semantic
    matcher as the intended one, and the bench that compares them (N1) is
    the gate before any CI check trusts this traversal."""

    def normalize(self, text: str) -> str:
        text = re.sub(r"[^\w\s]", " ", text.casefold())
        return " ".join(text.split())

    def score(self, a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, self.normalize(a),
                                       self.normalize(b)).ratio()


@dataclass
class Constraints:
    """What the record says about a question before anyone re-decides it."""

    question_norm: str
    matched_norm: str = ""          # the stored key the matcher resolved to
    match_score: float = 1.0
    live: Optional[dict[str, Any]] = None
    lineage: list[dict[str, Any]] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    reopeners: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    tampered: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unconstrained(self) -> bool:
        return (self.live is None and not self.lineage
                and not self.rejections and not self.tampered)


class DecisionMemory:
    """propose / seal / reject / supersede / constraints_on over one domain."""

    def __init__(self, store: DecisionStore, domain: str = "decision",
                 matcher: Optional[Matcher] = None,
                 threshold: float = SEAL_THRESHOLD) -> None:
        self.store = store
        self.domain = domain
        self.matcher = matcher or StringMatcher()
        self.threshold = threshold

    # -- writes (thin: the covenant is enforced in the store) -------------

    def propose(self, question: str, commitment: str, rationale: str = "",
                author: str = "") -> dict[str, Any]:
        return self.store.propose(question, self.matcher.normalize(question),
                                  commitment, rationale, author, self.domain)

    def seal(self, decision_id: str, verifier: str,
             reason: str = "") -> dict[str, Any]:
        return self.store.seal(decision_id, verifier, reason)

    def reject(self, question: str, option: str, reason: str, verifier: str,
               reopen_when: str = "") -> dict[str, Any]:
        return self.store.reject(self.matcher.normalize(question), option,
                                 reason, verifier, reopen_when, self.domain)

    def supersede(self, old_id: str, commitment: str, reason: str,
                  verifier: str, author: str = "") -> dict[str, Any]:
        return self.store.supersede(old_id, commitment, reason, verifier,
                                    author)

    # -- the traversal ----------------------------------------------------

    def _resolve_key(self, question_norm: str) -> tuple[str, float]:
        """Exact key first; else the matcher's best candidate at or above
        threshold; else the question's own norm (unconstrained). A re-worded
        question resolving to its stored twin is the whole game (N1)."""
        known = self.store.all_questions(self.domain)
        if question_norm in known:
            return question_norm, 1.0
        best, best_score = "", 0.0
        for cand in known:
            s = self.matcher.score(question_norm, cand)
            if s > best_score:
                best, best_score = cand, s
        if best and best_score >= self.threshold:
            return best, best_score
        return question_norm, 1.0

    def constraints_on(self, question: str) -> Constraints:
        norm = self.matcher.normalize(question)
        key, score = self._resolve_key(norm)
        c = Constraints(question_norm=norm, matched_norm=key,
                        match_score=score)

        live = self.store.live(key, self.domain)
        if live is not None:
            if live["status"] == "tampered":
                c.tampered.append(live)
            else:
                c.live = live
                c.lineage = self.store.lineage(live["id"])
                c.edges = self.store.edges_for(live["id"])

        for r in self.store.rejections_for(key, self.domain):
            if r.get("tampered"):
                c.tampered.append(r)
            elif r["reopen_when"]:
                c.reopeners.append(r)   # not-yet: a condition to re-check
            else:
                c.rejections.append(r)  # never: a closed door, with a reason
        return c
