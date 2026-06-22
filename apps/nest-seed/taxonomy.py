"""
nest-seed/taxonomy.py — semantic category prototypes for the embedding tier.

Each category is defined by a handful of natural-language seed phrases. We embed
the seeds (with the query prefix) and average them into a centroid vector. A
document is classified by cosine similarity to the nearest centroid; the score
*is* the confidence, and the gap to the runner-up tells us whether to trust the
embedding tier or escalate to the generative LLM.

Centroids are deterministic for a given (model, seeds) pair, so they're cached
to disk — embedding the seeds once instead of every run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

try:  # works both as a package (apps.nest_seed) and as a plain script dir
    from . import embed as _embed
except ImportError:
    import embed as _embed

# Topical categories. Keep seeds short, concrete, and varied — they define the
# region of meaning each category occupies. Order is irrelevant.
CATEGORIES: dict[str, list[str]] = {
    "legal": [
        "a legal letter or court filing about a lawsuit",
        "a custody, bankruptcy, or workers compensation case document",
        "a contract, settlement, or sworn legal statement",
    ],
    "journal": [
        "a personal journal entry or daily log",
        "session notes reflecting on work that was done",
        "a diary of thoughts, plans, and reflections",
    ],
    "knowledge": [
        "an explanatory reference article",
        "a technical writeup explaining how a concept works",
        "documentation or an analysis of a subject",
    ],
    "narrative": [
        "a short story or creative fiction",
        "narrative prose with characters and a plot",
    ],
    "specs": [
        "a software specification or design document",
        "a technical implementation plan with requirements",
    ],
    "code": [
        "python source code with functions, classes, and import statements",
        "a shell, javascript, or sql program with logic and control flow",
    ],
    "correspondence": [
        "an email message between people",
        "a personal letter written to someone",
    ],
    "financial": [
        "a receipt or invoice with dollar amounts and totals",
        "a bank statement or financial transaction record",
    ],
    "education": [
        "a lesson plan or curriculum for students",
        "educational teaching material with learning objectives",
    ],
    "config": [
        "a json or yaml configuration file with settings like timeout, retries, and options",
        "environment variables, feature flags, and application parameters",
        "a manifest or build definition file",
    ],
    "data": [
        "a database export or structured dataset",
        "statistics, metrics, and benchmark results",
    ],
    "personal": [
        "personal identity, family, or medical records",
        "private notes about a person's life and relationships",
    ],
}

# Category → structural fragment_type stored alongside the topical label.
CATEGORY_FRAGMENT_TYPE = {
    "financial": "receipt",
    "correspondence": "note",
    "journal": "note",
    "narrative": "note",
}


def _seeds_hash() -> str:
    blob = json.dumps(CATEGORIES, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _cache_path(model: str) -> Path:
    base = Path(os.environ.get("NEST_CACHE_DIR", Path.home() / ".cache" / "nest-seed"))
    safe_model = model.replace("/", "_").replace(":", "_")
    return base / f"centroids_{safe_model}_{_seeds_hash()}.json"


def build_centroids(model: str = _embed.DEFAULT_EMBED_MODEL,
                    use_cache: bool = True) -> dict[str, list[float]] | None:
    """Return {category: centroid_vector}, or None if embeddings are unavailable.

    Cached to disk keyed by (model, seed hash) — recomputed only when the seeds
    or model change.
    """
    cache = _cache_path(model)
    if use_cache and cache.exists():
        try:
            return json.loads(cache.read_text())
        except (OSError, ValueError):
            pass

    if not _embed.available(model):
        return None

    centroids: dict[str, list[float]] = {}
    for cat, seeds in CATEGORIES.items():
        vecs = [_embed.embed_query(s, model=model) for s in seeds]
        c = _embed.centroid(vecs)
        if c is None:
            return None  # partial failure → don't cache a broken set
        centroids[cat] = c

    if use_cache:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(centroids))
        except OSError:
            pass
    return centroids


def rank(doc_vec: list[float], centroids: dict[str, list[float]]) -> list[tuple[float, str]]:
    """Cosine-rank a document vector against all centroids, best first."""
    sims = [(_embed.cosine(doc_vec, c), cat) for cat, c in centroids.items()]
    sims.sort(reverse=True)
    return sims
