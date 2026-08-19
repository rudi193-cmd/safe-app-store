"""User identity — read UUID and write session composites.

Pattern: Protocol + set_client() injection + silent no-op.
With no client injected, get_user_uuid reads from the vault's
user_identity.json and write_session_composite returns False.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class IdentityClient(Protocol):
    """Anything that can read user identity and write session atoms."""

    def get_user_uuid(self) -> Optional[str]:
        ...

    def write_session_composite(self, stats: dict, uuid: str,
                                app_id: str, collection: str) -> bool:
        ...


_client: Optional[IdentityClient] = None
_app_id: str = "unknown"
_identity_path: Optional[Path] = None


def set_identity_client(client: Optional[IdentityClient], *,
                        app_id: str = "unknown",
                        identity_path: Optional[Path] = None) -> None:
    global _client, _app_id, _identity_path
    _client = client
    _app_id = app_id
    _identity_path = identity_path


def get_identity_client() -> Optional[IdentityClient]:
    return _client


def get_user_uuid() -> Optional[str]:
    """Read user UUID. Injected client takes priority, else reads identity file."""
    if _client is not None:
        try:
            return _client.get_user_uuid()
        except Exception:
            return None
    if _identity_path is None:
        return None
    try:
        data = json.loads(_identity_path.read_text())
        return data.get("uuid") or None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_session_composite(stats: dict, uuid: str) -> bool:
    """Write a session composite atom. Returns False if no client or no UUID."""
    if not uuid:
        return False
    safe_uuid = re.sub(r"[^a-zA-Z0-9_\-]", "-", uuid)
    collection = f"user-{safe_uuid}/{_app_id}/atoms"

    if _client is not None:
        try:
            return _client.write_session_composite(stats, uuid, _app_id, collection)
        except Exception:
            return False
    return False
