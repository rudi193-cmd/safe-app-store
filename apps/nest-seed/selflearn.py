"""
nest-seed/selflearn.py — self-learning centroids + clustering discovery.

taxonomy.py builds *static* category centroids from curated exemplars. This
module is the "adapts to your data" layer the taxonomy docstring promises: the
user's own confidently-classified documents are folded back into the centroids
so the Nest learns what *their* legal filings, journals, and receipts actually
look like.

Two capabilities, both pure-stdlib (no numpy) and degrading gracefully:

  build_adaptive_centroids(model)
      Exemplar centroids + the learned-member store, combined by an exact mean:
          combined = (exemplar_centroid * n_exemplars + Σ learned) / (n_ex + n_learned)
      This needs only the cached exemplar centroid and the exemplar count, so it
      never re-embeds the exemplars. Cached to disk keyed by
      (model, exemplar-hash, learned-hash) — recomputed only when either changes.
      With no learned members it returns the plain exemplar centroids unchanged,
      so it is a safe drop-in for taxonomy.build_centroids().

  discover(items, k)
      Spherical k-means over (vector, snippet) pairs — clusters the low-margin /
      unknown tail to surface categories the exemplars are missing. Report-only.

Learning is deliberately conservative: only `confirmed`-band classifications
(margin ≥ 0.10) are recorded, deduped by source hash, and capped per category
(highest-margin kept). This limits the confirmation-bias risk of a classifier
learning from its own least-certain guesses.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable, Optional

try:  # works both as a package (apps.nest_seed) and as a plain script dir
    from . import embed as _embed
    from . import taxonomy as _tax
except ImportError:
    import embed as _embed
    import taxonomy as _tax

# Only the most confident band feeds the centroids (see module docstring).
LEARN_MIN_MARGIN = float(os.environ.get("NEST_LEARN_MIN_MARGIN", "0.10"))
LEARN_MAX_PER_CAT = int(os.environ.get("NEST_LEARN_MAX_PER_CAT", "50"))

# Type of the per-doc hook classify() calls: (category, vec, margin, confidence).
LearnSink = Callable[[str, list, float, str], None]


# --- learned-member store ---------------------------------------------------

def _cache_dir() -> Path:
    return Path(os.environ.get("NEST_CACHE_DIR", Path.home() / ".cache" / "nest-seed"))


def _learned_path(model: str) -> Path:
    safe = model.replace("/", "_").replace(":", "_")
    return _cache_dir() / f"learned_{safe}.json"


def load_learned(model: str) -> dict[str, list[dict]]:
    """Return {category: [{"vec":[...], "hash":str, "margin":float}, ...]}."""
    p = _learned_path(model)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_learned(model: str, store: dict[str, list[dict]]) -> None:
    p = _learned_path(model)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store))
    except OSError:
        pass


def learned_hash(model: str) -> str:
    """Stable fingerprint of the learned store — part of the centroid cache key."""
    store = load_learned(model)
    sig = {cat: sorted(e.get("hash", "") for e in entries)
           for cat, entries in store.items()}
    return hashlib.sha256(json.dumps(sig, sort_keys=True).encode()).hexdigest()[:12]


def merge_learned(model: str, observations: list[dict], *,
                  min_margin: float | None = None,
                  max_per_cat: int | None = None) -> dict:
    """Fold new confident observations into the learned store on disk.

    observations: [{"category","vec","margin","hash"}]. Deduped by hash within a
    category; each category capped to the highest-margin `max_per_cat`.
    Returns a summary {added, per_category, total}.

    Defaults are resolved at call time from the module globals (which honour the
    NEST_LEARN_* env vars), not bound at import.
    """
    if min_margin is None:
        min_margin = LEARN_MIN_MARGIN
    if max_per_cat is None:
        max_per_cat = LEARN_MAX_PER_CAT
    store = load_learned(model)
    added = 0
    for obs in observations:
        if obs.get("margin", 0.0) < min_margin or not obs.get("vec"):
            continue
        cat = obs["category"]
        bucket = store.setdefault(cat, [])
        h = obs.get("hash", "")
        existing = next((e for e in bucket if e.get("hash") == h), None) if h else None
        if existing:
            existing["margin"] = max(existing.get("margin", 0.0), obs["margin"])
            continue
        bucket.append({"vec": obs["vec"], "hash": h, "margin": obs["margin"]})
        added += 1

    # cap each category to the strongest members
    for cat, bucket in store.items():
        if len(bucket) > max_per_cat:
            bucket.sort(key=lambda e: e.get("margin", 0.0), reverse=True)
            store[cat] = bucket[:max_per_cat]

    save_learned(model, store)
    return {
        "added": added,
        "total": sum(len(v) for v in store.values()),
        "per_category": {c: len(v) for c, v in store.items()},
    }


# --- adaptive centroids -----------------------------------------------------

def _adaptive_cache_path(model: str) -> Path:
    safe = model.replace("/", "_").replace(":", "_")
    return _cache_dir() / f"centroids_adaptive_{safe}_{_tax._seeds_hash()}_{learned_hash(model)}.json"


def build_adaptive_centroids(model: str = _embed.DEFAULT_EMBED_MODEL,
                             use_cache: bool = True) -> Optional[dict[str, list[float]]]:
    """Exemplar centroids folded with the user's learned members.

    Drop-in for taxonomy.build_centroids(): identical result when nothing has
    been learned yet. Returns None only if exemplar embeddings are unavailable.
    """
    base = _tax.build_centroids(model=model, use_cache=use_cache)
    if base is None:
        return None
    learned = load_learned(model)
    if not learned:
        return base

    cache = _adaptive_cache_path(model)
    if use_cache and cache.exists():
        try:
            return json.loads(cache.read_text())
        except (OSError, ValueError):
            pass

    out: dict[str, list[float]] = {}
    for cat, centroid in base.items():
        members = [e["vec"] for e in learned.get(cat, []) if e.get("vec")]
        n_ex = len(_tax.EXEMPLARS.get(cat, [])) or 1
        if not members:
            out[cat] = centroid
            continue
        dim = len(centroid)
        n_total = n_ex + len(members)
        # exact mean of (exemplars + learned): exemplar sum = centroid * n_ex
        out[cat] = [
            (centroid[i] * n_ex + sum(v[i] for v in members)) / n_total
            for i in range(dim)
        ]

    if use_cache:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(out))
        except OSError:
            pass
    return out


# --- per-run observation collector ------------------------------------------

class Recorder:
    """Collects classify()'s per-doc observations during an ingest run.

    `confident` feeds the learned store; `tail` (uncertain/speculative/unknown)
    feeds clustering discovery. Both reuse the embedding classify already
    computed — no extra model calls.
    """

    def __init__(self) -> None:
        self.confident: list[dict] = []
        self.tail: list[dict] = []

    def sink_for(self, *, key: str, snippet: str) -> LearnSink:
        """A per-file hook bound to this file's hash + snippet."""
        def _sink(category: str, vec: list, margin: float, confidence: str) -> None:
            if confidence == "confirmed":
                self.confident.append(
                    {"category": category, "vec": vec, "margin": margin, "hash": key})
            elif confidence in ("uncertain", "speculative"):
                self.tail.append({"vec": vec, "snippet": snippet, "category": category})
        return _sink

    def flush_learned(self, model: str) -> dict:
        return merge_learned(model, self.confident)


