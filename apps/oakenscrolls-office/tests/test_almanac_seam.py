import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_vertical(root: Path, name: str, entries: list[dict], sha: str = "a" * 40,
                  packed: bool = False) -> None:
    """A fake local almanac clone: catalog.json + just enough .git for HEAD."""
    repo = root / name
    (repo / ".git").mkdir(parents=True)
    (repo / "catalog.json").write_text(json.dumps({"name": name, "entries": entries}))
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    if packed:
        (repo / ".git" / "packed-refs").write_text(
            f"# pack-refs with: peeled fully-peeled sorted\n{sha} refs/heads/main\n"
        )
    else:
        (repo / ".git" / "refs" / "heads").mkdir(parents=True)
        (repo / ".git" / "refs" / "heads" / "main").write_text(sha + "\n")


ENTRY = {
    "id": "berkeley-earth-temperature",
    "title": "Berkeley Earth Surface Temperature",
    "description": "Independent global land and ocean surface temperature analysis",
    "publisher": "Berkeley Earth",
    "topics": ["temperature", "global"],
    "source": {"canonical_url": "https://berkeleyearth.org/data/"},
    "status": "live",
    "license": "CC-BY-NC-SA-4.0",
}
FROZEN = {
    "id": "billion-dollar-disasters",
    "title": "Billion-Dollar Disasters",
    "description": "US weather and climate disasters exceeding one billion dollars",
    "publisher": "NOAA",
    "topics": ["disasters"],
    "source": {"canonical_url": "https://example.gov/disasters"},
    "status": "frozen",
    "license": "public-domain",
}


@pytest.fixture()
def seam(tmp_path, monkeypatch):
    monkeypatch.setenv("ALMANAC_DATA_ROOT", str(tmp_path / "almanac-data"))
    import almanac_seam
    return almanac_seam


def test_no_clones_is_empty_not_an_error(seam):
    assert seam.verticals() == []
    assert seam.search("temperature") == []


def test_search_matches_and_ranks_live_first(seam, tmp_path):
    root = tmp_path / "almanac-data"
    make_vertical(root, "climate-almanac", [ENTRY, FROZEN], sha="b" * 40)
    hits = seam.search("temperature global")
    assert [h["entry_id"] for h in hits] == ["berkeley-earth-temperature"]
    assert hits[0]["catalog_commit"] == "b" * 40
    assert hits[0]["canonical_url"] == "https://berkeleyearth.org/data/"

    both = seam.search("climate" if False else "e")  # matches everything
    # live entries rank above frozen ones
    statuses = [h["status"] for h in both]
    assert statuses.index("live") < statuses.index("frozen")


def test_head_commit_via_packed_refs(seam, tmp_path):
    root = tmp_path / "almanac-data"
    make_vertical(root, "economy-almanac", [FROZEN], sha="c" * 40, packed=True)
    assert seam.verticals()[0]["commit"] == "c" * 40


def test_citation_carries_facts_and_pin(seam, tmp_path):
    root = tmp_path / "almanac-data"
    make_vertical(root, "climate-almanac", [ENTRY])
    hit = seam.search("berkeley")[0]
    cite = seam.citation(hit, note="checked the 2026 anomaly table")
    assert cite["kind"] == "almanac-data"
    assert cite["vertical"] == "climate-almanac"
    assert cite["catalog_commit"] == "a" * 40
    assert cite["publisher"] == "Berkeley Earth"
    assert cite["cited_at"] > 0
