"""The end of the night: a photo of the GM's handwritten page read into the
binder by the ocr add-on (tesseract), the night compiled and closed by
gm-end.md, and what the table holds true printed last. Needs tesseract, as
its CI row says. The page is made up: a fifth night's notes in a
handwriting-like font, tilted and grainy like a phone photo."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import willow_pin

ROOT = (
    willow_pin.root()
)  # willow, where its pieces live, held to apps/game/willow.pin.json
sys.path.insert(0, str(ROOT))
import kernel

NOW = ["--now", "2026-11-21T18:00:00Z"]
PAGE = HERE / "sample-scans" / "2026-11-21.jpg"


def py(*argv) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *map(str, argv)], capture_output=True, text=True, check=False
    )


@pytest.fixture
def night(tmp_path):
    table = tmp_path / "table"
    got = py(
        HERE / "open_table.py",
        "open",
        "--table",
        table,
        "--key",
        tmp_path / "gm.key",
        *NOW,
    )
    assert got.returncode == 42, got.stderr
    shutil.copy(PAGE, table / "scans" / PAGE.name)
    end = py(HERE / "open_table.py", "end", "--table", table)
    return table, end


def test_the_handwritten_page_is_read_into_the_binder(night):
    table, end = night
    read = (table / "pile" / "scanned" / "2026-11-21.jpg.txt").read_text()
    for line in ("Juno followed the springs.", "Old Vell found her lamp in the wasp nest!",
                 "Next time: what is Cogwen building"):  # fmt: skip
        assert line in read, read
    assert end.returncode == 42, end.stderr  # the session seal waits on the GM


def test_tonights_page_joins_the_threads_in_session_order(night):
    table, _ = night
    run = table / "end" / "001"
    springs = (run / "springs.txt").read_text()
    assert (
        "2026-11-21  scanned/2026-11-21.jpg.txt:3  Juno followed the springs."
        in springs
    )
    assert springs.index("2026-11-14") < springs.index("2026-11-21")
    assert (
        "scanned/2026-11-21.jpg.txt" in (run / "04-all.txt").read_text()
    )  # next time: Cogwen


def test_the_night_is_sealed_as_one_backed_up_and_pinned(night):
    table, end = night
    run = table / "end" / "001"
    log = (run / "00-stack.txt").read_text()
    assert "08 session-seal: exit 42" in log and "populated" in log.split("08 session-seal: exit 42")[1].splitlines()[0]  # fmt: skip
    rows = kernel.read(table / "record" / "record.jsonl")[0]
    assert [r["kind"] for r in rows].count("session") == 1
    assert not [
        r for r in rows if r["kind"] in ("seal", "decline")
    ]  # handed in, never sealed here
    assert list(run.glob("willow-backup-*.zip")) and json.loads(
        (run / "pin.json").read_text()
    )
    assert log.rstrip().endswith(
        "done: 2 of 10 steps flagged"
    )  # the rules and the session, both the GM's
    assert "## what the table holds true" in end.stdout


def test_a_second_night_runs_in_its_own_folder(night):
    table, _ = night
    again = py(HERE / "open_table.py", "end", "--table", table)
    assert again.returncode in (0, 42), again.stderr
    assert (table / "end" / "002" / "springs.txt").is_file()


def test_the_recap_after_the_night_gives_the_gm_tonights_handwritten_page(night):
    table, _ = night
    got = py(HERE / "session.py", "--table", table, "recap").stdout
    gm_only = got.split("## For the GM's eyes")[1]
    assert "Your notes from 2026-11-21:" in gm_only
    cited = {line.split()[0]: " ".join(line.split()[1:]) for line in gm_only.splitlines() if line.startswith("  ")}  # fmt: skip
    assert (
        cited["scanned/2026-11-21.jpg.txt:3"]
        == "Juno followed the springs. They go into the"
    )
    assert any(k.startswith("scanned/2026-11-21.jpg.txt:") and v == "Next time: what is Cogwen building"
               for k, v in cited.items())  # fmt: skip
