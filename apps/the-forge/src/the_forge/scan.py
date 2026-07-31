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
An executable non-`.py` `FileWrite` (a shell script, say) is flagged
unconditionally as `unscanned_executable` rather than passed through
unexamined — see `scan_plan`.

Checks (AST-based):
  network_call        — import of a network-root module (socket, ssl,
                         urllib, http, requests, httpx, aiohttp, websockets,
                         urllib3, ftplib, smtplib, xmlrpc, asyncio,
                         webbrowser), anywhere in the file, not just at
                         module level.
  process_exec        — subprocess.*, os.system/popen/exec*/fork*/spawn*/
                         posix_spawn*.
  dynamic_exec         — eval, exec, compile.
  dynamic_import       — __import__, importlib.import_module — may pull in
                         any of the above transitively; flagged for the
                         gate/human to decide, not resolved here.
  native_or_dynamic_risk — import of ctypes (arbitrary native code), pickle/
                         marshal/shelve (deserialization can execute code),
                         pty/runpy/multiprocessing (process/interpreter
                         control this scan otherwise has no visibility into).
  unscanned_executable — a FileWrite marked executable whose content this
                         scan cannot examine at all (not `.py`).

Import aliasing is resolved for both imports (`import os as o; o.system(...)`
and `from os import system as go; go(...)` both flag as `os.system`) and
simple top-level assignment (`run = os.system; run(...)` also flags) — a
check that only recognized the unaliased literal spelling would make the
alias itself the evasion.

This is a floor, not a proof (D3), and the honest remaining gap list is
longer than earlier drafts of this docstring said — found in the 2026-08-01
audit, listed here instead of understated:
  - Dynamic attribute lookup: `getattr(os, "system")(...)`,
    `os.__dict__["system"](...)`, any subscript/getattr-based dispatch.
  - Non-`Name` owners: `ns.mod.system(...)` — `_call_name` only resolves
    `owner.attr(...)` where `owner` is a bare name, not a deeper chain.
  - Calls reached through a decorator, a class body, or built from string
    concatenation/f-strings and passed to something else that invokes them.
  - Re-aliasing a *builtin* specifically (`from builtins import eval as go`)
    — the alias table only tracks names bound via `import`/`from import`.
None of these are resolved here; closing them properly is closer to
data-flow analysis than a lightweight AST walk, which is a different scan
than this one, not a bug in this one.
"""
from __future__ import annotations

import ast
import dataclasses

# Superset of stores/promote_check.py's _NET — not imported from it, since
# the_forge stays import-pure (D13) and doesn't reach into safe-app-store
# internals. Kept in sync by hand; if that drifts, it drifts in the
# direction of over-flagging, not under-flagging. Widened 2026-08-01 (audit)
# to add the network-adjacent stdlib modules the original list missed.
_NET_MODULES = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
                "websockets", "urllib3", "ftplib", "smtplib", "xmlrpc", "asyncio",
                "webbrowser"}

# Modules that grant arbitrary native code execution, code execution via
# deserialization, or process/interpreter control this scan otherwise can't
# see into. Same treatment as _NET_MODULES: flagged on import, anywhere.
_NATIVE_OR_DYNAMIC_RISK_MODULES = {"ctypes", "pickle", "marshal", "shelve",
                                    "pty", "runpy", "multiprocessing"}

_PROCESS_EXEC_ATTRS = {"system", "popen", "execl", "execle", "execlp", "execlpe",
                        "execv", "execve", "execvp", "execvpe", "spawnl", "spawnle",
                        "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
                        "fork", "forkpty", "posix_spawn", "posix_spawnp"}
_DYNAMIC_EXEC_NAMES = {"eval", "exec", "compile"}
_DYNAMIC_IMPORT_NAMES = {"__import__", "import_module"}


@dataclasses.dataclass(frozen=True)
class Finding:
    rule: str  # "network_call" | "process_exec" | "dynamic_exec" | "dynamic_import"
    #           | "native_or_dynamic_risk" | "unscanned_executable"
    line: int
    col: int
    detail: str


class ScanError(Exception):
    """The source couldn't even be parsed — refused before it's scanned for
    anything else. A build that can't produce parseable Python has nothing
    here to evaluate honestly."""


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def _call_name_from_expr(expr: ast.expr) -> tuple[str | None, str | None]:
    """Returns (owner, attr) for `owner.attr`, or (None, name) for a bare
    `name` — works on any expression, so it covers both a `Call` node's
    `.func` (something being called) and an assignment's right-hand side
    (something being aliased, not yet called)."""
    if isinstance(expr, ast.Name):
        return None, expr.id
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        return expr.value.id, expr.attr
    return None, None


def _call_name(node: ast.Call) -> tuple[str | None, str | None]:
    """Returns (owner, attr) for `owner.attr(...)`, or (None, name) for a
    bare `name(...)`."""
    return _call_name_from_expr(node.func)


def _collect_aliases(tree: ast.AST) -> dict[str, str]:
    """Map a bound name to what it actually refers to, so `import os as o;
    o.system(...)`, `from os import system as go; go(...)`, and
    `run = os.system; run(...)` all resolve back to `os.system` the same as
    the unaliased spelling would. Without this, the alias IS the evasion —
    a scan that only recognizes `os.system(...)` literally is trivial to
    defeat with one line."""
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
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            owner, attr = _call_name_from_expr(node.value)
            if owner is not None and attr is not None:
                aliases[node.targets[0].id] = f"{aliases.get(owner, owner)}.{attr}"
            elif owner is None and attr is not None:
                aliases[node.targets[0].id] = aliases.get(attr, attr)
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
                elif root in _NATIVE_OR_DYNAMIC_RISK_MODULES:
                    findings.append(Finding("native_or_dynamic_risk", node.lineno, node.col_offset,
                                             f"import of {root!r}"))
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
    is Python (case-insensitive `.py`, so `app.PY` doesn't slip past a
    scan that only checked the lowercase spelling). Returns
    `{dest_path: findings}` for entries with at least one finding — a
    clean entry is simply absent, not present with an empty list, so a
    caller checking `if scan_plan(plan.entries):` gets a plan-is-clean
    signal for free.

    A `FileWrite` marked `executable=True` whose content this scan can't
    examine at all (not Python) is flagged `unscanned_executable`
    unconditionally — pairing "we can't check this" with "and it's meant to
    run" is exactly the combination a floor-not-proof scan can't wave
    through silently. A non-executable non-Python `FileWrite` is still
    skipped, not flagged: this scan genuinely has nothing to say about a
    static asset. `McpCall` entries are skipped for the same reason."""
    from .plan import FileWrite  # local import: keeps plan.py free of a scan.py dependency

    results: dict[str, list[Finding]] = {}
    for entry in entries:
        if not isinstance(entry, FileWrite):
            continue
        if entry.dest_path.lower().endswith(".py"):
            found = scan_source(entry.content, filename=entry.dest_path)
        elif entry.executable:
            found = [Finding("unscanned_executable", 0, 0,
                              f"{entry.dest_path!r} is executable but not Python — this scan cannot examine it")]
        else:
            found = []
        if found:
            results[entry.dest_path] = found
    return results