# --- clustering discovery (pure-python spherical k-means) -------------------

def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def discover(items: list[dict], k: int = 6, iters: int = 25) -> dict:
    """Cluster (vec, snippet) items into k groups by spherical k-means.

    items: [{"vec":[...], "snippet":str}]. Report-only — surfaces candidate
    categories the exemplars don't cover. Deterministic (fixed init).
    """
    pts = [(_normalize(it["vec"]), it.get("snippet", "")) for it in items if it.get("vec")]
    if len(pts) < k:
        return {"status": "noop", "reason": f"only {len(pts)} items for k={k}"}

    # deterministic init: evenly spaced picks across the list
    step = max(1, len(pts) // k)
    centers = [pts[i * step][0][:] for i in range(k)]
    labels = [0] * len(pts)

    for _ in range(iters):
        changed = False
        for i, (v, _s) in enumerate(pts):
            best = max(range(k), key=lambda c: _dot(v, centers[c]))
            if best != labels[i]:
                labels[i] = best
                changed = True
        for c in range(k):
            members = [v for (v, _s), lab in zip(pts, labels) if lab == c]
            if members:
                dim = len(members[0])
                mean = [sum(m[i] for m in members) / len(members) for i in range(dim)]
                centers[c] = _normalize(mean)
        if not changed:
            break

    clusters = []
    for c in range(k):
        idx = [i for i, lab in enumerate(labels) if lab == c]
        if not idx:
            continue
        rep_i = max(idx, key=lambda i: _dot(pts[i][0], centers[c]))
        clusters.append({
            "size": len(idx),
            "representative": pts[rep_i][1][:140],
        })
    clusters.sort(key=lambda c: c["size"], reverse=True)
    return {"status": "ok", "n_items": len(pts), "clusters": clusters}
