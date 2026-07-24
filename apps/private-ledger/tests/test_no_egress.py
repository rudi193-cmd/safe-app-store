"""The no-egress zone is structural, not policy (oakenscrolls pattern): the
ledger and the math must be incapable of talking to anything. An AST scan
refuses network, process, and FFI imports in the core modules, and refuses the
core from importing the outward web seam.

CORE (no-egress): db.py, schema.py, pl_paths.py, subscriptions.py.
OUTWARD (excluded): web.py, app.py, llm.py, serve.py.
"""
import ast
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "src" / "private_ledger"
NO_EGRESS_MODULES = ("db.py", "schema.py", "pl_paths.py", "subscriptions.py")
BRIDGE = CORE / "willow_bridge.py"
SERVE = CORE / "serve.py"
FORBIDDEN = {
    "socket", "http", "urllib", "requests", "httpx", "aiohttp", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "webbrowser",
    "subprocess", "ctypes", "multiprocessing",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_core_modules_cannot_egress():
    for name in NO_EGRESS_MODULES:
        leaked = _imports(CORE / name) & FORBIDDEN
        assert not leaked, f"{name} imports forbidden modules: {sorted(leaked)}"


def test_core_does_not_import_the_web_seam():
    for name in NO_EGRESS_MODULES:
        imports = _imports(CORE / name)
        assert "web" not in imports, (
            f"{name} must not import web — the seam points outward only"
        )


def test_core_does_not_import_the_willow_bridge():
    """The Willow seam points OUTWARD only: bridge imports core, never reverse."""
    for name in NO_EGRESS_MODULES:
        imports = _imports(CORE / name)
        assert "willow_bridge" not in imports, (
            f"{name} must not import willow_bridge — the bridge imports the "
            "core, never the reverse"
        )


def test_core_does_not_import_the_serve_seam():
    """The stdio seam points OUTWARD only: serve imports the core, never the
    reverse. A core module reaching for serve would be a leak of direction."""
    for name in NO_EGRESS_MODULES:
        imports = _imports(CORE / name)
        assert "serve" not in imports, (
            f"{name} must not import serve — the seam points outward only"
        )


def test_serve_seam_is_stdio_only():
    """serve.py is OUTWARD (not in the core set) but must still never phone
    home: it is a stdio command loop, so it imports no network module. The
    protocol reaches the world only through stdin/stdout."""
    leaked = _imports(SERVE) & FORBIDDEN
    assert not leaked, f"serve imports forbidden modules: {sorted(leaked)}"


def test_willow_bridge_is_pure_injection():
    """willow_bridge is OUTWARD (not in the core set) but must still never phone
    home: no ``import willow`` and no network/process import. It reaches Willow
    only through an INJECTED ingest callable."""
    imports = _imports(BRIDGE)
    assert "willow" not in imports, (
        "willow_bridge must not import willow — it is pure dependency injection"
    )
    leaked = imports & FORBIDDEN
    assert not leaked, f"willow_bridge imports forbidden modules: {sorted(leaked)}"
