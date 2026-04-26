import threading
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

class Mode(Enum):
    JOURNAL = "journal"
    LISTENING = "listening"
    CHAT = "chat"

CONFIG_PATH = Path.home() / ".squirrel" / "config.json"

@dataclass
class AppState:
    mode: Mode = Mode.JOURNAL
    skin: str = "mcm"
    squirrel_md: Path = field(default_factory=lambda: Path("Squirrel.md"))
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                self.skin = data.get("skin", "mcm")
            except Exception:
                pass

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"skin": self.skin}, indent=2))

    def append(self, text: str):
        with self._lock:
            with open(self.squirrel_md, "a", encoding="utf-8") as f:
                f.write("\n" + text + "\n")
