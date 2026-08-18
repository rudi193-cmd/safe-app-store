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


def _all_imports(tree: ast.Module) -> set[str]:
    """Every imported top-level name, **anywhere in the tree** — including a lazy
    import nested inside a function body.

    The H-5 audit found `_toplevel_imports` (which walks `tree.body` only) blind to
    `def f(): import socket` — a deferred dial that never shows at module scope. The
    network scan below uses this full walk instead, so 'nothing dials' means nothing,
    not nothing at the top level. (The declared-dependency scan keeps
    `_toplevel_imports`: a lazy third-party import is a different, lesser sin, and
    the network rule is the one that must be total.)"""
    names: set[str] = set()
    for node in ast.walk(tree):
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
    """No network module anywhere in the package — at module scope or lazily inside
    a function body. A full-tree walk, after the H-5 audit showed a top-level-only
    scan misses a deferred `import socket`."""
    offenders = {}
    for mod in _modules():
        hits = NET & _all_imports(ast.parse(mod.read_text(encoding="utf-8")))
        if hits:
            offenders[str(mod.relative_to(APP))] = sorted(hits)
    assert not offenders, (
        f"nothing in this module dials — H-5's fetch half and I-26. Found: {offenders}"
    )


def test_the_network_scan_sees_a_lazy_import(tmp_path):
    """The scan itself, held honest. A network import hidden inside a function body
    must be caught — the exact bypass the H-5 audit planted, which the old
    top-level-only walk sailed past."""
    probe = tmp_path / "lazy.py"
    probe.write_text("def dial():\n    import socket\n    return socket\n")
    tree = ast.parse(probe.read_text())
    assert NET & _all_imports(tree), "a lazy `import socket` must be caught"
    assert not (NET & _toplevel_imports(tree)), "and it is invisible to the top-level walk"


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


# ── I-19 / I-20 · no second resolver, by any mechanism ───────────────────────
#
# **Rewritten after the bite-1 audit (2026-08-11), which earned its keep the
# way the Phase 0 audit did.** The first version of this scan banned three
# call *names* and advertised itself as "the engine's own scans … the same
# checks". It was not: the engine's `tests/test_invariants_paths.py` was
# itself rewritten after the Phase 0 audit because a call-name scan let
# `Path(os.environ["HOME"]) / "Desktop" / "Nest"` — the Desktop leak, F-1,
# in idiomatic pathlib — pass the whole suite (`os.environ[...]` is a
# Subscript, not a call; `/ "Desktop"` contains no slash). The audit planted
# the engine's own regression payload here and this file stayed green while
# the engine's caught it twice. The copy below is the engine's mechanism
# scan ported whole — home-reaching calls *and* environment subscripts *and*
# user-directory literals in path context — with the engine's regression
# test kept, so the next weakened copy is caught by its own suite.

HOME_CALLS = {"expanduser", "expandvars", "getenv"}
HOME_ENV_KEYS = {"HOME", "USERPROFILE", "HOMEPATH", "HOMEDRIVE"}
BANNED_SEGMENTS = {"desktop", "documents", "downloads", "users", "home", "~"}


def _dotted(node: ast.AST) -> str:
    """`Path.home` from a `Path.home()` call; `paths.home` from `paths.home()`."""
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}".lstrip(".")
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Docstrings are excluded from the literal scan — the engine's lesson: a
    scanner that fires on its own documentation gets switched off."""
    ids: set[int] = set()
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _home_reaches(tree: ast.AST) -> list[tuple[int, str]]:
    """Every construct in this tree that reaches a home directory."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Path.home(), os.path.expanduser(...), os.getenv("HOME"),
        # os.path.expandvars("$HOME"), and any aliased binding of them.
        # `paths.home` is exempt: that is the engine's resolver, which is the
        # one legitimate way for this module to hold a root at all.
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            leaf = dotted.rsplit(".", 1)[-1]
            if leaf == "home" and dotted != "paths.home":
                hits.append((node.lineno, dotted or "home"))
            elif leaf in HOME_CALLS:
                hits.append((node.lineno, dotted or leaf))
        # os.environ["HOME"] / environ.get("HOME") — a Subscript, not a call,
        # which is exactly how the Desktop leak walked through a name scan.
        elif isinstance(node, ast.Subscript):
            if "environ" in _dotted(node.value):
                key = getattr(node.slice, "value", None)
                if isinstance(key, str) and key.upper() in HOME_ENV_KEYS:
                    hits.append((node.lineno, f"environ[{key!r}]"))
    return hits


