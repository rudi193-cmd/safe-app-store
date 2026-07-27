"""Tests for the promotion-gate hardening (box audit B13).

Covers the two gaps closed: the pure-core import scan now catches dynamic
imports done at import time (``__import__`` / ``importlib.import_module``), and
the gate now runs the store's vault-leak lint.
"""
import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("promote_check", _REPO / "stores" / "promote_check.py")
promote_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_check)


# ── dynamic import-time network detection ─────────────────────────────────────

def _w(tmp_path, body: str) -> Path:
    p = tmp_path / "m.py"
    p.write_text(body)
    return p


def test_static_scan_still_misses_dynamic__caught_by_new_helper(tmp_path):
    p = _w(tmp_path, '__import__("socket")\n')
    assert promote_check._toplevel_imports(p) == set()          # static scan blind to it
    assert promote_check._toplevel_dynamic_net(p) == {"socket"}  # new helper catches it


def test_importlib_import_module_at_toplevel_is_caught(tmp_path):
    p = _w(tmp_path, "import importlib\nimportlib.import_module('ssl')\n")
    assert promote_check._toplevel_dynamic_net(p) == {"ssl"}


def test_dynamic_import_inside_function_is_lazy_and_ignored(tmp_path):
    p = _w(tmp_path, "def go():\n    __import__('socket')\n")
    assert promote_check._toplevel_dynamic_net(p) == set()      # runs later, not at import


def test_dynamic_import_of_nonnet_module_ignored(tmp_path):
    p = _w(tmp_path, "__import__('json')\n")
    assert promote_check._toplevel_dynamic_net(p) == set()


# ── vault-leak gate ───────────────────────────────────────────────────────────

def test_vault_leak_gate_passes_clean_candidate(tmp_path):
    (tmp_path / "app.py").write_text(
        "import os\nDB = os.environ.get('WILLOW_STORE_ROOT', '/x') + '/app.db'\n")
    gate, ok, _ = promote_check._vault_leak_gate(tmp_path)
    assert gate == "vault_leak [M]" and ok is True


def test_vault_leak_gate_fails_on_data_at_fixed_home_path(tmp_path):
    (tmp_path / "leak.py").write_text(
        "from pathlib import Path\nDB = Path.home() / 'myapp' / 'data.db'\n")
    gate, ok, detail = promote_check._vault_leak_gate(tmp_path)
    assert gate == "vault_leak [M]" and ok is False
    assert "fixed path" in detail
