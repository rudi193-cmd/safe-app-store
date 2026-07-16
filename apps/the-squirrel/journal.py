"""
journal.py — the single writer/reader of Squirrel.md.
b17: NNA92
ΔΣ=42

B-006 fix. The old watcher tracked its own `_last_size` and, after
processing, reset it to the current file size to skip the bot responses it
had written. Any concurrent /write that appended DURING processing sat
between the bytes just read and that reset — and was leaped over, silently
dropped. Two locks made it worse: /write used one, the responder's append
used another, so they never coordinated.

This object is the one lock. Every write to Squirrel.md and every read by
the watcher goes through it:

  append_user  — a user command (POST /write). Does NOT advance the
                 processed-offset; the watcher must still dispatch it.
  append_bot   — the responder's output. Written from inside process(),
                 under the held lock; the final offset bump covers it.
  process      — the watcher's whole cycle: read unprocessed bytes,
                 dispatch each command (which calls append_bot re-entrantly),
                 THEN advance the offset to EOF — all under one RLock held
                 the entire time.

Because the lock is held across read → dispatch → append → advance, no
append_user can interleave: it blocks until the batch finishes. So when the
offset advances to EOF, everything behind it is either a user line just
processed or bot output just written — never an unprocessed user line. The
loop-to-EOF is safe precisely because the writer can't sneak in mid-cycle.
"""

import threading
from pathlib import Path


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        # Anything already in the file at boot (e.g. the welcome block, whose
        # example lines contain '@squirrel:') is considered already processed.
        self._processed = self.path.stat().st_size if self.path.exists() else 0

    def append_user(self, text: str) -> None:
        """A user command. Blocks while the watcher is mid-process()."""
        if not text:
            return
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("\n" + text + "\n")

    def append_bot(self, text: str) -> None:
        """Responder output. Only ever called from within process() (via the
        responder callback), so the lock is already held by this thread."""
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("\n" + text + "\n")

    def process(self, handle_line, mode_fn) -> None:
        """One watcher cycle. Held under the lock start to finish so no
        concurrent append_user can slip a command past the offset advance."""
        with self._lock:
            size = self.path.stat().st_size
            if size <= self._processed:
                # File shrank/rewritten (e.g. truncated by hand) — resync.
                self._processed = size
                return
            with open(self.path, encoding="utf-8") as f:
                f.seek(self._processed)
                new_text = f.read()
            mode = mode_fn()
            for line in new_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if "@squirrel:" in line.lower():
                    handle_line(line)          # appends bot output re-entrantly
                elif mode != "journal":
                    handle_line(line)
            # Everything from old offset to now is processed-or-bot; no user
            # line can be behind EOF because append_user was locked out.
            self._processed = self.path.stat().st_size
