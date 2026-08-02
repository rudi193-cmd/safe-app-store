"""paths.py — the single vault-rooted path resolver for Playgate.

Installer design D8: every persistence location derives from the vault root
(D7), never a hardcoded home path and never the app's own install directory.
Env overrides are preserved so an operator can point at a legacy location while
migrating into the vault.

This module is the only place in the app that decides *where* anything lives.
Every other module takes a path as an argument, which is what lets the whole
core stay stdlib-only and lets the tests run entirely under `tmp_path`.

The disposition log in particular must not default into the app directory. It
is a record of what a specific family's children asked for and what their
parents decided; writing it beside the source would put it inside a checkout,
carry it into any copy of the app, and lose it on a reinstall.
"""
from __future__ import annotations

from pathlib import Path

try:
    import vault_paths as _vp
except ImportError:  # not yet installed via `pip install -e libs/vault-paths`
    import sys

    _canonical_src = Path(__file__).resolve().parents[3] / "libs" / "vault-paths" / "src"
    if not _canonical_src.is_dir():
        raise ImportError(
            "vault_paths is not installed and libs/vault-paths isn't reachable "
            "from this checkout. Run `pip install -e libs/vault-paths` from the "
            "store root — where the vault lives is that library's one decision "
            "to own, not a second copy of it here."
        ) from None
    sys.path.insert(0, str(_canonical_src))
    import vault_paths as _vp  # type: ignore[no-redef]

APP_ID = "playgate"

# The seed catalog is deliberately *not* resolved here. It is shipped content
# rather than user data — it travels with the app, is read-only at runtime, and
# is replaced wholesale by `--catalog`. Its one definition lives in catalog.py,
# next to the code that reads it; repeating it here would make two modules
# responsible for the same decision.


def app_dir() -> Path:
    """This app's directory under the vault. APP_DATA overrides."""
    return _vp.app_dir(APP_ID)


def log_path() -> Path:
    """The disposition log. PLAYGATE_LOG overrides."""
    return _vp.resolve(APP_ID, "requests.jsonl", env_vars=("PLAYGATE_LOG",))


def apk_dir() -> Path:
    """Where an operator puts the APKs this app is allowed to install.

    Under the vault rather than beside the source: these are files a person
    deliberately placed, and they should survive a reinstall of the app and
    stay out of any checkout of it.

    PLAYGATE_APK_DIR overrides.
    """
    return _vp.resolve(APP_ID, "apks", env_vars=("PLAYGATE_APK_DIR",))
