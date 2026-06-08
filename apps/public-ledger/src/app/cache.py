"""
Response Cache
==============
File-backed TTL cache for API responses. Avoids repeat calls to
ProPublica and USAspending within the TTL window.

Cache dir: .cache/ (gitignored, created on first use)
"""

import hashlib
import json
import os
import time

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".cache")
_DEFAULT_TTL = 3600  # 1 hour


def _ensure_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _key_path(namespace, key):
    slug = hashlib.sha256(f"{namespace}:{key}".encode()).hexdigest()[:16]
    return os.path.join(_CACHE_DIR, f"{namespace}_{slug}.json")


def get(namespace, key):
    """Return cached value or None if missing/expired."""
    path = _key_path(namespace, key)
    try:
        with open(path, "r") as f:
            entry = json.load(f)
        if time.time() - entry["ts"] > entry.get("ttl", _DEFAULT_TTL):
            os.remove(path)
            return None
        return entry["data"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def put(namespace, key, data, ttl=None):
    """Store a value with TTL."""
    _ensure_dir()
    entry = {
        "ns": namespace,
        "key": key,
        "ts": time.time(),
        "ttl": ttl or _DEFAULT_TTL,
        "data": data,
    }
    path = _key_path(namespace, key)
    with open(path, "w") as f:
        json.dump(entry, f)


def clear(namespace=None):
    """Clear all cache or just one namespace."""
    if not os.path.isdir(_CACHE_DIR):
        return 0
    count = 0
    for fname in os.listdir(_CACHE_DIR):
        if namespace and not fname.startswith(f"{namespace}_"):
            continue
        os.remove(os.path.join(_CACHE_DIR, fname))
        count += 1
    return count


def stats():
    """Return cache stats."""
    if not os.path.isdir(_CACHE_DIR):
        return {"entries": 0, "size_bytes": 0}
    entries = [f for f in os.listdir(_CACHE_DIR) if f.endswith(".json")]
    total_size = sum(
        os.path.getsize(os.path.join(_CACHE_DIR, f)) for f in entries
    )
    return {"entries": len(entries), "size_bytes": total_size}
