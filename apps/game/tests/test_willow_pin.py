"""The pin: the box runs on willow where its pieces live, and only on a willow
whose files are the pinned bytes."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "box"  # the box these tests test
sys.path.insert(0, str(HERE))
import willow_pin

REAL = willow_pin.root()  # found once, before any test hides it


def test_the_willow_beside_the_store_is_the_pinned_one():
    root = willow_pin.root()
    assert (root / "kernel.py").is_file() and not willow_pin.drift(
        root, willow_pin.pin()
    )


def test_every_add_on_the_box_plays_with_is_pinned():
    pinned = willow_pin.pin()
    folders = {p.split("/")[2] for p in pinned["files"] if p.startswith("adapters/")}
    assert set(pinned["add_ons"]) <= folders
    assert "kernel.py" in pinned["files"]


@pytest.fixture
def alone(tmp_path, monkeypatch):
    """A store with no willow beside it: only WILLOW_ROOT is looked at."""
    monkeypatch.setattr(willow_pin, "STORE", tmp_path / "store")
    return tmp_path


def copy_of_willow(to: Path) -> Path:
    real = REAL
    for rel in willow_pin.pin()["files"]:
        (to / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(real / rel, to / rel)
    return to


def test_a_willow_with_a_changed_file_is_refused_by_name(alone, monkeypatch):
    w = copy_of_willow(alone / "w")
    monkeypatch.setenv("WILLOW_ROOT", str(w))
    assert willow_pin.root() == w
    with open(w / "adapters" / "stdlib" / "play-dice" / "play_dice.py", "a") as f:
        f.write("# changed\n")
    with pytest.raises(
        willow_pin.Unpinned, match="adapters/stdlib/play-dice/play_dice.py differs"
    ):
        willow_pin.root()


def test_a_willow_missing_a_file_or_none_at_all_is_refused(alone, monkeypatch):
    w = copy_of_willow(alone / "w")
    (w / "adapters" / "stdlib" / "play-odds" / "play_odds.py").unlink()
    monkeypatch.setenv("WILLOW_ROOT", str(w))
    with pytest.raises(willow_pin.Unpinned, match="play_odds.py is missing"):
        willow_pin.root()
    monkeypatch.delenv("WILLOW_ROOT")
    with pytest.raises(willow_pin.Unpinned, match="no willow there"):
        willow_pin.root()
