"""storage-backend: injectable SOIL storage seam.

Defines a StorageBackend Protocol (put/list/delete) with dependency injection.
Apps call set_backend() at startup; the module-level functions degrade to
silent no-ops when no backend is configured.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

log = logging.getLogger("storage_backend")

__all__ = [
    "StorageBackend",
    "set_backend",
    "get_backend",
    "available",
    "put",
    "list_records",
    "delete",
]


@runtime_checkable
class StorageBackend(Protocol):
    """Anything that can store, list, and delete records in a collection."""

    def put(self, collection: str, record: dict, *, record_id: str = "") -> Optional[dict]:
        ...

    def list(self, collection: str) -> list[dict]:
        ...

    def delete(self, collection: str, record_id: str) -> bool:
        ...


_backend: Optional[StorageBackend] = None
_app_id: str = "unknown"


def set_backend(backend: Optional[StorageBackend], *, app_id: str = "unknown") -> None:
    global _backend, _app_id
    _backend = backend
    _app_id = app_id


def get_backend() -> Optional[StorageBackend]:
    return _backend


def available() -> bool:
    return _backend is not None


def put(collection: str, record: dict, *, record_id: str = "") -> Optional[dict]:
    if _backend is None:
        log.debug("put(%s) no-op: no backend configured", collection)
        return None
    return _backend.put(collection, record, record_id=record_id)


def list_records(collection: str) -> list[dict]:
    if _backend is None:
        log.debug("list(%s) no-op: no backend configured", collection)
        return []
    return _backend.list(collection)


def delete(collection: str, record_id: str) -> bool:
    if _backend is None:
        log.debug("delete(%s, %s) no-op: no backend configured", collection, record_id)
        return False
    return _backend.delete(collection, record_id)
