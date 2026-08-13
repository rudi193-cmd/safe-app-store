#!/usr/bin/env python3
"""stores/promote_check.py — the promotion gate.

Turns the promotion bar in stores/README.md from prose into a fail-closed check.
A build in the shared `apps/` playground is a *proposal*; promotion is the
*ratification* that lifts it into a standing SAFE app. On a shared surface that
crossing is a trust boundary, so this gate refuses anything that does not clear
every criterion — and refuses, too, anything it cannot verify (fail-closed).

    python stores/promote_check.py <candidate-dir> [--json] [--record]

The candidate dir must contain a `promotion.json` attestation:

    {
      "app_id":        "nestor",
      "author":        "sean",            # who built it (enrolls)
      "verified_by":   "loki",            # who promotes it — MUST differ (§0.2)
      "repo_url":      "https://github.com/.../Nestor",   # its OWN repo, not the store
      "host":          "willow-2.0",      # what it was extracted from (inversion check)
      "core_module":   "nestor",          # the import-pure core package to scan
      "semantic_seam": "nestor.matcher:Matcher",   # module:symbol of the search seam
      "host_repointed": true,             # the host now consumes it as a dependency
      "major": "python",                  # optional; which store --record files under
      "trust": {                          # OPTIONAL — upgrades `witnessed` to a seal
        "custody":     "trust/custody.jsonl",
        "checkpoint":  "trust/checkpoint.json",
        "author_id":   "agent:vishwakarma",
        "verifier_id": "loki"             # == verified_by; key resolved from NESTOR_KEYRING
      }
    }

Two kinds of gate:
  [M] mechanical — this script verifies it directly (tests, AST scans, symbols).
  [A] attested   — a human/witness asserts it in promotion.json; the script
                   enforces the assertion's *shape* and fails closed if absent.

The `witnessed [M]` gate has two tiers (see _witnessed()). Its FLOOR is the
string check — verified_by set and ≠ author — and that is all a promotion needs
by default. When the attestation carries a `trust` block it CLAIMS a
cryptographic ratification, and the gate then demands `forge.trust.witnessed()`
pass (the author's provisional seal in a hash-verified custody ledger, covered by
a checkpoint signed by the verifier's keyring key). A claimed seal that cannot be
verified here FAILS — it never falls back to the floor. The seam is imported
lazily, so a promotion with no `trust` block keeps this script stdlib-only.

`--record` is the store refit's P2 (docs/store_refit_plan.md): a passing run
writes stores/{major}/promoted/<app_id>.json so the passage leaves a mark
instead of scrolling past in a terminal. It is fail-closed on both edges — any
failed gate writes nothing at all, and `verified_by == author` refuses to write
even if every gate somehow passed, which is what turns §0.2 (proposing and
ratifying never rest in the same hand) from a thing a person remembers into a
mechanism.

Stdlib only. Nestor and Jeles are the worked standard: run this against either
and it should pass.

Fleet placement: this gate travels with the stores law into **forge-play** when
that face stands up. Until then it lives here — see stores/README.md
"Fleet placement — still here on purpose".
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORES = REPO / "stores"

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


_DYN_IMPORT = {"__import__", "import_module"}


def _toplevel_dynamic_net(path: Path) -> set[str]:
    """Network root packages pulled in *dynamically at import time* via
    ``__import__("socket")`` / ``importlib.import_module("socket")`` in a
    top-level statement. Static top-level imports are covered by
    :func:`_toplevel_imports`; this closes the dynamic-import evasion the
    static scan misses. Calls inside a function/class body are lazy (run later,
    not at import) and are deliberately not flagged."""
    hits: set[str] = set()
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return hits
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # a dynamic import inside a callable runs later, not at import
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            fname = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if fname in _DYN_IMPORT and n.args and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str):
                hits.add(n.args[0].value.split(".")[0])
    return {h for h in hits if h in _NET}


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


def _vault_leak_gate(cand: Path) -> Result:
    """Run the store's own vault-leak linter on the candidate. A promoted app
    must not persist user DATA to a fixed/home path (installer design D8) — the
    gate had this lint available (`tools/vault_leak_lint.py`) but never called
    it. Wire it in-process; fail closed if it can't run."""
    lint = REPO / "tools" / "vault_leak_lint.py"
    if not lint.exists():
        return ("vault_leak [M]", False, "tools/vault_leak_lint.py not found (fail-closed)")
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("_vault_leak_lint", lint)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.lint_app(cand)
    except Exception as e:
        return ("vault_leak [M]", False, f"could not run vault-leak lint (fail-closed): {e}")
    leaks = res.get("leaks") or []
    if res.get("verdict") != "FAIL":
        return ("vault_leak [M]", True, f"no data leaks ({res.get('verdict')})")
    detail = "; ".join(f"{f['file']}:{f['line']} {f['reason']}" for f in leaks[:3])
    return ("vault_leak [M]", False, f"user data at fixed path: {detail}")


