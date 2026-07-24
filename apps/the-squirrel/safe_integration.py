"""SAFE Framework Integration for The Squirrel.

Thin shim over the shared portless surface (safe-app-common, #18). The
byte-identical-except-app_id ``safe_integration.py`` stub that was copied across
the-squirrel / llmphysics-bot / UTETY-Reddit-Bots now lives once in
``safe_app_common.safe_client``; this file keeps the-squirrel's public API
(`get_manifest()` / `status()`) and delegates.
"""
from pathlib import Path

from safe_app_common.safe_client import get_manifest as _get_manifest
from safe_app_common.safe_client import status as _status

_APP_ID = "the-squirrel"


def get_manifest():
    return _get_manifest(Path(__file__).parent)


def status():
    """Check if Willow store is reachable (portless)."""
    return _status(_APP_ID)
