"""Lab standup helpers — one root for all three products.

``configure_lab(root)`` mints or reuses ``NESTOR_SEAL_KEY`` **before**
anything imports ``willow_mcp.tool_oracle``. The oracle's shipped bundle
is verified under the process seal key on first import; matching keys
across configure_lab and the oracle load avoids the 100+ row demotion
warning the handoff called out.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any


def configure_lab(
    root: str | Path,
    *,
    seal_key: str | None = None,
    mint_seal_key: bool = True,
) -> dict[str, Any]:
    """Point Nestor, Jeles, and willow-mcp at one lab root.

    Sets ``WILLOW_HOME``, ``WILLOW_STORE_ROOT``, ``NESTOR_DB``,
    ``NESTOR_LEDGER``, and ``NESTOR_SEAL_KEY``. The seal key is written to
    ``<root>/nestor/seal.key`` (chmod 0600) so a second session on the
    same lab picks it up rather than minting a new one that would demote
    every previously-sealed row.

    Does not start Postgres, grant net leases, or harden trust root —
    those stay operator ceremony.
    """
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    willow_home = root / "willow_home"
    soil = root / "soil"
    nestor_dir = root / "nestor"
    for d in (willow_home, soil, nestor_dir):
        d.mkdir(parents=True, exist_ok=True)

    os.environ["WILLOW_HOME"] = str(willow_home)
    os.environ["WILLOW_STORE_ROOT"] = str(soil)
    os.environ["NESTOR_DB"] = str(nestor_dir / "nestor.db")
    os.environ["NESTOR_LEDGER"] = str(nestor_dir / "ledger.jsonl")

    key_file = nestor_dir / "seal.key"
    key_source: str
    if seal_key:
        os.environ["NESTOR_SEAL_KEY"] = seal_key
        key_file.write_text(seal_key)
        key_file.chmod(0o600)
        key_source = "provided"
    elif os.environ.get("NESTOR_SEAL_KEY"):
        key_source = "env"
    elif key_file.exists():
        os.environ["NESTOR_SEAL_KEY"] = key_file.read_text().strip()
        key_source = "seal.key"
    elif mint_seal_key:
        os.environ["NESTOR_SEAL_KEY"] = secrets.token_hex(32)
        key_file.write_text(os.environ["NESTOR_SEAL_KEY"])
        key_file.chmod(0o600)
        key_source = "minted"
    else:
        key_source = "absent"

    return {
        "root": str(root),
        "WILLOW_HOME": os.environ["WILLOW_HOME"],
        "WILLOW_STORE_ROOT": os.environ["WILLOW_STORE_ROOT"],
        "NESTOR_DB": os.environ["NESTOR_DB"],
        "NESTOR_LEDGER": os.environ["NESTOR_LEDGER"],
        "NESTOR_SEAL_KEY": {
            "source": key_source,
            "path": str(key_file) if key_source in ("minted", "seal.key", "provided") else None,
        },
    }


def doctor_summary() -> dict[str, Any]:
    """Cheap health snapshot across the three products."""
    out: dict[str, Any] = {"env": {}, "imports": {}, "oracle": {}, "willow_doctor": None}

    for k in ("WILLOW_HOME", "WILLOW_STORE_ROOT", "NESTOR_DB", "NESTOR_LEDGER", "NESTOR_SEAL_KEY"):
        v = os.environ.get(k)
        out["env"][k] = ("set" if v else "missing") if k == "NESTOR_SEAL_KEY" else v

    for name in ("nestor", "jeles", "willow_mcp"):
        try:
            __import__(name)
            out["imports"][name] = True
        except Exception as exc:
            out["imports"][name] = f"{type(exc).__name__}: {exc}"

    try:
        from willow_mcp import tool_oracle
        out["oracle"] = {
            "nestor_available": tool_oracle.available(),
            "pending_count": len(tool_oracle.pending() or []),
        }
    except Exception as exc:
        out["oracle"] = {"error": f"{type(exc).__name__}: {exc}"}

    try:
        from nestor import cascade
        out["cascade"] = {
            "tier15_wired": cascade.get_tier15_recognizer() is not None,
        }
    except Exception as exc:
        out["cascade"] = {"error": f"{type(exc).__name__}: {exc}"}

    # willow_mcp doctor is a subcommand; keep it optional so a broken doctor
    # doesn't fail the summary.
    try:
        r = subprocess.run(
            [sys.executable, "-m", "willow_mcp", "doctor"],
            capture_output=True, text=True, env=os.environ.copy(), timeout=60,
        )
        text = (r.stdout or r.stderr or "").strip()
        verdict = "unknown"
        for line in text.splitlines():
            if "verdict" in line.lower():
                verdict = line.split(":", 1)[-1].strip()
                break
        out["willow_doctor"] = {"verdict": verdict, "returncode": r.returncode}
    except Exception as e:
        out["willow_doctor"] = {"error": f"{type(e).__name__}: {e}"}

    return out
