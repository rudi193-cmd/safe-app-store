#!/usr/bin/env python3
"""
vault_leak_lint.py — data-vs-config vault-leak linter (SAFE installer design D8/D8.1)

Scans SAFE apps for persistence paths and classifies each fixed/home-rooted one:

  LEAK   — user DATA at a fixed path (DBs, case files, deposits, identity).
           These must derive from the vault root instead. → app FAILs.
  config — config/cache in home/XDG (~/.cache, ~/.config, ~/.<app>/config…).
           Allowed; not a leak.
  core   — willow-core discovery paths (~/github/willow-*). Fragility, not a
           data leak. → WARN.
  vault  — path derives from WILLOW_STORE_ROOT / WILLOW_HOME. Good.

Verdict per app:
  FAIL  — one or more DATA leaks.
  WARN  — only core-discovery / unknown fixed paths.
  PASS  — only config/cache/vault-routed, or no local persistence.

The rule (D8): an app is vault-clean only when every *data* path derives from
the vault root. The refinement (D8.1): config/cache in home is fine — classify,
don't cry wolf.

Usage:
  tools/vault_leak_lint.py                 # scan apps/* under the repo
  tools/vault_leak_lint.py --app law-gazelle
  tools/vault_leak_lint.py --path apps/ask-jeles
  tools/vault_leak_lint.py --json
  tools/vault_leak_lint.py --strict        # exit 1 if any FAIL (CI / receipt gate)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIR_PARTS = {"tests", "test", "_archived", ".venv", "venv", "node_modules",
                  "__pycache__", ".git", "web", "functions"}

# ── path-expression extraction ───────────────────────────────────────────────
# Each returns a reconstructed home-rooted path string like "~/.willow/apps/…".

_SEG = re.compile(r'/\s*["\']([^"\']+)["\']')

def _extract(line: str) -> list[str]:
    out: list[str] = []
    # Path.home() / "a" / "b" / VAR / "c"  -> ~/a/b/c   (var segments dropped)
    for m in re.finditer(r'Path\.home\(\)((?:\s*/\s*[^\n#]+?)(?=$|[#\n]))', line):
        segs = _SEG.findall(m.group(1))
        if segs:
            out.append("~/" + "/".join(segs))
    # expanduser("~/…")  and  Path("~/…").expanduser()
    for m in re.finditer(r'expanduser\(\s*f?["\']([^"\']+)["\']', line):
        out.append(m.group(1))
    for m in re.finditer(r'Path\(\s*f?["\'](~/[^"\']+)["\']\s*\)\s*\.expanduser', line):
        out.append(m.group(1))
    # bare "~/…" literal
    for m in re.finditer(r'["\'](~/[^"\']+)["\']', line):
        out.append(m.group(1))
    return out

# ── classification (D8.1 rules) ──────────────────────────────────────────────
_DATA_EXT = (".db", ".sqlite", ".sqlite3", ".enc")
_DATA_SEGS = {"cases", "intake", "saves", "deposits", "learning_events",
              "jeles_saves", "jeles_kb_views", "jeles_learning_events",
              "kb_views", "store", "records", "timeline", "ledger", "ledgers"}
_DATA_NAME_HINTS = ("identity", "profile", "persona", "case", "vault", "history")
_CONFIG_FILE = re.compile(r'(config|settings)\.(json|ya?ml|toml|ini|py)$|\.(conf|ini|cfg|env)$')
_CORE = re.compile(r'github|willow-1\.\d|willow-2\.\d|/core\b')

def classify(path: str, line: str) -> tuple[str, str]:
    """Return (category, reason). category in {skip, vault, config, core, leak, unknown}."""
    p = path.strip()
    low = p.lower()
    segs = [s for s in low.replace("~/", "/").split("/") if s]
    base = p.rsplit("/", 1)[-1]

    # bare home (expanduser("~")) — not a persistence path
    if not segs or low in ("~", "~/"):
        return "skip", "bare home"

    if "WILLOW_STORE_ROOT" in line or "WILLOW_HOME" in line:
        return "vault", "derives from vault root env"

    # CONFIG / CACHE — allowed (checked before data heuristics so e.g.
    # ~/.cache/nest-seed is not mistaken for a Nest data store)
    if ".cache" in segs or ".config" in segs:
        return "config", "XDG config/cache"
    if _CONFIG_FILE.search(base):
        return "config", f"config file ({base})"

    # DATA — leaks
    if ".willow" in segs and "apps" in segs:
        return "leak", "per-app data dir under ~/.willow/apps (outside vault)"
    if "desktop" in segs and "nest" in segs:
        return "leak", "Desktop/Nest PII store outside the vault"
    if base == "key.bin" or base.endswith(".key"):
        return "leak", f"crypto key material at fixed path ({base})"
    if low.endswith(_DATA_EXT):
        return "leak", f"data/db file at fixed path ({base})"
    dseg = set(segs) & _DATA_SEGS
    if dseg:
        return "leak", f"data directory ({', '.join(sorted(dseg))}) at fixed path"
    if any(h in low for h in _DATA_NAME_HINTS):
        return "leak", f"user data ({base}) at fixed path"

    # CORE discovery (fragility, not a data leak)
    if _CORE.search(low):
        return "core", "willow-core discovery path (fragility, not data)"

    return "unknown", f"fixed home path, unclassified ({base})"


def lint_app(app_dir: Path) -> dict:
    findings = []
    persists = False
    for py in sorted(app_dir.rglob("*.py")):
        if SKIP_DIR_PARTS & set(py.parts):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if re.search(r'sqlite3\.connect|CREATE TABLE|\.execute\(', text):
            persists = True
        for i, line in enumerate(text.splitlines(), 1):
            if "Path.home()" not in line and "expanduser" not in line and "~/" not in line:
                continue
            for path in _extract(line):
                cat, reason = classify(path, line)
                if cat == "skip":
                    continue
                if cat in ("leak", "core", "unknown"):
                    findings.append({
                        "file": str(py.relative_to(app_dir.parent)),
                        "line": i, "path": path, "category": cat, "reason": reason,
                    })
    leaks = [f for f in findings if f["category"] == "leak"]
    warns = [f for f in findings if f["category"] in ("core", "unknown")]
    verdict = "FAIL" if leaks else ("WARN" if warns else "PASS")
    return {"app": app_dir.name, "verdict": verdict, "leaks": leaks,
            "warns": warns, "persists": persists}


def main() -> int:
    ap = argparse.ArgumentParser(description="Vault-leak linter (data vs config)")
    ap.add_argument("--path", help="scan this dir's apps/* (default: repo root of this script)")
    ap.add_argument("--app", help="scan a single app by name")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any app FAILs")
    args = ap.parse_args()

    repo = Path(args.path) if args.path else Path(__file__).resolve().parent.parent
    apps_dir = repo / "apps" if (repo / "apps").is_dir() else repo
    if args.app:
        targets = [apps_dir / args.app]
    else:
        targets = [d for d in sorted(apps_dir.iterdir()) if d.is_dir() and not d.name.startswith(".")]

    results = [lint_app(d) for d in targets if d.exists()]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        for r in sorted(results, key=lambda r: (order[r["verdict"]], r["app"])):
            mark = {"FAIL": "❌", "WARN": "⚠️ ", "PASS": "✅"}[r["verdict"]]
            extra = "" if r["persists"] or r["leaks"] or r["warns"] else " (no local persistence)"
            print(f"{mark} {r['verdict']:4} {r['app']}{extra}")
            for f in r["leaks"]:
                print(f"      LEAK  {f['file']}:{f['line']}  {f['path']}  — {f['reason']}")
            for f in r["warns"]:
                print(f"      warn  {f['file']}:{f['line']}  {f['path']}  — {f['reason']}")
        n_fail = sum(1 for r in results if r["verdict"] == "FAIL")
        n_warn = sum(1 for r in results if r["verdict"] == "WARN")
        n_pass = sum(1 for r in results if r["verdict"] == "PASS")
        print(f"\n{len(results)} apps: {n_fail} FAIL · {n_warn} WARN · {n_pass} PASS")

    if args.strict and any(r["verdict"] == "FAIL" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
