"""The core cannot reach the network, verified by walking the AST.

Adapted from UTETY's test_boundaries and safe-app-common-package's no_egress
scanner. The point of doing it structurally rather than by review: a promise in
a README is checked by whoever remembers to check it, and an import added in a
hurry three months from now will not remind anyone.

asyncio is deliberately absent from the forbidden set — async I/O is not network
egress by itself.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "marching_arts"

FORBIDDEN = {
    "socket", "ssl", "urllib", "urllib3", "http", "httplib", "ftplib",
    "smtplib", "telnetlib", "xmlrpc", "requests", "httpx", "aiohttp",
    "websockets", "paramiko", "boto3",
}

#: Callables that execute a string as code, which would let an import hide from
#: a static scan. The scanner is only as good as the absence of these.
DYNAMIC = {"eval", "exec", "compile", "__import__"}


def _modules() -> "list[Path]":
    return sorted(CORE.rglob("*.py"))


def test_the_core_has_modules_to_scan():
    """A scanner that finds nothing must not pass by finding nothing."""
    assert _modules(), f"no modules under {CORE}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_network_imports(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module.split(".")[0])
    leaked = sorted(set(found) & FORBIDDEN)
    assert not leaked, f"{path.name} imports {leaked}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_dynamic_execution(path: Path):
    """No eval/exec/compile/__import__ — otherwise the import scan above is
    checkable only for the imports someone chose to write plainly."""
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = [
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    leaked = sorted(set(calls) & DYNAMIC)
    assert not leaked, f"{path.name} calls {leaked}"


def test_import_is_stdlib_only():
    """Importing the core must not pull in a third-party package.

    Dependency-light is part of the promotion bar, and it is also what lets this
    core be ported: the browser host reimplements the same rules, and a core
    that needed a package would have needed a port of the package too.
    """
    before = set(sys.modules)
    sys.path.insert(0, str(CORE.parent))
    import marching_arts  # noqa: F401

    stdlib = set(sys.stdlib_module_names)
    added = {
        name.split(".")[0] for name in set(sys.modules) - before
    } - {"marching_arts"}
    third_party = sorted(n for n in added if n and not n.startswith("_")
                         and n not in stdlib)
    assert not third_party, f"core pulled in {third_party}"
