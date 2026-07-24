#!/usr/bin/env python3
"""stores/promote_check.py — the promotion gate.

Turns the promotion bar in stores/README.md from prose into a fail-closed check.
A build in the shared `apps/` playground is a *proposal*; promotion is the
*ratification* that lifts it into a standing SAFE app. On a shared surface that
crossing is a trust boundary, so this gate refuses anything that does not clear
every criterion — and refuses, too, anything it cannot verify (fail-closed).

    python stores/promote_check.py <candidate-dir> [--json]

The candidate dir must contain a `promotion.json` attestation:

    {
      "app_id":        "nestor",
      "author":        "sean",            # who built it (enrolls)
      "verified_by":   "loki",            # who promotes it — MUST differ (§0.2)
      "repo_url":      "https://github.com/.../Nestor",   # its OWN repo, not the store
      "host":          "willow-2.0",      # what it was extracted from (inversion check)
      "core_module":   "nestor",          # the import-pure core package to scan
      "semantic_seam": "nestor.matcher:Matcher",   # module:symbol of the search seam
      "host_repointed": true              # the host now consumes it as a dependency
    }

Two kinds of gate:
  [M] mechanical — this script verifies it directly (tests, AST scans, symbols).
  [A] attested   — a human/witness asserts it in promotion.json; the script
                   enforces the assertion's *shape* and fails closed if absent.

Stdlib only. Nestor and Jeles are the worked standard: run this against either
and it should pass.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

# import-time network modules — a promoted core must be network-free at import
# (the same guarantee UTETY's test_no_egress and Nestor/Jeles enforce). NOTE:
# asyncio is deliberately NOT here — async I/O is not network egress by itself.
_NET = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
        "websockets", "urllib3"}

Result = tuple[str, bool, str]  # (gate, ok, detail)


def _load_attestation(cand: Path) -> dict | None:
    f = cand / "promotion.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception as e:  # malformed attestation is no attestation
        return {"_error": str(e)}


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "test" not in p.name.lower()]


def _toplevel_imports(path: Path) -> set[str]:
    """Root package names imported at module top level (not inside functions)."""
    names: set[str] = set()
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return names
    for node in tree.body:  # top level only — a lazy import inside a function is fine
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _defines_symbol(mod_file: Path, symbol: str) -> bool:
    try:
        tree = ast.parse(mod_file.read_text())
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name == symbol:
            return True
        if isinstance(node, ast.Assign):  # module-level constant seam
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == symbol:
                    return True
    return False


def check(cand: Path) -> list[Result]:
    out: list[Result] = []
    att = _load_attestation(cand)

    # ── attestation must exist and parse ──────────────────────────────────────
    if att is None:
        return [("attestation", False, "no promotion.json — cannot promote (fail-closed)")]
    if "_error" in att:
        return [("attestation", False, f"promotion.json is malformed: {att['_error']}")]

    author = att.get("author", "")
    verifier = att.get("verified_by", "")
    core = att.get("core_module", "")
    host = att.get("host", "")
    seam = att.get("semantic_seam", "")

    # ── [M] witnessed: proposing and ratifying are different hands (§0.2) ──────
    ok = bool(author) and bool(verifier) and author != verifier
    out.append(("witnessed [M]", ok,
                f"author={author!r} verified_by={verifier!r}"
                + ("" if ok else " — verifier must be set and differ from author")))

    # ── [A] own repo: an extraction, not still in the store monorepo ──────────
    repo = att.get("repo_url", "")
    ok = bool(repo) and "safe-app-store" not in repo
    out.append(("own_repo [A]", ok,
                repo or "repo_url missing" if ok else f"repo_url={repo!r} (must be its own repo)"))

    # ── [A] host repointed: the host now consumes it ──────────────────────────
    ok = att.get("host_repointed") is True
    out.append(("host_repointed [A]", ok,
                "attested" if ok else "host_repointed must be asserted true"))

    # ── [M] manifest present and shaped ───────────────────────────────────────
    # MCP-shaped promotions carry safe-app-manifest.json; library-clean ones
    # (Jeles, Nestor) carry pyproject.toml as their package manifest. The bar is
    # "MCP-shaped OR library-clean" — accept either, reject neither-present.
    saf, pyproj = cand / "safe-app-manifest.json", cand / "pyproject.toml"
    if saf.exists():
        try:
            m = json.loads(saf.read_text())
            miss = {"app_id", "permissions", "privacy_tier"} - set(m)
            out.append(("manifest [M]", not miss,
                        "safe-app-manifest.json" + (f" — missing {sorted(miss)}" if miss else " ok")))
        except Exception as e:
            out.append(("manifest [M]", False, f"safe-app-manifest.json is not valid JSON: {e}"))
    elif pyproj.exists():
        txt = pyproj.read_text()
        ok = "[project]" in txt and "name" in txt
        out.append(("manifest [M]", ok,
                    "pyproject.toml (library-clean)" if ok else "pyproject.toml missing [project].name"))
    else:
        out.append(("manifest [M]", False, "no safe-app-manifest.json or pyproject.toml"))

    # ── [M] tests green: a tests/ dir that actually passes ────────────────────
    tdir = cand / "tests"
    if not tdir.is_dir():
        out.append(("tests_green [M]", False, "no tests/ directory"))
    else:
        cmd = [sys.executable, "-m", "pytest", "-q"]
        try:
            r = subprocess.run(cmd, cwd=cand, capture_output=True, text=True, timeout=300)
            if r.returncode == 5 or "No module named pytest" in (r.stderr or ""):
                r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                                   cwd=cand, capture_output=True, text=True, timeout=300)
            ok = r.returncode == 0
            tail = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
            out.append(("tests_green [M]", ok, tail[0][:80] if ok else f"exit {r.returncode}: {tail[0][:80]}"))
        except Exception as e:
            out.append(("tests_green [M]", False, f"could not run tests (fail-closed): {e}"))

    # ── core-based mechanical checks ──────────────────────────────────────────
    core_dir = cand / core if core else None
    if not core or not (core_dir and core_dir.is_dir()):
        for g in ("import_pure_core [M]", "inversion [M]", "semantic_seam [M]"):
            out.append((g, False, f"core_module {core!r} not found under candidate"))
        return out

    # [M] import-pure core: no network module imported at import time. The bar
    # scopes this to the *core*, not the whole package — a package may ship an
    # impure adapter (e.g. Jeles' willow_mcp_client) as long as the core stays
    # pure. `pure_core` in the attestation names it; default is the whole core.
    pure = att.get("pure_core", core)
    pfile = cand / (pure.replace(".", "/") + ".py")
    pdir = cand / pure.replace(".", "/")
    pure_files = [pfile] if pfile.exists() else (_py_files(pdir) if pdir.is_dir() else [])
    net_hits = {p.name: sorted(_NET & _toplevel_imports(p)) for p in pure_files}
    net_hits = {k: v for k, v in net_hits.items() if v}
    out.append(("import_pure_core [M]", bool(pure_files) and not net_hits,
                f"{pure}: network-free at import" if (pure_files and not net_hits)
                else (f"network imports: {net_hits}" if pure_files else f"pure_core {pure!r} not found")))

    # [M] inversion: the core must NOT import its host
    if host:
        host_root = host.split("-")[0].replace("/", ".").split(".")[0]
        hits = [p.name for p in _py_files(core_dir) if host_root in _toplevel_imports(p)]
        out.append(("inversion [M]", not hits,
                    "host not imported (seams injected)" if not hits else f"imports host {host_root!r}: {hits}"))
    else:
        out.append(("inversion [M]", False, "host not declared — cannot verify seam inversion"))

    # [M] semantic-search seam: the declared module:symbol is defined
    if ":" in seam:
        mod, sym = seam.split(":", 1)
        mod_file = cand / (mod.replace(".", "/") + ".py")
        if not mod_file.exists():
            mod_file = cand / mod.replace(".", "/") / "__init__.py"
        ok = mod_file.exists() and _defines_symbol(mod_file, sym)
        out.append(("semantic_seam [M]", ok,
                    f"{seam} defined" if ok else f"{seam} not resolvable"))
    else:
        out.append(("semantic_seam [M]", False, "semantic_seam not declared as module:symbol"))

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Promotion gate for the SAFE store.")
    ap.add_argument("candidate", help="path to the extracted candidate app")
    ap.add_argument("--json", action="store_true", help="machine-readable verdict")
    args = ap.parse_args(argv)

    cand = Path(args.candidate).resolve()
    results = check(cand)
    promoted = all(ok for _, ok, _ in results)  # fail-closed: any gate fails → denied

    if args.json:
        print(json.dumps({"candidate": str(cand), "promoted": promoted,
                          "gates": [{"gate": g, "ok": ok, "detail": d} for g, ok, d in results]}, indent=2))
    else:
        print(f"\npromotion candidate: {cand.name}")
        for g, ok, d in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {g:22} {d}")
        print(f"\n  verdict: {'PROMOTED' if promoted else 'NOT PROMOTED (fail-closed)'}\n")
    return 0 if promoted else 1


if __name__ == "__main__":
    raise SystemExit(main())
