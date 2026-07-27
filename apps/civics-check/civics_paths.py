"""
civics_paths.py — single vault-rooted path resolver for Civics Check.

Installer design D8: every persistence location derives from the vault root
(D7). No hardcoded home paths. Env overrides are preserved so an operator can
point at a legacy location during migration into the vault.
"""
from __future__ import annotations

from pathlib import Path

# The shared resolver (box audit A5). vault_root is re-exported so callers that
# do `from civics_paths import vault_root` keep working.
from vault_paths import app_dir, vault_root  # noqa: F401

APP_ID = "civics-check"


def app_data() -> Path:
    """This app's own persistence, under the vault. APP_DATA overrides."""
    return app_dir(APP_ID)
