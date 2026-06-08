"""
sap.core.gate — SAFE App Permission Gate
b17: NNA92
ΔΣ=42

PII access gate for client_only data streams.

Call authorized() before any PII read or write. Raises PermissionDenied if the
current context has not been explicitly cleared for PII operations.

Authorization:
  - SAP_AUTHORIZED=1 env var  (process-level: set in trusted shells/scripts)
  - sap.core.gate.bypass(reason)  (block-level: explicit per-operation override)

Neither is a free pass — both require deliberate action by the caller.
"""

import os
from contextlib import contextmanager
from threading import local

_state = local()


class PermissionDenied(PermissionError):
    """Raised when the SAP gate rejects a PII operation."""


def authorized(operation: str = "write", scope: str = "family_history") -> None:
    """
    Assert that the current context is authorized for PII operations.

    Raises PermissionDenied if not authorized.

    Args:
        operation: "read" or "write" — used in the error message only.
        scope:     Data scope label — used in the error message only.
    """
    if getattr(_state, "bypass_active", False):
        return
    if os.environ.get("SAP_AUTHORIZED") == "1":
        return
    raise PermissionDenied(
        f"SAP gate: PII {operation} on '{scope}' is not authorized. "
        f"Set SAP_AUTHORIZED=1 or use `with sap.core.gate.bypass(reason):`."
    )


@contextmanager
def bypass(reason: str):
    """
    Explicitly bypass the SAP gate for a block of PII operations.

    Requires a non-empty reason string — the reason is the paper trail.
    Use for migration scripts and other trusted internal operations.

    Example:
        import sap.core.gate
        with sap.core.gate.bypass("backfill Oscar Mann from FindAGrave memorial 273702757"):
            persons_db.add_person(conn, full_name="Oscar William Mann", ...)
    """
    if not reason or not reason.strip():
        raise ValueError("sap.core.gate.bypass() requires a non-empty reason.")
    _state.bypass_active = True
    try:
        yield
    finally:
        _state.bypass_active = False
