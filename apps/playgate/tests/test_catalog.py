"""The catalog gate: an entry with nothing recorded does not load.

This is the file that makes the interruption field a gate rather than a
convention. `assumed` passes, because admitting nobody has looked is honest and
is usually the truth. A missing field does not pass, because that is the state
in which the catalog silently implies more than it knows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from playgate import catalog
from playgate import install
from playgate.interruption import InterruptionError

SEED_APK_DIR = Path(__file__).resolve().parents[1] / "data" / "apks"
SOURCES_PATH = SEED_APK_DIR / "SOURCES.json"

ENTRY = {
    "id": "example",
    "title": "Example",
    "blurb": "A game.",
    "age_band": "7+",
    "abi": "universal",
    "package": "com.example.game",
    "interruption": {"provenance": "assumed"},
}


def write(tmp_path, *entries):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"apps": list(entries)}))
    return path


def test_an_assumed_entry_loads(tmp_path):
    apps = catalog.load(write(tmp_path, ENTRY))
    assert apps[0].interruption.provenance == "assumed"


def test_an_entry_with_no_interruption_field_is_refused(tmp_path):
    """The gate. Blank is the one value that is not allowed."""
    bare = {k: v for k, v in ENTRY.items() if k != "interruption"}
    with pytest.raises(InterruptionError, match="no interruption record"):
        catalog.load(write(tmp_path, bare))


def test_the_error_names_the_offending_entry(tmp_path):
    bare = {k: v for k, v in ENTRY.items() if k != "interruption"}
    with pytest.raises(InterruptionError, match="example"):
        catalog.load(write(tmp_path, bare))


def test_a_missing_required_field_is_refused(tmp_path):
    for field in ("id", "title", "package", "age_band"):
        broken = {k: v for k, v in ENTRY.items() if k != field}
        with pytest.raises(InterruptionError, match="missing"):
            catalog.load(write(tmp_path, broken))


def test_duplicate_ids_are_refused(tmp_path):
    with pytest.raises(InterruptionError, match="duplicate"):
        catalog.load(write(tmp_path, ENTRY, dict(ENTRY)))


# -- what the UIs are handed ----------------------------------------------

MEASURED_ENTRY = dict(
    ENTRY,
    version="3.1",
    interruption={
        "provenance": "measured", "count_per_10min": 6, "dismissal": "deceptive_close",
        "observed_version": "3.1", "observed_at": "2026-08-02", "observed_by": "a parent",
    },
    tracker_provenance="measured",
)


def test_the_view_carries_the_four_facts_and_no_score(tmp_path):
    """Count, dismissal, date, and provenance — unweighted and uncombined.

    A composite would be built from weights somebody picked, displayed, sorted
    on, and within two releases optimised against, at which point it would
    measure compliance with the scoring function instead of interruption.
    """
    app = catalog.load(write(tmp_path, MEASURED_ENTRY))[0]
    view = app.view()
    assert view["interruption"]["count_per_10min"] == 6
    assert view["interruption"]["dismissal"] == "deceptive_close"
    assert view["interruption"]["observed_at"] == "2026-08-02"
    assert view["interruption"]["provenance"] == "measured"
    assert "score" not in view and "rating" not in view


def test_the_view_demotes_a_stale_measurement(tmp_path):
    stale = dict(MEASURED_ENTRY, version="3.2")
    app = catalog.load(write(tmp_path, stale))[0]
    assert app.view()["interruption"]["provenance"] == "fitted"


def test_confidence_is_the_weakest_input_not_an_average(tmp_path):
    """A measured interruption count beside an assumed tracker inventory is an
    assumed entry. Not two-thirds of the way to good."""
    mixed = dict(MEASURED_ENTRY, tracker_provenance="assumed")
    app = catalog.load(write(tmp_path, mixed))[0]
    assert app.view()["confidence"] == "assumed"


def test_confidence_rises_only_when_every_input_does(tmp_path):
    app = catalog.load(write(tmp_path, MEASURED_ENTRY))[0]
    assert app.view()["confidence"] == "measured"


# -- search ----------------------------------------------------------------

def test_search_matches_title_and_blurb(tmp_path):
    apps = catalog.load(write(tmp_path, ENTRY))
    assert catalog.search(apps, "exam") == apps
    assert catalog.search(apps, "a game") == apps
    assert catalog.search(apps, "zzz") == []


def test_an_empty_query_returns_everything_in_written_order(tmp_path):
    second = dict(ENTRY, id="other", title="Other")
    apps = catalog.load(write(tmp_path, ENTRY, second))
    assert [a.id for a in catalog.search(apps, "  ")] == ["example", "other"]


# -- the shipped catalog ---------------------------------------------------

def test_the_shipped_catalog_loads():
    assert catalog.load()


def test_every_shipped_entry_is_honestly_assumed():
    """Nobody has measured any of these. An entry claiming otherwise would be
    the exact failure this app exists to refuse, committed in its own data file.
    """
    for app in catalog.load():
        assert app.interruption.provenance == "assumed", app.id
        assert app.view()["confidence"] == "assumed", app.id


def test_every_shipped_entry_pairs_apk_path_with_a_digest():
    """apk_path and sha256 must agree — never one set and the other blank."""
    for app in catalog.load():
        assert (app.apk_path is None) == (app.sha256 is None), app.id


def test_the_shipped_catalog_matches_the_sources_manifest():
    """catalog.json and data/apks/SOURCES.json must not drift for F-Droid entries."""
    sources = json.loads(SOURCES_PATH.read_text())
    by_id = {entry["catalog_id"]: entry for entry in sources["apks"]}
    for app in catalog.load():
        if not app.apk_path:
            continue
        assert app.id in by_id, f"{app.id} missing from SOURCES.json"
        src = by_id[app.id]
        assert app.apk_path == src["filename"], app.id
        assert app.sha256 == src["sha256"], app.id
        assert app.version == src["version_name"], app.id
        assert app.package == src["package"], app.id


def test_shipped_apk_bytes_match_their_recorded_digests():
    """When seed APKs are present locally, their bytes must match the catalog.

    CI does not fetch ~50 MiB of F-Droid binaries; operators run
    tools/fetch_apks.py. This test runs when the files are already there.
    """
    apps = catalog.load()
    if any(not (SEED_APK_DIR / app.apk_path).is_file() for app in apps if app.apk_path):
        pytest.skip("seed APKs absent — run tools/fetch_apks.py")
    for app in apps:
        if not app.apk_path:
            continue
        path = SEED_APK_DIR / app.apk_path
        result = install.verify(path, app.sha256 or "")
        assert result.ok, f"{app.id}: {result.detail}"
