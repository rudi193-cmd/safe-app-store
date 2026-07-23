"""The no-egress zone is structural, not policy (utety pattern, verbatim in
spirit): the ledger and the math must be incapable of talking to anything.
An AST scan refuses network, process, and FFI imports in core modules."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NO_EGRESS_MODULES = ("office_db.py", "office_paths.py", "calibration.py", "almanac_seam.py")
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
        leaked = _imports(ROOT / name) & FORBIDDEN
        assert not leaked, f"{name} imports forbidden modules: {sorted(leaked)}"


def test_core_does_not_import_the_bridge():
    for name in NO_EGRESS_MODULES:
        assert "willow_bridge" not in _imports(ROOT / name), (
            f"{name} must not import willow_bridge — the seam points outward only"
        )