def _within(cand: Path, rel: str) -> Path | None:
    """Resolve an attestation-supplied, candidate-relative path — or None if it
    is empty or escapes the candidate dir. A `trust` block path is human-authored
    and used to open a file, so it gets the same treatment as `app_id` on the
    write path (`_APP_ID_PATTERN`): an external field that addresses the
    filesystem is not trusted to point outside the thing being promoted."""
    if not rel:
        return None
    try:
        p = (cand / rel).resolve()
        p.relative_to(cand.resolve())
    except (ValueError, OSError):
        return None
    return p


def _witnessed(cand: Path, att: dict) -> Result:
    """§0.2 — proposing and ratifying never rest in the same hand.

    FLOOR (stdlib, always runs): `verified_by` must be set and differ from
    `author`. That is the baseline every promotion clears, and it is exactly the
    hollow check this fleet already got burned by — a name typed into a JSON
    field is not a ratification.

    SEAL (opt-in, fail-closed): when the attestation carries a `trust` block the
    name is no longer enough. The promotion now CLAIMS a cryptographic
    ratification, and a claimed seal this gate cannot verify is a FAILURE, never a
    silent fallback to the floor. The claim is checked through
    `forge.trust.witnessed()` — the forge's own promotion-trust seam, reused
    wholesale (rule 11): the author's provisional seal must sit in a hash-verified
    custody ledger, and a checkpoint signed by the verifier's key must cover it.
    The verifier's PUBLIC key is resolved from the fleet keyring (`NESTOR_KEYRING`)
    by `verifier_id` — never from the candidate — so identity is anchored to the
    gate, not to whatever key material a candidate chose to ship.

        "trust": {
          "custody":     "trust/custody.jsonl",   # candidate-relative; loaded + hash-verified
          "checkpoint":  "trust/checkpoint.json",  # the ratify() checkpoint event
          "author_id":   "agent:vishwakarma",      # who provisionally sealed (actor in the ledger)
          "verifier_id": "rudi193"                 # whose key ratified; MUST equal verified_by
        }

    The whole seal path is lazily imported: `promote_check` stays stdlib-only, and
    a promotion without a `trust` block never touches the cloud seam at all.
    """
    author = att.get("author", "")
    verifier = att.get("verified_by", "")
    string_ok = bool(author) and bool(verifier) and author != verifier
    trust = att.get("trust")

    if not trust:
        return ("witnessed [M]", string_ok,
                f"author={author!r} verified_by={verifier!r} (attested — no seal declared)"
                + ("" if string_ok else " — verifier must be set and differ from author"))

    # A seal is CLAIMED. Every branch from here is fail-closed: a claimed-but-
    # unverifiable ratification denies the promotion, it does not fall through.
    if not isinstance(trust, dict):
        return ("witnessed [M]", False, "trust block is not an object (fail-closed)")
    if not string_ok:
        return ("witnessed [M]", False,
                f"seal declared but the §0.2 floor fails: author={author!r} verified_by={verifier!r}")

    verifier_id = trust.get("verifier_id", "")
    author_id = trust.get("author_id", "")
    if verifier_id != verifier:
        return ("witnessed [M]", False,
                f"trust.verifier_id={verifier_id!r} must equal verified_by={verifier!r} "
                f"(the hand named in the seal is the hand recorded as verifier)")
    if not author_id:
        return ("witnessed [M]", False, "trust.author_id missing — who provisionally sealed?")

    cpath = _within(cand, trust.get("custody", ""))
    kpath = _within(cand, trust.get("checkpoint", ""))
    if cpath is None or kpath is None:
        return ("witnessed [M]", False,
                "trust custody/checkpoint path missing or escapes the candidate (fail-closed)")

    try:  # LAZY — the gate is stdlib-only until a promotion opts into the seal
        from willow_gate.custody import ChainError, CustodyLedger
        from forge.trust import witnessed as trust_witnessed
        from nestor.keyring import get_keyring
        from nestor.signing import _verifies_with
    except ImportError as e:
        return ("witnessed [M]", False,
                f"seal declared but the cloud seam (forge.trust + willow-gate + nestor) "
                f"is not installed at this end (fail-closed): {e}")

    ring = get_keyring()
    if ring is None:
        return ("witnessed [M]", False,
                "seal declared but no fleet keyring is configured — set NESTOR_KEYRING (fail-closed)")
    entry = ring.verifying_entry(verifier_id)
    if entry is None:
        return ("witnessed [M]", False,
                f"verifier {verifier_id!r} is not trusted in the keyring "
                f"(unknown, revoked-compromised) — fail-closed")

    class _KeyringVerifier:
        """Verify-only signer over the keyring's PUBLIC key — `witnessed()` →
        `verify_checkpoint()` only ever calls `.verify()`, never `.sign()`."""
        def verify(self, data: bytes, sig: str) -> bool:
            return _verifies_with(entry.kind, entry.key, data, sig)

    try:
        led = CustodyLedger.load(str(cpath))
    except (ChainError, OSError, ValueError) as e:
        return ("witnessed [M]", False, f"custody ledger failed to load/verify: {e}")
    try:
        checkpoint_event = json.loads(kpath.read_text())
    except Exception as e:
        return ("witnessed [M]", False, f"checkpoint event unreadable: {e}")

    app_id = att.get("app_id") or cand.name
    w = trust_witnessed(led, checkpoint_event, _KeyringVerifier(),
                        author_id=author_id, verifier_id=verifier_id, app_id=app_id)
    return ("witnessed [M]", bool(w.ok),
            f"sealed: {w.reason}" if w.ok else f"seal rejected: {w.reason}")


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
    # Floor is the string check; an opt-in `trust` block upgrades it to a
    # verified cryptographic seal (fail-closed) — see _witnessed().
    out.append(_witnessed(cand, att))

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

    # ── [M] no user-data leak to a fixed path (installer design D8) ────────────
    out.append(_vault_leak_gate(cand))

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
    net_hits = {p.name: sorted((_NET & _toplevel_imports(p)) | _toplevel_dynamic_net(p))
                for p in pure_files}
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