def _path_context_strings(tree: ast.AST) -> list[tuple[int, str]]:
    """String literals used to *build a path* — an operand of `/`, an argument
    to `Path(...)`, or any string carrying a separator. The engine's scoping,
    for the engine's reason: broad enough to catch `/ "Desktop"`, narrow
    enough not to fire on a symbol named "home" in `__all__`."""
    out: list[tuple[int, str]] = []
    skip = _docstring_ids(tree)

    def note(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in skip:
            out.append((node.lineno, node.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            note(node.left)
            note(node.right)
        elif isinstance(node, ast.Call) and _dotted(node.func).rsplit(".", 1)[-1] == "Path":
            for arg in node.args:
                note(arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in skip:
            if "/" in node.value or "\\" in node.value:
                out.append((node.lineno, node.value))
    return out


def test_i19_i20_nothing_here_reaches_home():
    """No module in this package may reach a home directory, by any means.

    Stricter than the engine's version of the same scan on purpose: the
    engine exempts its own resolver file, and this package has no resolver
    file to exempt — the resolver is the engine's (`homestead.keep.paths`),
    one dependency over.
    """
    offenders = []
    for mod in _modules():
        for lineno, how in _home_reaches(ast.parse(mod.read_text(encoding="utf-8"))):
            offenders.append(f"{mod.relative_to(APP)}:{lineno} {how}")
    assert not offenders, (
        "only the engine's resolver (homestead.keep.paths) may reach a home "
        f"directory. Found: {offenders}"
    )
    # And the one resolver exists to be used: the claim is "use the engine's",
    # which is only honest while the engine has one.
    assert importlib.util.find_spec("homestead.keep.paths") is not None


def test_i20_the_invisible_spelling_is_banned_everywhere():
    """`expanduser` is invisible to the store's vault-leak linter, so it is
    banned in every spelling and every position — the engine's rule, verbatim."""
    offenders = []
    for mod in _modules():
        for node in ast.walk(ast.parse(mod.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) \
                    and _dotted(node.func).rsplit(".", 1)[-1] == "expanduser":
                offenders.append(f"{mod.relative_to(APP)}:{node.lineno}")
    assert not offenders, f"expanduser() is invisible to the linter. Found: {offenders}"


def test_i19_no_user_directory_literals():
    """Segment-wise and in path context — `/ "Desktop" / "Nest"` contains no
    slash and a substring scan never sees it."""
    offenders = []
    for mod in _modules():
        for lineno, value in _path_context_strings(ast.parse(mod.read_text(encoding="utf-8"))):
            segments = {s.strip().lower() for s in value.replace("\\", "/").split("/")}
            hit = segments & BANNED_SEGMENTS
            if hit:
                offenders.append(
                    f"{mod.relative_to(APP)}:{lineno} {value!r} ({sorted(hit)})"
                )
    assert not offenders, f"user-directory literals are forbidden. Found: {offenders}"


def test_i19_regression_desktop_leak(tmp_path):
    """The engine's regression payload, held against *this* file's scans.

    The bite-1 audit planted exactly this in a scratch copy of the package
    and the first version of this suite stayed green — the same defect the
    engine's Phase 0 audit found in its first path scan, reintroduced by
    copying the weaker version. Both scans must catch it, here, forever.
    """
    leak = tmp_path / "leaky.py"
    leak.write_text(
        "import os\n"
        "from pathlib import Path\n"
        '_LEAK = Path(os.environ["HOME"]) / "Desktop" / "Nest"\n'
    )
    tree = ast.parse(leak.read_text())

    assert _home_reaches(tree), "the mechanism scan must catch os.environ['HOME']"

    caught = [
        v for _, v in _path_context_strings(tree)
        if {s.lower() for s in v.split("/")} & BANNED_SEGMENTS
    ]
    assert caught, "the literal scan must catch a bare 'Desktop' segment"


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
