"""The chokepoint (I-16), package-wide — no module here may reach a payload.

The engine holds I-16 with an AST scan that lets only the gate (`keep/rungs`) and
the store (`keep/record`) touch a `Classified.payload`, and makes the reach a build
failure anywhere else. That scan walks the *engine* package (its `PKG` is
`homestead/homestead`) and never this app — so homestead-health needs its own, and
this is it.

**Why one package-wide scan, not a per-module one.** The roster's first cut carried
a per-module check that matched the literal attribute spelling `.payload` and would
have missed `getattr(record, "payload")`, `vars(record)["payload"]`, and
`record.__dict__["payload"]` — the exact enforcement-theatre shape the engine's own
chokepoint history warns about (a scanner that matches a spelling, not the property).
A single strong scan over the whole package is harder to let rot than N weak copies,
and it covers modules that have no scan of their own (`school_form`, `due`).

**Why the rule is "none, anywhere."** homestead-health has no gate and no store —
every module in it is *consumer* code that must receive content already scored, as
`Served.value` from `serve()`/`serve_all()` or `AmbientRow.text` from
`ambient_rows()`. None of them has any business reaching a raw payload, by any
spelling. A future one-line `history.payload` or `getattr(name, "payload")` ships
**red** here.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "homestead_health"


def _modules() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}".lstrip(".")
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _slice_constant(node: ast.Subscript) -> object:
    # py39+: the slice is the expression directly (no ast.Index wrapper).
    sl = node.slice
    if isinstance(sl, ast.Constant):
        return sl.value
    return None


def _payload_reaches(tree: ast.AST) -> list[tuple[int, str]]:
    """Every construct in this tree that reaches a `.payload`, by any spelling."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # x.payload
        if isinstance(node, ast.Attribute) and node.attr == "payload":
            hits.append((node.lineno, ".payload"))
        # getattr(x, "payload"[, ...])  — the reflection bypass a name scan misses
        elif isinstance(node, ast.Call) and _dotted(node.func).rsplit(".", 1)[-1] == "getattr":
            for arg in node.args[1:2]:
                if isinstance(arg, ast.Constant) and arg.value == "payload":
                    hits.append((node.lineno, 'getattr(_, "payload")'))
        # x.__dict__["payload"] / vars(x)["payload"] — same reach through the dict
        elif isinstance(node, ast.Subscript) and _slice_constant(node) == "payload":
            base = node.value
            reached_via_dict = (
                isinstance(base, ast.Attribute) and base.attr == "__dict__"
            ) or (
                isinstance(base, ast.Call)
                and _dotted(base.func).rsplit(".", 1)[-1] == "vars"
            )
            if reached_via_dict:
                hits.append((node.lineno, '__dict__/vars["payload"]'))
    return hits


def test_no_module_in_the_package_reaches_a_payload():
    """I-16 for homestead-health: the gate and the store are the engine's, one
    dependency over, and this app has neither — so nothing in it may reach a raw
    payload. Content arrives already scored, through serve()."""
    offenders = []
    for mod in _modules():
        for lineno, how in _payload_reaches(ast.parse(mod.read_text(encoding="utf-8"))):
            offenders.append(f"{mod.relative_to(PKG.parent)}:{lineno} {how}")
    assert not offenders, (
        "a surface reached a payload — content must arrive as serve()'s scored "
        f"value, never a raw payload (I-16). Found: {offenders}"
    )


def test_the_scan_catches_every_bypass_spelling(tmp_path):
    """The scan itself, held honest. All four reaches — the attribute, getattr, and
    both dict spellings — must be caught, so a weakened future copy that drops one
    is failed by its own suite (the engine's regression discipline, on the reach
    this app must forbid)."""
    probe = tmp_path / "bypass.py"
    probe.write_text(
        "def a(r): return r.payload\n"
        "def b(r): return getattr(r, 'payload')\n"
        "def c(r): return r.__dict__['payload']\n"
        "def d(r): return vars(r)['payload']\n"
    )
    hows = {how for _, how in _payload_reaches(ast.parse(probe.read_text()))}
    assert hows == {".payload", 'getattr(_, "payload")', '__dict__/vars["payload"]'}, (
        f"the scan missed a bypass spelling; caught only {hows}"
    )
