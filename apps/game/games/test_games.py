"""The games: a folder each, every one a pinned willow add-on, and each played
through play.py on a box's record, or on its own when it reads no box."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
BOX = HERE.parent / "box"
sys.path.insert(0, str(BOX))
import willow_pin

GAMES = sorted(
    p.name for p in HERE.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
)
NOW = ["--now", "2026-11-21T19:00:00Z"]

# one honest move of each game: on a box (True), or with no box (False)
FIRST = {
    "daily-word": (True, ["today"]),
    "game-master": (True, ["check"]),
    "oracle-text": (False, ["--seed", "between nights"]),
    "play-backgammon": (True, ["new"]),
    "play-bureau": (True, ["new"]),
    "play-catgrid": (True, ["play"]),
    "play-checkers": (True, ["new"]),
    "play-crazy-eights": (True, ["new"]),
    "play-dice": (True, ["roll", "2d6+1"]),
    "play-dice5e": (True, ["roll", "4d6kh3"]),
    "play-hearts": (True, ["new"]),
    "play-horoscope": (False, ["Ana"]),
    "play-liars-dice": (True, ["new"]),
    "play-life": (True, ["play"]),
    "play-odds": (False, ["2d6", "--bands", "10,7"]),
    "play-quiz": (True, ["ask"]),
    "play-tarot": (True, ["draw"]),
    "verse": (True, []),
}


def play(*argv) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HERE / "play.py"), *map(str, argv)],
                          capture_output=True, text=True, check=False)  # fmt: skip


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("games")
    got = subprocess.run([sys.executable, str(BOX / "open_table.py"), "open", "--table", str(tmp / "t"),
                          "--key", str(tmp / "gm.key"), *NOW], capture_output=True, text=True, check=False)  # fmt: skip
    assert got.returncode == 42, got.stderr
    return tmp / "t"


def test_every_game_has_a_folder_a_readme_and_a_pin():
    assert GAMES == sorted(FIRST)
    pinned = willow_pin.pin()["add_ons"]
    for g in GAMES:
        assert g in pinned, g
        readme = (HERE / g / "README.md").read_text()
        assert f"adapters/stdlib/{g}" in readme and "willow.pin.json" in readme


@pytest.mark.parametrize("game", sorted(FIRST))
def test_each_game_plays_through_the_pin(table, game):
    on_box, args = FIRST[game]
    got = play(game, *(["--table", table] if on_box else []), *args, *(NOW if on_box and game not in ("verse",) else []))  # fmt: skip
    assert got.returncode in (0, 42), (game, got.stderr)


def test_what_isnt_a_game_or_a_box_is_refused(tmp_path):
    got = play("chess")
    assert got.returncode == 2 and "isn't one of the games" in got.stderr
    got = play("play-checkers", "--table", tmp_path, "new")
    assert got.returncode == 2 and "isn't a box" in got.stderr
    assert play().returncode == 2