# ── P2: promotion leaves a record ─────────────────────────────────────────────

# app_id comes straight from promotion.json — human-authored, but external to
# this script, and it is used to build a filesystem path. A value like
# "../../../tmp/evil" would resolve outside stores/ entirely if trusted as-is.
# No "/" or "\" in the allowed set is what actually closes this: without a
# separator there is no way to address a parent directory at all, whatever
# dots or hyphens appear in the rest of the string.
_APP_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _gates_payload(results: list[Result]) -> list[dict]:
    """The shape both --json's payload and a promotion record use for the gate
    list, in one place so the two can't quietly drift apart."""
    return [{"gate": g, "ok": ok, "detail": d} for g, ok, d in results]


def _real_majors(stores_root: Path) -> set[str]:
    """A real major is a stores/<name>/ with *both* tiers on disk. Discovered,
    never hardcoded — the same rule tools/catalog_lint.py's `_real_majors()`
    uses, and for the same reason it was changed to discovery in P0 review: a
    hardcoded list silently stops being true the day a store is added (P1 added
    `browser`, which no hardcoded list would have known about)."""
    if not stores_root.is_dir():
        return set()
    return {d.name for d in stores_root.iterdir()
            if d.is_dir() and (d / "stored").is_dir() and (d / "promoted").is_dir()}


def resolve_major(att: dict, stores_root: Path) -> tuple[str | None, str]:
    """Which store does a promotion record file under? Returns (major, why).

    P1 established the majors as *crafts* — python, node, rust, go, cpp,
    obsidian, browser — and a record may name only a store that actually
    exists. Two ways to arrive at one, in order:

    1. **The attestation says so.** `major` in promotion.json is authoritative
       when present: the hands doing the promoting know the craft better than
       an inference does. It is still checked against the real stores, so a
       typo fails closed rather than inventing an eighth major.

    2. **Otherwise: python, and not as a guess.** Every gate in `check()` that
       a candidate can *pass* is Python-shaped. `core_module` is resolved as a
       package directory and scanned with `ast.parse` over `*.py`;
       `import_pure_core` measures Python top-level imports (`_NET` is a set of
       Python stdlib/PyPI names); `semantic_seam` resolves `module:symbol` to a
       `.py` file or a package `__init__.py`; `tests_green` runs pytest and
       falls back to unittest. A Node or Rust candidate cannot reach a PASS
       through this script at all — it fails core resolution, the pure-core
       scan and the seam check. So on *this* gate, PASS implies python.

    Recording that as a default rather than hardcoding it is the point: the
    inference is a property of the current gate, not of promotion. When
    promote_check grows a non-Python path, candidates declare `major` and this
    default stops being load-bearing — and until then, an out-of-band claim
    still cannot invent a store that isn't there.
    """
    majors = _real_majors(stores_root)
    declared = att.get("major")
    if declared:
        if declared in majors:
            return declared, f"major {declared!r} declared in promotion.json"
        return None, (f"major {declared!r} is not a real store "
                      f"(have: {sorted(majors) or 'none'}) — fail-closed")
    if "python" in majors:
        return "python", ("major not declared; defaulting to 'python' — every "
                          "gate this candidate passed is Python-shaped")
    return None, "major not declared and no 'python' store exists — fail-closed"


