"""killswitch.py — one command + a dead-man's-file that halts trading.

The trading loop checks is_killed() each tick. Two ways to trip it:
  1. engage() — sets an in-process flag AND writes the dead-man's-file.
  2. an out-of-band process (or a previous run) creating the dead-man's-file at
     killswitch_path(); its mere presence means "stop trading immediately".

disengage() is deliberately explicit and removes the file, so recovering from a
kill is a conscious act.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..paths import ensure_app_dir, killswitch_path


class KillSwitch:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or killswitch_path()
        self._engaged_in_process = False

    @property
    def path(self) -> Path:
        return self._path

    def engage(self, reason: str = "manual") -> None:
        """Halt trading: set the in-process flag and drop the dead-man's-file."""
        self._engaged_in_process = True
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        self._path.write_text(f"KILLED {stamp} reason={reason}\n", encoding="utf-8")

    def is_killed(self) -> bool:
        """True if engaged in-process OR the dead-man's-file exists on disk."""
        return self._engaged_in_process or self._path.exists()

    def disengage(self) -> None:
        """Explicitly clear the kill (remove the file, reset the flag)."""
        self._engaged_in_process = False
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass

    def status(self) -> dict:
        return {
            "killed": self.is_killed(),
            "dead_mans_file": str(self._path),
            "file_present": self._path.exists(),
            "engaged_in_process": self._engaged_in_process,
        }
