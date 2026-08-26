"""Process-local hook install.

The only wiring left here is the tier-1.5 recognizer, and that goes
through the seam Nestor ships (``cascade.set_tier15_recognizer``,
decision 0205). No monkeypatch of ``cascade.translate_segment``, no
sys.path shim, no shadow package.
"""
from __future__ import annotations

from typing import Any

_installed = False


def install(
    *,
    seed_jeles_demo: bool = False,
    ensure_seal_key: bool = True,
) -> dict[str, Any]:
    """Wire the established recognizer through Nestor's cascade seam.

    ``seed_jeles_demo``: also load the four demo nuggets (three human,
    one asserted decoy that must be refused).

    ``ensure_seal_key``: warn if ``NESTOR_SEAL_KEY`` is unset. Sealing
    without a key still works, but seal signatures aren't verified — the
    lab standup mints one via :func:`configure_lab` for exactly this
    reason.
    """
    global _installed
    report: dict[str, Any] = {"wire": None, "jeles_seed": None, "seal_key": None}

    if ensure_seal_key:
        import os
        report["seal_key"] = "set" if os.environ.get("NESTOR_SEAL_KEY") else "missing"

    try:
        from nestor.established import install as est_install
        est_install()
        from nestor import cascade
        report["wire"] = "installed" if cascade.get_tier15_recognizer() is not None else "failed"
    except Exception as exc:
        report["wire"] = {"error": type(exc).__name__, "detail": str(exc)}

    if seed_jeles_demo:
        try:
            from nestor.established import seed_demo_nuggets
            report["jeles_seed"] = seed_demo_nuggets()
        except Exception as exc:
            report["jeles_seed"] = {"error": type(exc).__name__, "detail": str(exc)}

    _installed = True
    return report


def uninstall() -> None:
    """Undo the tier-1.5 registration."""
    global _installed
    try:
        from nestor.established import uninstall as est_uninstall
        est_uninstall()
    except Exception:
        pass
    _installed = False


def installed() -> bool:
    return _installed
