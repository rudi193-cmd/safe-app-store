"""die_namic.binder: ask the GM's binder in your own words. Python 3.9+.

Die-Namic's semantic-search seam: the reader ships here, the corpus stays
with whoever grew it. A `Binder` is handed its passages and the ranker to
read them with; it never reads a folder, a model or the network itself.

It asks the way willow's own UI searches for add-ons (willow ui/canvas.py,
`search`), turned to a binder's pages:

1. your words, and each pair of them run together ("spring wasps" is also
   "springwasps");
2. read through the GM's words list, how they ask and the binder's words for
   it (`dog = hound`), each binder word remembering the word of yours it
   stands for;
3. ranked by the ranker handed in, over everything you said and what it
   means (willow's pile-rank BM25F, in the box);
4. then put in tiers: a page you named first ("the wasps" names
   monsters/spring-wasps.md), then a page one of your words usually means
   ("the keeper" means cogwen), then the ranking, each passage saying why.

It points at where to look; it is not an answer. Willow's kernel serves a
passage only when it holds half the question's words; this serves the best
passages whatever they hold, as pile-rank does, and a passage it serves is
the binder's own words with its page and line, never a summary.

The pieces it is handed:

    passages  [{"path": "monsters/clockwork-hound.md", "line": 5, "text": ...}]
              (willow's kernel.chunks over the binder)
    ranker    a factory taking the passages, whose .rank(question, top)
              gives (passage, score, phrases) best first (pile-rank's Ranker)
    means     the words list, {"dog": ["hound"]} (willow's kernel.parse_words)
    words     a text's words, lowercased (kernel.words; a plain default here)
    common    words that name nothing ("the", "what"; kernel.FUNCTION)
    plain     a word's plain form, so "hounds" holds "hound" (kernel.stem)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

WORD = re.compile(r"[^\W_]+")


def plain_words(text: str) -> list[str]:
    """A text's words, lowercased and composed: the kernel's own rule, so the
    core reads alike with or without willow handed in."""
    return WORD.findall(unicodedata.normalize("NFC", text.lower()))


@dataclass(frozen=True)
class Found:
    """One place to look: a passage of the binder, where it is, and why."""

    path: str
    line: int
    text: str
    score: float
    why: str

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"


class Binder:
    """The GM's binder, asked in their own words. Everything it reads with is
    handed in; see the module's docstring."""

    def __init__(
        self,
        passages: Iterable[Mapping[str, Any]],
        ranker: Callable[[list], Any],
        means: Mapping[str, Sequence[str]] | None = None,
        *,
        words: Callable[[str], list[str]] = plain_words,
        common: Iterable[str] = (),
        plain: Callable[[str], str] = lambda w: w,
    ):
        self.passages = list(passages)
        for c in self.passages:
            if not {"path", "line", "text"} <= set(c):
                raise ValueError("a passage has its path, line and text")
        self.rank = ranker(self.passages).rank
        self.means = {k: list(v) for k, v in (means or {}).items()}
        self.words, self.common, self.plain = words, frozenset(common), plain

    def _named(self, path: str, said: Sequence[str]) -> str | None:
        """The part of a page's name you said, if any: monsters/spring-wasps.md
        is named by "spring-wasps", "spring" or "wasps" (three letters or more,
        not a common word)."""
        name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return next((p for p in [name, *name.split("-")]
                     if p in said and len(p) >= 3 and p not in self.common), None)  # fmt: skip

    def ask(self, question: str, top: int = 6) -> list[Found]:
        """The places to look for `question`, best first: pages you named,
        then what your words usually mean, then the ranking. Empty when no
        passage holds a word of it."""
        said = self.words(question)
        if not said:
            return []
        asked = said + [a + b for a, b in zip(said, said[1:])]
        stands: dict[str, str] = {}  # a binder word, and the word of yours it stands for
        for w in asked:
            for m in self.means.get(w, []):
                stands.setdefault(m, w)
        query = " ".join(dict.fromkeys(asked + list(stands)))
        ranked = list(self.rank(query, top * 2))
        meant = list(stands)

        def tier(r) -> int:
            path = r[0]["path"]
            return 0 if self._named(path, asked) else 1 if self._named(path, meant) else 2

        ranked.sort(key=tier)  # stable: the ranking's order within each tier
        yours = {}
        for w in asked + meant:
            yours.setdefault(self.plain(w), w)
        out = []
        for c, score, phrases in ranked[:top]:
            if self._named(c["path"], asked):
                why = "you named its page"
            elif part := self._named(c["path"], meant):
                why = f"what “{stands[part]}” usually means here"
            else:
                held = [t for t in dict.fromkeys(self.plain(w) for w in self.words(c["text"]))
                        if t in yours and yours[t] not in self.common]  # fmt: skip
                said_ = [yours[t] for t in held] or list(phrases)
                why = f"holds {', '.join(said_[:4])}" if said_ else "close to what you said"
            out.append(Found(str(c["path"]), int(c["line"]), str(c["text"]), float(score), why))
        return out
