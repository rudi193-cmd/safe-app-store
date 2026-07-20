"""The seam is the only door — package-wide, AST-based, mirroring UTETY's
tests/test_boundaries.py.

`test_core.py` proves core.py is stdlib-only. This walks the ENTIRE package so a
future module added under src/subject_consent/ cannot quietly pull in a network
or subprocess dependency. Both checks are static (no imports executed): the whole
point of this package is that a child-device consumer (UTETY) and a
stdlib-only-charter consumer (corpus-lens) can depend on it without dragging a
runtime in behind it — so the boundary is a test, not a comment.
"""
import ast
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parent.parent / "src" / "subject_consent"
_STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}

# Egress / exec modules named explicitly so a future edit that adds one fails
# loudly even though each is *technically* stdlib.
_BANNED = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib", "telnetlib",
           "subprocess", "asyncio", "multiprocessing", "ctypes",
           "requests", "httpx", "aiohttp", "urllib3"}


def _modules() -> list[Path]:
    return sorted(_PKG.rglob("*.py"))


def test_package_has_modules():
    assert _modules(), f"no modules found under {_PKG}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_module_imports_stdlib_only(path: Path):
    """Every top-level import in every package module resolves to the stdlib."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # relative imports (from .core import …) are package-local — fine.
            if node.level and node.level > 0:
                continue
            if node.module:
                imported.add(node.module.split(".")[0])
    offenders = sorted(m for m in imported if m not in _STDLIB and m != "subject_consent")
    assert not offenders, f"{path.name} imports non-stdlib modules: {offenders}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_module_has_no_egress_or_exec_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            mods = [node.module.split(".")[0]]
        hit = sorted(set(mods) & _BANNED)
        assert not hit, f"{path.name} must not import egress/exec modules: {hit}"
