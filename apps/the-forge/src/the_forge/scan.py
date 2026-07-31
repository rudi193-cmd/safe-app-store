"""scan.py — the seam's pre-crossing static scan (D3).

Runs on a `FileWrite` entry's content before the seam lets it cross. This is
a floor, not a proof (D3): it catches the obvious/accidental case, not a
determined adversary — Kart's sandbox (D2) is what actually contains
execution, not this scan.

Deliberately NOT adapted from either existing precedent as-is, per D3's
correction (2026-08-01):

- `tools/vault_leak_lint.py` is line-based regex, not AST — a different
  tool for a different question (fixed-path data leaks), not reused here.
- `stores/promote_check.py`'s `_toplevel_dynamic_net` is AST-based but
  deliberately top-level-only, because it's answering an import-time
  question. This scan is answering a runtime-behavior question — generated
  code that hasn't executed yet at all — so it walks function bodies too.
  `def f(): os.system(...)` has to be visible here even though
  `promote_check.py` correctly ignores it for its own purpose.

Python source only. A `FileWrite` for any other language is not covered by
this scan — named as a real, current limitation, not silently glossed over.

Checks (AST-based):
  network_call     — import of a network-root module (same list
                      `promote_check.py` uses: socket, ssl, urllib, http,
                      requests, httpx, aiohttp, websockets, urllib3),
                      anywhere in the file, not just at module level.
  process_exec     — subprocess.*, os.system, os.popen, os.exec* family.
  dynamic_exec     — eval, exec, compile.
  dynamic_import   — __import__, importlib.import_module — may pull in any
                      of the above transitively; flagged for the gate/human
                      to decide, not resolved here.

Import aliasing is resolved (`import os as o; o.system(...)` and
`from os import system as go; go(...)` both flag as `os.system`) — an
unaliased-literal-only check would make the alias itself the evasion.
Known remaining gap, accepted rather than silently glossed over: re-aliasing
a *builtin* (`from builtins import eval as go`) is not resolved, since it's
a rare enough pattern that chasing it added more complexity than the floor
this scan aims for justifies.
"""
from __future__ import annotations

import ast
import dataclasses

# Same vocabulary as stores/promote_check.py's _NET — not imported from it,
# since the_forge stays import-pure (D13) and doesn't reach into
# safe-app-store internals. Kept in sync by hand; if that drifts, it drifts
# in the direction of over-flagging, not under-flagging.
_NET_MODULES = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
                "websockets", "urllib3"}

_PROCESS_EXEC_ATTRS = {"system", "popen", "execl", "execle", "execlp", "execlpe",
                        "execv", "execve", "execvp", "execvpe", "spawnl", "spawnle",
                        "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"}
_DYNAMIC_EXEC_NAMES = {"eval", "exec", "compile"}
_DYNAMIC_IMPORT_NAMES = {"__import__", "import_module"}


@dataclasses.dataclass(frozen=True)
class Finding:
    rule: str  # "network_call" | "process_exec" | "dynamic_exec" | "dynamic_import"
    line: int
    col: int
    detail: str


class ScanError(Exception):
    """The source couldn't even be parsed — refused before it's scanned for
    anything else. A build that can't produce parseable Python has nothing
    here to evaluate honestly."""


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def _call_name(node: ast.Call) -> tuple[str | None, str | None]:
    """Returns (owner, attr) for `owner.attr(...)`, or (None, name) for a
    bare `name(...)`."""
    fn = node.func
    if isinstance(fn, ast.Name):
        return None, fn.id
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        return fn.value.id, fn.attr
    return None, None


def _collect_aliases(tree: ast.AST) -> dict[str, str]:
    """Map a bound name to what it actually refers to, so `import os as o;
    o.system(...)` and `from os import system as go; go(...)` resolve back
    to `os.system` the same as the unaliased spelling would. Without this,
    the alias IS the evasion — a scan that only recognizes `os.system(...)`
    literally is trivial to defeat with one `from` line."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                # unaliased `import os.path` binds the root `os` — no entry
                # needed, `os` already resolves to itself.
    return aliases


def scan_source(source: str, *, filename: str = "<generated>") -> list[Finding]:
    """Walk the WHOLE tree — `ast.walk`, not `tree.body` — so a check
    nested in a function, a class method, a comprehension, or a nested
    def is just as visible as one at module level."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise ScanError(f"{filename}: does not parse as Python: {e}") from e

    aliases = _collect_aliases(tree)
    process_exec_targets = {f"os.{a}" for a in _PROCESS_EXEC_ATTRS}

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [n.name for n in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                root = _root_module(name)
                if root in _NET_MODULES:
                    findings.append(Finding("network_call", node.lineno, node.col_offset,
                                             f"import of network module {root!r}"))
        elif isinstance(node, ast.Call):
            owner, attr = _call_name(node)
            if owner is not None:
                qualified = f"{aliases.get(owner, owner)}.{attr}"
            elif attr is not None:
                qualified = aliases.get(attr, attr)
            else:
                continue

            if qualified in process_exec_targets or qualified.startswith("subprocess."):
                findings.append(Finding("process_exec", node.lineno, node.col_offset, f"{qualified}(...)"))
            elif qualified in _DYNAMIC_EXEC_NAMES:
                findings.append(Finding("dynamic_exec", node.lineno, node.col_offset, f"{qualified}(...)"))
            elif qualified in _DYNAMIC_IMPORT_NAMES or qualified == "importlib.import_module":
                findings.append(Finding("dynamic_import", node.lineno, node.col_offset, f"{qualified}(...)"))
    return findings


def scan_plan(entries) -> dict[str, list[Finding]]:
    """Scan every `FileWrite` entry in a plan's `entries` whose `dest_path`
    ends in `.py`. Returns `{dest_path: findings}` for entries with at least
    one finding — a clean entry is simply absent, not present with an empty
    list, so a caller checking `if scan_plan(plan.entries):` gets a
    plan-is-clean signal for free. Non-Python `FileWrite`s and `McpCall`
    entries are skipped, not flagged — this scan has nothing to say about
    them (see module docstring)."""
    from .plan import FileWrite  # local import: keeps plan.py free of a scan.py dependency

    results: dict[str, list[Finding]] = {}
    for entry in entries:
        if isinstance(entry, FileWrite) and entry.dest_path.endswith(".py"):
            found = scan_source(entry.content, filename=entry.dest_path)
            if found:
                results[entry.dest_path] = found
    return results
