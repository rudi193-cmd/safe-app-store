"""The end of the night: a photo of the GM's handwritten page read into the
binder by the ocr add-on, the night compiled and closed by gm-end.md, and
what the table holds true printed last. The page is made up: a fifth
night's notes in a handwriting-like font, tilted and grainy like a phone
photo.

ocr is a deps add-on: it reads only where tesseract is on PATH and its own
requirements (Pillow, pypdf) import, as in the deps job's environment, not
in every job that runs this. Where it can, the page is held to what it
says; where it can't, the night is held to what a GM without it gets: the
ocr step flagged, the other nine run, and no page that was never read in
the threads or the recap. Both are asserted; neither is skipped."""

from __future__ import annotations

import importlib.util
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
READS = bool(shutil.which("tesseract")) and all(
    importlib.util.find_spec(m) for m in ("PIL", "pypdf")
)  # ocr's programs line and its requirements.txt


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
    scanned = table / "pile" / "scanned" / "2026-11-21.jpg.txt"
    log = (table / "end" / "001" / "00-stack.txt").read_text()
    assert end.returncode == 42, end.stderr  # the session seal waits on the GM
    if not READS:
        assert "01 ocr: exit 2, 1 line, flagged" in log and not scanned.exists()
        return
    assert "01 ocr: exit 0" in log
    read = scanned.read_text()
    for line in ("Juno followed the springs.", "Old Vell found her lamp in the wasp nest!",
                 "Next time: what is Cogwen building"):  # fmt: skip
        assert line in read, read


def test_tonights_page_joins_the_threads_in_session_order(night):
    table, _ = night
    run = table / "end" / "001"
    springs = (run / "springs.txt").read_text()
    if not READS:  # tonight's page was never read: only the typed nights
        assert "2026-11-14" in springs and "2026-11-21" not in springs
        return
    assert (
        "2026-11-21  scanned/2026-11-21.jpg.txt:3  Juno followed the springs."
        in springs
    )
    assert springs.index("2026-11-14") < springs.index("2026-11-21")
    assert (
        "scanned/2026-11-21.jpg.txt" in (run / "04-all-passages.txt").read_text()
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
    flagged = 2 if READS else 3  # the rules and the session, both the GM's; and ocr
    assert log.rstrip().endswith(f"done: {flagged} of 10 steps flagged")
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
    if not READS:  # the latest night the binder holds is the last typed one
        assert "Your notes from 2026-11-14:" in gm_only and "scanned/" not in gm_only
        return
    assert "Your notes from 2026-11-21:" in gm_only
    cited = {line.split()[0]: " ".join(line.split()[1:]) for line in gm_only.splitlines() if line.startswith("  ")}  # fmt: skip
    assert (
        cited["scanned/2026-11-21.jpg.txt:3"]
        == "Juno followed the springs. They go into the"
    )
    assert any(k.startswith("scanned/2026-11-21.jpg.txt:") and v == "Next time: what is Cogwen building"
               for k, v in cited.items())  # fmt: skip
