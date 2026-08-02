"""Nest Playgate — a curated kid catalog with a parent gate that closes.

The core (`catalog`, `disposition`, `install`, `interruption`) is stdlib-only
and network-free. `server` is the one module that binds a socket, and it binds
loopback.
"""
from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["catalog", "disposition", "install", "interruption", "server"]
