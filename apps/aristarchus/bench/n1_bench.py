#!/usr/bin/env python3
"""N1 bench — does the matcher recognize the same decision in different words?

The design doc's open question 2, and the gate on everything downstream: if
the matcher misses re-worded decisions, constraints_on() silently returns
nothing and the system is worse than useless - it is *reassuring*. So: a
number, before anything trusts the traversal.

Three populations, three failure modes:

  paraphrases — the same decision, re-worded. Must resolve to its stored
                key: misses lower RECALL.
  distractors — a DIFFERENT decision wearing similar words (the dangerous
                case). Resolving one to any stored key is a FALSE MATCH -
                the analog of Nestor's false seal.
  novel       — no stored counterpart at all. Resolving to any stored key
                is likewise a FALSE MATCH.

Sweeps the resolve threshold per matcher and writes results to
bench/results/n1.json. Runs through the real code path (DecisionMemory over
a real store, sealed rows), not a matcher in isolation.

Usage:  ARISTARCHUS_SEAL_KEY=bench python3 bench/n1_bench.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("ARISTARCHUS_SEAL_KEY", "bench")

from aristarchus import DecisionMemory, DecisionStore, StringMatcher  # noqa: E402

HERE = Path(__file__).resolve().parent
THRESHOLDS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


class TokenMatcher(StringMatcher):
    """Jaccard over token sets - order-free, the cheap second baseline."""

    def score(self, a: str, b: str) -> float:
        ta, tb = set(self.normalize(a).split()), set(self.normalize(b).split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)


def semantic_matcher():
    """Nestor's intended matcher, if its optional dependency is present.
    Returns None (reported, not hidden) when it is not."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return None
    import numpy as np

    class SemanticMatcher(StringMatcher):
        name = "SemanticMatcher(fastembed)"

        def __init__(self) -> None:
            self.model = TextEmbedding()
            self._cache: dict[str, "np.ndarray"] = {}

        def _embed(self, text: str) -> "np.ndarray":
            key = self.normalize(text)
            if key not in self._cache:
                self._cache[key] = next(iter(self.model.embed([key])))
            return self._cache[key]

        def score(self, a: str, b: str) -> float:
            va, vb = self._embed(a), self._embed(b)
            cos = float(va @ vb / ((va @ va) ** 0.5 * (vb @ vb) ** 0.5))
            return (cos + 1.0) / 2.0   # map [-1,1] -> [0,1]

    try:
        return SemanticMatcher()
    except Exception as exc:            # model download can fail offline
        print(f"  semantic matcher unavailable: {exc}", file=sys.stderr)
        return None


def spacy_matcher():
    """Fallback semantic leg for environments where huggingface.co is
    policy-denied: spaCy's md word vectors (GitHub-released, so reachable
    here). Averaged word vectors, not a sentence encoder - a weaker
    semantic signal than fastembed, and labeled as such in the results."""
    try:
        import spacy
    except ImportError:
        return None

    class SpacyMatcher(StringMatcher):
        name = "SpacyVectors(en_core_web_md)"

        def __init__(self) -> None:
            self.nlp = spacy.load("en_core_web_md",
                                  disable=["parser", "ner", "tagger",
                                           "lemmatizer", "attribute_ruler"])
            self._cache: dict[str, object] = {}

        def _doc(self, text: str):
            key = self.normalize(text)
            if key not in self._cache:
                self._cache[key] = self.nlp(key)
            return self._cache[key]

        def score(self, a: str, b: str) -> float:
            da, db = self._doc(a), self._doc(b)
            if not da.vector_norm or not db.vector_norm:
                return 0.0
            return (float(da.similarity(db)) + 1.0) / 2.0

    try:
        return SpacyMatcher()
    except Exception as exc:
        print(f"  spacy matcher unavailable: {exc}", file=sys.stderr)
        return None


def build_memory(corpus: dict, matcher, threshold: float) -> DecisionMemory:
    store = DecisionStore(":memory:", Path("/tmp") / "n1-bench-ledger.jsonl")
    store.ledger_path.unlink(missing_ok=True)
    mem = DecisionMemory(store, matcher=matcher, threshold=threshold)
    for item in corpus["stored"]:
        d = mem.propose(item["key"], "committed", "bench", author="machine")
        mem.seal(d["id"], "operator")
    return mem


def run_one(corpus: dict, matcher, threshold: float) -> dict:
    mem = build_memory(corpus, matcher, threshold)
    norm = matcher.normalize

    para_total = para_hit = para_wrong = 0
    for item in corpus["stored"]:
        want = norm(item["key"])
        for p in item["paraphrases"]:
            para_total += 1
            c = mem.constraints_on(p)
            if c.live is not None and c.matched_norm == want:
                para_hit += 1
            elif c.live is not None:
                para_wrong += 1          # matched, but to the wrong decision

    false_matches = 0
    intruders = corpus["distractors"] + corpus["novel"]
    for item in intruders:
        c = mem.constraints_on(item["question"])
        # A distractor/novel question resolving to ANY stored key is a false
        # match; its own norm is not stored, so live/lineage/rejections all
        # empty <=> it stayed unmatched.
        if not c.unconstrained:
            false_matches += 1

    mem.store.close()
    return {
        "threshold": threshold,
        "recall": round(para_hit / para_total, 3),
        "wrong_key": round(para_wrong / para_total, 3),
        "false_match": round(false_matches / len(intruders), 3),
        "n_para": para_total, "n_intruders": len(intruders),
    }


def main() -> None:
    corpus = json.loads((HERE / "corpus.json").read_text())
    matchers = [("StringMatcher(difflib)", StringMatcher()),
                ("TokenMatcher(jaccard)", TokenMatcher())]
    sem = semantic_matcher()
    if sem is None:
        sem = spacy_matcher()
    if sem is not None:
        matchers.append((sem.name, sem))
    else:
        print("note: no semantic matcher available - not benched this run "
              "(reported in results, not hidden)")

    results = {"corpus": {"stored": len(corpus["stored"]),
                          "paraphrases": sum(len(s["paraphrases"])
                                             for s in corpus["stored"]),
                          "distractors": len(corpus["distractors"]),
                          "novel": len(corpus["novel"])},
               "semantic_benched": sem is not None,
               "matchers": {}}

    for name, matcher in matchers:
        rows = [run_one(corpus, matcher, t) for t in THRESHOLDS]
        results["matchers"][name] = rows
        print(f"\n{name}")
        print("  thr    recall  wrong-key  false-match")
        for r in rows:
            print(f"  {r['threshold']:.2f}   {r['recall']:6.1%}   "
                  f"{r['wrong_key']:6.1%}     {r['false_match']:6.1%}")

    out = HERE / "results" / "n1.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
