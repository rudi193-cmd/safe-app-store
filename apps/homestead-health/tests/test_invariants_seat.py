"""Bite 1 — the seat, held to its *done when*.

`homestead/docs/PLAN-homestead-health.md` § bite 1: cold checkout installs and
the suite is green; grepping the package for network imports, `expanduser`,
and a second path resolver all come back empty (I-19/I-20/I-26/I-27/I-28).
These are the engine's own scans (`tests/test_invariants_shape.py`,
`tests/test_invariants_paths.py`) aimed at this package — the same checks
because they are the same claims, one module over.
"""
from __future__ import annotations

import ast
import importlib.metadata as md
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PKG = APP / "homestead_health"

NET = {"socket", "ssl", "urllib", "http", "requests", "httpx",
       "aiohttp", "websockets", "urllib3", "socketserver", "ftplib",
       "telnetlib", "smtplib", "xmlrpc"}


def _modules() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _toplevel_imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


# ── the pin ──────────────────────────────────────────────────────────────────


def test_the_engine_pin_is_true():
    """I-27, both halves: the declared engine is the installed engine.

    `import homestead.keep` succeeding proves an engine is present;
    resolving the *distribution* proves it is the declared one
    (`homestead-affairs`), not a same-named package that happens to be
    importable — the import name and the distribution name differ by design,
    and only the metadata ties them together.
    """
    import homestead.keep  # noqa: F401

    version = md.version("homestead-affairs")
    assert version, "the engine distribution is not installed; the pin is not true"


def test_the_pin_has_a_floor_and_a_cap():
    """The engine is pre-1.0 and decides what renders; the dependency line
    states the release this seat was verified against and refuses the next
    minor unseen — the engine's own floor-and-cap reasoning for `holidays`."""
    dependency_block = re.search(
        r"^dependencies\s*=\s*\[(.*?)\]",
        (APP / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    assert dependency_block, "pyproject.toml must declare its dependencies"
    pin = re.search(r'"homestead-affairs([^"]*)"', dependency_block.group(1))
    assert pin, "the engine pin is the one declared dependency, and it is missing"
    spec = pin.group(1)
    assert ">=" in spec, f"the pin needs a floor (got {spec!r})"
    assert "<" in spec, f"the pin needs a cap — the engine is pre-1.0 (got {spec!r})"


def test_the_seat_imports_clean():
    """Importing the package from a fresh interpreter works and pulls no
    network module into the process — I-26 measured on the live import, not
    just the source scan below."""
    probe = (
        "import sys; import homestead_health; "
        f"bad = sorted(set(sys.modules) & {NET!r}); "
        "print('NET:' + ','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=APP, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "NET:\n" in result.stdout or result.stdout.strip() == "NET:", (
        f"importing the seat pulled network modules: {result.stdout}"
    )


# ── the scans (the *done when* greps, as tests) ──────────────────────────────


def test_i30_i26_nothing_imports_the_network():
    """No network module at import time, anywhere in the package."""
    offenders = {}
    for mod in _modules():
        hits = NET & _toplevel_imports(ast.parse(mod.read_text(encoding="utf-8")))
        if hits:
            offenders[str(mod.relative_to(APP))] = sorted(hits)
    assert not offenders, (
        f"nothing in this module dials — H-5's fetch half and I-26. Found: {offenders}"
    )


def test_i30_nothing_listens():
    """No bind/listen/serve call, however spelled. `bind` itself is not
    banned, for the engine's stated tkinter reason; these names have no GUI
    meaning."""
    banned = {"listen", "serve_forever", "create_server", "ThreadingHTTPServer"}
    offenders = []
    for mod in _modules():
        for node in ast.walk(ast.parse(mod.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name in banned:
                    offenders.append(f"{mod.relative_to(APP)}:{node.lineno} {name}")
    assert not offenders, f"nothing may listen. Found: {offenders}"


def test_i19_i20_no_second_resolver():
    """Every path this module ever touches comes from `homestead.keep.paths`.

    Two spellings are banned outright (I-20's lesson: `expanduser` is
    invisible to the store's vault-leak linter), and `Path.home` with them —
    a module that can reach a home directory has a second resolver, whatever
    it calls it.
    """
    banned_calls = {"expanduser", "expandvars", "home"}
    offenders = []
    for mod in _modules():
        for node in ast.walk(ast.parse(mod.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name in banned_calls:
                    offenders.append(f"{mod.relative_to(APP)}:{node.lineno} {name}")
    assert not offenders, (
        f"the one resolver is the engine's (homestead.keep.paths). Found: {offenders}"
    )
    # And the one resolver exists to be used: the claim is "use the engine's",
    # which is only honest while the engine has one.
    assert importlib.util.find_spec("homestead.keep.paths") is not None


def test_i27_every_third_party_import_is_declared():
    """Nothing is imported that `pyproject.toml` does not name — the engine's
    ambient-dependency scan, verbatim. The engine brings `holidays`, which
    brings `python-dateutil`, which brings `six`: all three are importable
    here without being declared, which is exactly the shape this forbids."""
    dependency_block = re.search(
        r"^dependencies\s*=\s*\[(.*?)\]",
        (APP / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    assert dependency_block
    declared = {
        m.lower().replace("_", "-")
        for m in re.findall(r'"([A-Za-z0-9._-]+)', dependency_block.group(1))
    }

    dist_of = md.packages_distributions()
    offenders: list[str] = []
    for mod in _modules():
        for name in _toplevel_imports(ast.parse(mod.read_text(encoding="utf-8"))):
            if name in ("homestead", "homestead_health") or name in sys.stdlib_module_names:
                continue
            dists = {d.lower().replace("_", "-") for d in dist_of.get(name, [])}
            if not dists & declared:
                offenders.append(
                    f"{mod.relative_to(APP)} imports {name!r}"
                    f" (ships in {sorted(dists) or 'nothing installed'})"
                )
    assert not offenders, (
        "every third-party import must be a declared dependency, not one that "
        f"happens to be installed. Found: {offenders}"
    )


def test_i28_no_test_basename_is_shadowed():
    """The engine's check, kept for the same reason: a shadowed basename is
    how a suite stops being seen."""
    names = [p.name for p in APP.rglob("test_*.py") if ".git" not in p.parts]
    assert len(names) == len(set(names)), f"duplicate test basenames: {names}"
