"""
B-006 regression: the Journal never drops a user command and never
re-executes its own bot output as one.

Deterministic — drives Journal directly (no watchdog, no sleeps). The
verifier's isolation harness proved the drop needed a bot-append landing
between the watcher's read and its offset reset; these tests reproduce
that interleaving on purpose.
"""
import threading

import pytest

from journal import Journal


def test_bot_append_during_dispatch_does_not_drop_next_command(tmp_path):
    """The exact B-006 shape: a command whose handler appends bot output,
    with a second command written to the file mid-dispatch. The second must
    still be processed on the next cycle, not skipped by the offset reset."""
    path = tmp_path / "Squirrel.md"
    path.write_text("# seed\n", encoding="utf-8")
    j = Journal(path)
    processed = []

    def handle(line):
        processed.append(line)
        # A concurrent user write arriving *during* this dispatch (another
        # thread would block on the lock, but the bytes are what matters):
        # simulate the bot writing its response.
        j.append_bot(f"response to {line}")

    j.append_user("@squirrel: add person One")
    j.process(handle, lambda: "journal")
    j.append_user("@squirrel: add person Two")
    j.process(handle, lambda: "journal")

    assert processed == ["@squirrel: add person One", "@squirrel: add person Two"]


def test_bot_output_is_never_reprocessed_as_a_command(tmp_path):
    """Bot output containing a literal '@squirrel:' usage string (the trap
    the verifier flagged) must not be dispatched on a later cycle."""
    path = tmp_path / "Squirrel.md"
    path.write_text("# seed\n", encoding="utf-8")
    j = Journal(path)
    seen = []

    def handle(line):
        seen.append(line)
        j.append_bot("Usage: `@squirrel: stash \"x\"` — try that")  # a live-looking cmd

    j.append_user("@squirrel: show people")
    j.process(handle, lambda: "journal")
    j.process(handle, lambda: "journal")   # a second fire must find nothing new

    assert seen == ["@squirrel: show people"]  # the usage string was NOT dispatched


def test_burst_of_writes_all_processed(tmp_path):
    """Many appends before a single process() cycle — all delivered."""
    path = tmp_path / "Squirrel.md"
    path.write_text("# seed\n", encoding="utf-8")
    j = Journal(path)
    for i in range(50):
        j.append_user(f"@squirrel: add person P{i}")
    got = []
    j.process(lambda ln: got.append(ln), lambda: "journal")
    assert len(got) == 50


def test_concurrent_appends_and_processing_lose_nothing(tmp_path):
    """Threads hammer append_user while the main thread drains via process().
    The shared lock must serialize so every command is eventually seen."""
    path = tmp_path / "Squirrel.md"
    path.write_text("# seed\n", encoding="utf-8")
    j = Journal(path)
    N = 40
    done = threading.Event()

    def writer(i):
        j.append_user(f"@squirrel: add person T{i}")

    seen = []
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # drain everything written
    j.process(lambda ln: seen.append(ln), lambda: "journal")
    assert len(seen) == N
