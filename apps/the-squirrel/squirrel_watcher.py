"""
Watches Squirrel.md. On change, hands the whole read→dispatch→advance cycle
to the shared Journal (see journal.py) — which holds one lock across it so
concurrent writes can't be dropped (B-006).
"""
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileModifiedEvent, FileSystemEventHandler


class _Handler(FileSystemEventHandler):
    def __init__(self, journal, callback, state_fn):
        self._journal = journal
        self._callback = callback
        self._state_fn = state_fn

    def on_modified(self, event):
        if not isinstance(event, FileModifiedEvent):
            return
        if Path(event.src_path).resolve() != self._journal.path.resolve():
            return
        try:
            self._journal.process(self._callback, self._state_fn)
        except Exception as e:
            print(f"[watcher] error: {e}")


def start_watcher(journal, callback, state_fn):
    handler = _Handler(journal, callback, state_fn)
    obs = Observer()
    obs.schedule(handler, str(journal.path.parent), recursive=False)
    obs.start()
    return obs
