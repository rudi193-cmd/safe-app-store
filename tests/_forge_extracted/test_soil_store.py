"""Tests for stores/soil_store.py — the minimal FilesystemSoilStore that backs
the vendored human_loop (docs/design/the-forge-human-loop.md, D-HL-2).

Includes an end-to-end check that the vendored human_loop primitives actually
work over this store (attestation + queue), since the store exists only to
satisfy human_loop's injected-store contract. Pure — no Nestor/fsrs; runs
anywhere. Written test-first.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _REPO / "stores" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


soil_store = _load("soil_store", "soil_store.py")
human_loop = _load("human_loop", "human_loop.py")

BUILDER_A = "a" * 32
BUILDER_B = "b" * 32


# ── the store contract human_loop needs: put / get / all ─────────────────────

def test_put_then_get_round_trips(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    rec = {"id": "x1", "v": 1}
    s.put("things", rec, record_id="x1")
    assert s.get("things", "x1") == rec


def test_get_missing_is_none(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    assert s.get("things", "nope") is None


def test_all_returns_every_record_in_a_collection(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    s.put("things", {"id": "x1"}, record_id="x1")
    s.put("things", {"id": "x2"}, record_id="x2")
    s.put("other", {"id": "y1"}, record_id="y1")
    got = {r["id"] for r in s.all("things")}
    assert got == {"x1", "x2"}
    assert s.all("empty") == []


def test_put_updates_in_place_not_appends(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    s.put("things", {"id": "x1", "status": "open"}, record_id="x1")
    s.put("things", {"id": "x1", "status": "closed"}, record_id="x1")
    assert len(s.all("things")) == 1
    assert s.get("things", "x1")["status"] == "closed"


def test_two_builders_do_not_share_a_file(tmp_path):
    root = tmp_path / "soil"
    a = soil_store.FilesystemSoilStore(BUILDER_A, root=root)
    b = soil_store.FilesystemSoilStore(BUILDER_B, root=root)
    a.put("things", {"id": "x1"}, record_id="x1")
    assert b.all("things") == []             # isolated
    assert a.path != b.path
    assert a.path.exists()


def test_bad_builder_id_is_rejected(tmp_path):
    with pytest.raises(soil_store.SoilStoreError):
        soil_store.FilesystemSoilStore("../escape", root=tmp_path / "soil")


def test_put_without_an_id_is_rejected(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    with pytest.raises(soil_store.SoilStoreError):
        s.put("things", {"no": "id"})


def test_put_rejects_a_record_id_that_disagrees_with_record_id_field(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    with pytest.raises(soil_store.SoilStoreError):
        s.put("things", {"id": "Y"}, record_id="X")  # would make get(X)/get(Y) diverge


def test_a_symlinked_builder_file_is_refused(tmp_path):
    """A symlinked leaf `<a>.soil.json -> <b>.soil.json` would cross the
    one-file-per-builder boundary; both read and write must refuse it."""
    root = tmp_path / "soil"
    b = soil_store.FilesystemSoilStore(BUILDER_B, root=root)
    b.put("things", {"id": "secret"}, record_id="secret")  # B's file now exists
    # point A's file at B's file
    a = soil_store.FilesystemSoilStore(BUILDER_A, root=root)
    a.path.symlink_to(b.path)
    with pytest.raises(soil_store.SoilStoreError):
        a.get("things", "secret")          # read refused
    with pytest.raises(soil_store.SoilStoreError):
        a.put("things", {"id": "x"}, record_id="x")  # write refused (would clobber B)


# ── the vendored human_loop actually works over this store ───────────────────

def test_human_loop_attestation_round_trips_over_the_store(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    human_loop.create_attestation(
        s, subject_id="decision-1", attested_by=BUILDER_A, by_human=True,
        subject_type="other", statement="chose session cookie + CSRF",
    )
    assert human_loop.has_attestation(s, subject_id="decision-1", subject_type="other") is True
    assert human_loop.has_attestation(s, subject_id="decision-1", subject_type="other", require_human=True) is True
    assert human_loop.has_attestation(s, subject_id="nope", subject_type="other") is False


def test_human_loop_queue_round_trips_over_the_store(tmp_path):
    s = soil_store.FilesystemSoilStore(BUILDER_A, root=tmp_path / "soil")
    item = human_loop.enqueue(s, kind="review", title="thin rationale", source_agent="the-forge")
    assert len(human_loop.list_queue(s, status="open")) == 1
    human_loop.resolve(s, item["id"], resolved_by=BUILDER_A, status="acknowledged")
    assert human_loop.list_queue(s, status="open") == []  # states-not-deletions: no longer open
    assert human_loop.queue_stats(s).get("acknowledged") == 1
