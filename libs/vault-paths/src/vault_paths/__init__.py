"""vault_paths — the one vault-rooted path resolver for hosted apps.

Installer design D8: every persistence location derives from the vault root (D7),
never a hardcoded home path. Each app used to carry its own copy of this — a
byte-identical ``vault_root()`` plus a near-identical "env override, else under
the vault" accessor (box audit A5). ``vault_root()`` in particular is a security
boundary: it is the single decision of *where the vault box is*, so nine copies
of it is nine places for that boundary to drift. This is its one home.

  vault_root()                    the vault box; WILLOW_STORE_ROOT overrides
  app_dir(app_id)                 <vault>/<app_id>, or the APP_DATA override
  resolve(*parts, env_vars=...)   <vault>/<*parts>, or the first set env override

Env overrides are preserved so an operator can point at a legacy location during
migration into the vault. Stdlib-only, egress-free.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

__all__ = ["vault_root", "app_dir", "resolve"]


def vault_root() -> Path:
    """The vault box (installer design D7). Defaults to the willow store root;
    ``WILLOW_STORE_ROOT`` overrides."""
    return Path(os.environ.get(
        "WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def app_dir(app_id: str, env_var: str = "APP_DATA") -> Path:
    """An app's own persistence directory: ``<vault>/<app_id>``. If ``env_var``
    (default ``APP_DATA``) is set, it wins as a full path override."""
    env = os.environ.get(env_var)
    return Path(env).expanduser() if env else vault_root() / app_id


def resolve(*default_parts: str, env_vars: Iterable[str] = ()) -> Path:
    """Resolve a vault-rooted path: the first set env var in ``env_vars`` wins as
    a full path override, otherwise ``vault_root()`` joined with ``default_parts``
    (e.g. ``resolve("field-notes", "field-notes.db", env_vars=("FIELD_NOTES_DB",))``)."""
    for name in env_vars:
        val = os.environ.get(name)
        if val:
            return Path(val).expanduser()
    return vault_root().joinpath(*default_parts)
