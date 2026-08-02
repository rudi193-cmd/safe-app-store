"""Nothing leaves this machine, verified structurally rather than by review.

Adapted from marching-arts' test_no_egress. The split here is finer than that
app's, because playgate genuinely serves a socket: the core must import nothing
network-shaped at all, and `server.py` — which necessarily imports http.server —
must import no outbound *client*. Serving a socket the local browser connects to
is not egress. Opening one to somewhere else is.

The distinction matters for the manifest. This app's `network` field describes a
loopback listener, and that claim is worth exactly as much as this file.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "playgate"
SERVER = PACKAGE / "server.py"

#: Anything that could originate a connection. Top-level names, applied to the
#: core, where none of this has any business appearing.
OUTBOUND = {
    "socket", "ssl", "urllib", "urllib3", "httplib", "ftplib", "smtplib",
    "telnetlib", "xmlrpc", "requests", "httpx", "aiohttp", "websockets",
    "paramiko", "boto3", "webbrowser",
}

#: The same set for server.py, minus `urllib` — which is not one module. The
#: server parses query strings with urllib.parse, which is string handling and
#: opens nothing; urllib.request is the client and stays forbidden. Naming the
#: submodules rather than the package is the difference between a scan that
#: means something and one that is merely strict.
OUTBOUND_TOP_IN_SERVER = OUTBOUND - {"urllib"}
OUTBOUND_FULL = {"urllib.request", "urllib.error", "urllib.robotparser"}

#: Serving-side stdlib, allowed in server.py and nowhere else.
LISTENERS = {"http", "socketserver", "wsgiref"}

DYNAMIC = {"eval", "exec", "compile", "__import__"}


def _core_modules() -> "list[Path]":
    return sorted(p for p in PACKAGE.rglob("*.py") if p != SERVER)


def _imported_names(path: Path) -> "set[str]":
    """Every imported module, as written — dotted, not truncated."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return set(found)


def _imports(path: Path) -> "set[str]":
    """Top-level package names only."""
    return {name.split(".")[0] for name in _imported_names(path)}


def test_there_are_core_modules_to_scan():
    """A scanner that passes by finding nothing must not pass."""
    assert _core_modules(), f"no modules under {PACKAGE}"


def test_the_server_module_exists_to_be_scanned():
    """If server.py is renamed, the exemption below must move with it rather
    than silently exempting nothing while the real listener goes unchecked."""
    assert SERVER.is_file(), f"{SERVER} missing; the exemption in this file is stale"


@pytest.mark.parametrize("path", _core_modules(), ids=lambda p: p.name)
def test_core_imports_nothing_network_shaped(path: Path):
    leaked = sorted(_imports(path) & (OUTBOUND | LISTENERS))
    assert not leaked, f"{path.name} imports {leaked}"


def test_the_server_listens_but_does_not_call_out():
    names = _imported_names(SERVER)
    leaked = sorted(
        ({n.split(".")[0] for n in names} & OUTBOUND_TOP_IN_SERVER)
        | (names & OUTBOUND_FULL)
    )
    assert not leaked, f"server.py imports outbound client(s) {leaked}"


def test_the_narrower_server_rule_still_catches_a_real_client():
    """The exemption above is for urllib.parse specifically. If it were written
    as "allow anything under urllib", urllib.request would walk straight
    through it — so this asserts on the rule itself rather than trusting it.
    """
    names = {"urllib.parse", "urllib.request"}
    leaked = (
        ({n.split(".")[0] for n in names} & OUTBOUND_TOP_IN_SERVER)
        | (names & OUTBOUND_FULL)
    )
    assert leaked == {"urllib.request"}


@pytest.mark.parametrize(
    "path", sorted(PACKAGE.rglob("*.py")), ids=lambda p: p.name
)
def test_no_dynamic_execution(path: Path):
    """Without this the import scans above are only checkable for the imports
    somebody chose to write plainly."""
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = [
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    leaked = sorted(set(calls) & DYNAMIC)
    assert not leaked, f"{path.name} calls {leaked}"


def test_serve_refuses_a_non_loopback_bind():
    """The loopback claim is a mechanism, not a comment.

    Binding 0.0.0.0 would put a child's request queue and a parent's decisions
    on the local network.
    """
    from playgate import server

    for host in ("0.0.0.0", "192.168.1.10", "::"):
        with pytest.raises(ValueError, match="loopback"):
            server.serve([], None, host=host)


def test_import_is_stdlib_only():
    """The core must not pull in a third-party package.

    requirements.txt is empty on purpose; this is what keeps it true.
    """
    before = set(sys.modules)
    sys.path.insert(0, str(PACKAGE.parent))
    import playgate  # noqa: F401
    from playgate import catalog, disposition, install, interruption  # noqa: F401

    stdlib = set(sys.stdlib_module_names)
    added = {name.split(".")[0] for name in set(sys.modules) - before} - {"playgate"}
    third_party = sorted(
        n for n in added if n and not n.startswith("_") and n not in stdlib
    )
    assert not third_party, f"core pulled in {third_party}"