def record_promotion(cand: Path, results: list[Result],
                     stores_root: Path | None = None) -> tuple[Path | None, str]:
    """Write stores/{major}/promoted/<app_id>.json for a passing candidate.

    Returns (path_written, reason). `path_written` is None when nothing was
    written, and `reason` says why — the caller turns that into an exit code.

    Every refusal happens *before* the first filesystem write, so a refused
    record leaves `stores/` byte-identical: no partial file, no directory
    created and then abandoned. The refusals, in order:

    * any gate failed — the verdict is the record, and a NOT PROMOTED verdict
      is not a promotion record;
    * `verified_by == author` (or either is empty) — §0.2, enforced here
      *independently* of the `witnessed [M]` gate on purpose. The writer does
      not inherit its trust from the gate list it was handed: if that gate is
      ever reordered, renamed, or made skippable, the record is still the thing
      that cannot be minted by one hand;
    * the major does not resolve to a real store (see `resolve_major`);
    * `app_id` is not a plain identifier (see `_APP_ID_PATTERN`) — an attested
      field is still an external input, and this is the one field on the
      write path nothing else checks the shape of;
    * a record already exists — a promoted record is a witnessed decision, and
      silently overwriting one destroys the evidence that it was ever made
      differently. Re-minting is a deliberate act: remove the old record first.
    """
    stores_root = STORES if stores_root is None else stores_root

    if not results or not all(ok for _, ok, _ in results):
        return None, "candidate is NOT PROMOTED — no record written (fail-closed)"

    att = _load_attestation(cand) or {}
    author, verifier = att.get("author", ""), att.get("verified_by", "")
    if not author or not verifier or author == verifier:
        return None, (f"refusing to record: verified_by={verifier!r} must be set and "
                      f"differ from author={author!r} — proposing and ratifying never "
                      f"rest in the same hand (§0.2)")

    app_id = att.get("app_id") or cand.name
    major, why = resolve_major(att, stores_root)
    if major is None:
        return None, f"refusing to record: {why}"

    promoted_dir = stores_root / major / "promoted"
    if not _APP_ID_PATTERN.match(app_id):
        return None, (f"refusing to record: app_id {app_id!r} is not a plain "
                      f"identifier (fail-closed) — a path component in an "
                      f"attested field is not verified anywhere else on this path")
    out = promoted_dir / f"{app_id}.json"
    if out.exists():
        return None, (f"refusing to record: {out} already exists — a promotion record "
                      f"is not overwritten; remove it deliberately to re-mint")

    record = {
        "app_id": app_id,
        "verdict": "PROMOTED",
        "major": major,
        "major_reason": why,
        "repo_url": att.get("repo_url", ""),
        "author": author,
        "verified_by": verifier,
        # Both hands, not just the witness: a record that names only the
        # verifier cannot be checked against §0.2 after the fact.
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate": cand.name,
        # Every gate check() emitted, individually — not a count and not a
        # summary. docs/store_refit_plan.md says "the eight gate results";
        # check() emits nine today, because the B13 audit added vault_leak
        # after #88. Storing what the gate actually returned is what keeps this
        # record from carrying a stale invariant count the way a README does.
        "gates": _gates_payload(results),
    }
    out.write_text(json.dumps(record, indent=2) + "\n")
    return out, f"recorded at {out}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Promotion gate for the SAFE store.")
    ap.add_argument("candidate", help="path to the extracted candidate app")
    ap.add_argument("--json", action="store_true", help="machine-readable verdict")
    ap.add_argument("--record", action="store_true",
                    help="on a PASS, write stores/{major}/promoted/<app_id>.json (P2)")
    args = ap.parse_args(argv)

    cand = Path(args.candidate).resolve()
    results = check(cand)
    promoted = all(ok for _, ok, _ in results)  # fail-closed: any gate fails → denied

    written: Path | None = None
    reason = ""
    if args.record:
        written, reason = record_promotion(cand, results)

    if args.json:
        payload = {"candidate": str(cand), "promoted": promoted,
                   "gates": _gates_payload(results)}
        if args.record:
            payload["record"] = {"written": str(written) if written else None,
                                 "reason": reason}
        print(json.dumps(payload, indent=2))
    else:
        print(f"\npromotion candidate: {cand.name}")
        for g, ok, d in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {g:22} {d}")
        print(f"\n  verdict: {'PROMOTED' if promoted else 'NOT PROMOTED (fail-closed)'}")
        if args.record:
            print(f"  record:  {reason}")
        print()

    # --record makes the write part of the verdict: a promotion that could not
    # leave its mark is not reported as a success, or the mark stops meaning
    # anything. Without --record, behaviour is exactly as before.
    if args.record:
        return 0 if (promoted and written is not None) else 1
    return 0 if promoted else 1


if __name__ == "__main__":
    raise SystemExit(main())
