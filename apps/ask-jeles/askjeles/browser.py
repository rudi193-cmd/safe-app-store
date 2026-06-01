"""Open URLs in the system browser from the Jeles TUI."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser


def open_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://", "file://")):
        return False
    try:
        if webbrowser.open(url, new=2):
            return True
    except Exception:
        pass
    for cmd in ("xdg-open", "gio", "wslview"):
        if shutil.which(cmd):
            try:
                subprocess.run([cmd, url], check=False, timeout=5)
                return True
            except Exception:
                continue
    return False
