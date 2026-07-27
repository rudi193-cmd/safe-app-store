"""Tests for selflearn.py — run without Ollama by stubbing the embed backend.

Embeddings are made deterministic (hash-based) so centroid arithmetic is exact;
the tests assert the self-learning *mechanics* (store, fold, routing, cluster),
not embedding quality. Run from inside apps/nest-seed/ so `import selflearn`
resolves.
"""
import hashlib
import importlib

from nest_pipeline import embed as _embed
from nest_pipeline import taxonomy as _tax
from nest_pipeline import selflearn as _learn

_DIM = 8


def _fake_vec(text: str) -> list:
    h = hashlib.sha256(text.encode()).digest()
    return [h[i] / 255.0 for i in range(_DIM)]


def _fake_embed_document(text, model=None):
    return _fake_vec(text)


import pytest


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("NEST_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(_embed, "available", lambda model=None: True)
    monkeypatch.setattr(_embed, "embed_document", _fake_embed_document)
    # margins/caps independent of env
    monkeypatch.setattr(_learn, "LEARN_MIN_MARGIN", 0.10)
    monkeypatch.setattr(_learn, "LEARN_MAX_PER_CAT", 3)
    yield


def test_merge_dedupes_and_filters_low_margin():
    model = "fake"
    obs = [
        {"category": "financial", "vec": [0.1] * _DIM, "margin": 0.20, "hash": "a"},
        {"category": "financial", "vec": [0.1] * _DIM, "margin": 0.20, "hash": "a"},  # dup
        {"category": "financial", "vec": [0.2] * _DIM, "margin": 0.05, "hash": "b"},  # low margin
    ]
    summary = _learn.merge_learned(model, obs)
    assert summary["added"] == 1
    assert _learn.load_learned(model)["financial"][0]["hash"] == "a"


def test_merge_caps_per_category():
    model = "fake"
    obs = [{"category": "legal", "vec": [i / 10] * _DIM, "margin": 0.10 + i / 100,
            "hash": f"h{i}"} for i in range(6)]
    _learn.merge_learned(model, obs)  # cap=3 (from fixture)
    bucket = _learn.load_learned(model)["legal"]
    assert len(bucket) == 3
    # highest-margin kept
    assert min(e["margin"] for e in bucket) >= 0.13


def test_adaptive_equals_base_when_nothing_learned():
    model = "fake"
    base = _tax.build_centroids(model=model)
    adaptive = _learn.build_adaptive_centroids(model=model)
    assert adaptive == base


def test_adaptive_shifts_toward_learned_by_exact_mean():
    model = "fake"
    base = _tax.build_centroids(model=model)
    base_fin = base["financial"]
    n_ex = len(_tax.EXEMPLARS["financial"])  # 2
    L = [0.5] * _DIM
    _learn.merge_learned(model, [{"category": "financial", "vec": L,
                                  "margin": 0.20, "hash": "x"}])
    adaptive = _learn.build_adaptive_centroids(model=model, use_cache=False)
    expected = [(base_fin[i] * n_ex + L[i]) / (n_ex + 1) for i in range(_DIM)]
    for got, exp in zip(adaptive["financial"], expected):
        assert abs(got - exp) < 1e-9
    # untouched category unchanged
    assert adaptive["legal"] == base["legal"]


def test_recorder_routes_by_confidence():
    rec = _learn.Recorder()
    sink = rec.sink_for(key="h1", snippet="hello world")
    sink("financial", [0.1] * _DIM, 0.15, "confirmed")
    sink("legal", [0.2] * _DIM, 0.04, "uncertain")
    sink("code", [0.3] * _DIM, 0.20, "likely")  # not confirmed, not tail → ignored
    assert len(rec.confident) == 1 and rec.confident[0]["category"] == "financial"
    assert len(rec.tail) == 1 and rec.tail[0]["snippet"] == "hello world"


def test_discover_returns_clusters():
    # two tight groups in opposite directions
    a = [1.0, 0.0] + [0.0] * 6
    b = [0.0, 1.0] + [0.0] * 6
    items = ([{"vec": a, "snippet": "group A"}] * 5 +
             [{"vec": b, "snippet": "group B"}] * 5)
    res = _learn.discover(items, k=2)
    assert res["status"] == "ok"
    assert len(res["clusters"]) == 2
    assert sum(c["size"] for c in res["clusters"]) == 10


def test_discover_noop_when_too_few():
    res = _learn.discover([{"vec": [1.0] * _DIM, "snippet": "x"}], k=4)
    assert res["status"] == "noop"


# --- cluster promotion (phase 2b) -------------------------------------------

# A controlled 4-d base taxonomy so novelty/distinctness is deterministic.
_BASE = {"a": [1.0, 0, 0, 0], "b": [0, 1.0, 0, 0]}


@pytest.fixture
def _base_centroids(monkeypatch):
    monkeypatch.setattr(_tax, "build_centroids", lambda model=None, use_cache=True: dict(_BASE))


def test_promote_accepts_novel_cohesive_cluster(_base_centroids):
    model = "fake"
    items = [{"vec": [0, 0, 1.0, 0], "snippet": "tax invoice receipt total"}] * 6
    res = _learn.promote_clusters(model, items, k=1, min_size=4)
    assert res["status"] == "ok"
    assert len(res["promoted"]) == 1
    assert res["promoted"][0]["name"].startswith("auto:")
    # persisted and visible to the adaptive centroids
    assert res["promoted"][0]["name"] in _learn.load_discovered(model)


def test_promote_rejects_cluster_matching_existing(_base_centroids):
    model = "fake"
    items = [{"vec": [1.0, 0, 0, 0], "snippet": "looks like category a"}] * 6
    res = _learn.promote_clusters(model, items, k=1, min_size=4)
    assert res["promoted"] == []
    assert any("matches_existing" in r["reason"] for r in res["rejected"])


def test_promote_rejects_too_small(_base_centroids):
    model = "fake"
    items = [{"vec": [0, 0, 1.0, 0], "snippet": "novel but tiny"}] * 3
    res = _learn.promote_clusters(model, items, k=1, min_size=4)
    assert res["promoted"] == []
    assert any(r["reason"] == "too_small" for r in res["rejected"])


def test_discovered_categories_enter_adaptive_centroids(monkeypatch):
    model = "fake"
    monkeypatch.setattr(_tax, "build_centroids", lambda model=None, use_cache=True: dict(_BASE))
    _learn.save_discovered(model, {"auto:foo": {"vec": [0, 0, 1.0, 0], "label": "foo",
                                                "size": 5, "cohesion": 0.9}})
    adaptive = _learn.build_adaptive_centroids(model=model, use_cache=False)
    assert "auto:foo" in adaptive
    assert adaptive["a"] == _BASE["a"]


def test_slug_is_unique():
    used = set()
    a = _learn._slug("tax invoice receipt total amount", used); used.add(a)
    b = _learn._slug("tax invoice receipt total amount", used)
    assert a != b and a.startswith("auto:tax-invoice")
