#!/usr/bin/env python3
# tools/extract_forge_pkg.py — the one-shot extraction that enrolled The Forge
# model side into rudi193-cmd/forge (docs/design/the-forge-promotion.md).
# Re-runnable: "python tools/extract_forge_pkg.py <out-dir>" rebuilds the
# forge/ package from the current stores/ modules. Kept so the extraction is
# auditable and the ratifier can reproduce it, not a mystery diff.
"""Build the `forge` library package from the store-side model-side modules.

Transforms the monorepo spec_from_file_location sibling-loads into real package
imports. Line-based (not one big regex) so arbitrary spec-var names, interleaved
comments, and in-function lazy imports all transform reliably.

Layout produced:
  Forge/
    forge/__init__.py
    forge/model_route.py, model_egress.py         (the impure adapter, top level)
    forge/core/__init__.py, _ids.py, <15 pure modules>   (pure_core = forge.core)
    tests/<converted test files>
    pyproject.toml, promotion.json, README.md
"""
import re, shutil, sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
STORES = _REPO / "stores"
TESTS_SRC = _REPO / "tests"
OUT = Path(sys.argv[1])

CORE = [
    "calibration", "calibration_ledger", "checkpoint", "checkpoint_calibration",
    "checkpoint_engagement", "checkpoint_governance", "checkpoint_memory",
    "checkpoint_nudge", "checkpoint_schedule", "friction_floor", "human_loop",
    "measure_panel", "instrument_callgraph", "instrument_execution", "soil_store",
]
TOP = ["model_route", "model_egress"]
ALL_MODS = set(CORE + TOP)

# module -> the dotted package it lives in (for tests' absolute imports)
PKG_OF = {m: "forge.core" for m in CORE}
PKG_OF.update({m: "forge" for m in TOP})


def _consume_spec_block(lines, i):
    """If lines[i] begins an inline spec_from_file_location block, consume it
    through its `.loader.exec_module(<local>)` line. Return (mod, local, indent,
    next_i) or None. Handles the block spanning several lines with any spec-var
    name."""
    m = re.search(r'spec_from_file_location\(\s*"(\w+)"', lines[i])
    # the module name may be on the NEXT line: spec_from_file_location(\n "mod",
    j = i
    if not m:
        if "spec_from_file_location(" in lines[i]:
            # look ahead for the "mod" string
            for k in range(i, min(i + 3, len(lines))):
                mm = re.search(r'"(\w+)"', lines[k])
                if mm:
                    m = mm
                    break
        if not m:
            return None
    mod = m.group(1)
    indent = re.match(r'\s*', lines[i]).group(0)
    # advance to the exec_module line
    local = None
    k = i
    while k < len(lines):
        lm = re.search(r'(\w+)\.loader\.exec_module\((\w+)\)', lines[k])
        if lm:
            local = lm.group(2)
            break
        k += 1
        if k - i > 8:  # safety: a spec block is never this long
            return None
    if local is None:
        return None
    return mod, local, indent, k + 1


def _emit_import(mod, local, indent):
    # principal is vendored as core/_ids.py
    if mod == "principal":
        target = "_ids"
    else:
        target = mod
    asclause = "" if local == target else f" as {local}"
    # core modules import each other relatively; principal/_ids is in core too
    return f"{indent}from . import {target}{asclause}\n"


def transform_module(src_text, modname):
    lines = src_text.splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # measure_panel: drop the __main__ alias shim (real imports don't need it)
        if 'sys.modules.setdefault("measure_panel"' in line:
            i += 1
            continue

        # instrument reuse-guard: `if "measure_panel" in sys.modules:` ... else exec
        if re.match(r'\s*if "measure_panel" in sys\.modules:', line):
            indent = re.match(r'\s*', line).group(0)
            k = i
            while k < len(lines) and "exec_module(measure_panel)" not in lines[k]:
                k += 1
            out.append(f"{indent}from . import measure_panel\n")
            i = k + 1
            continue

        # module-level `def _load(name, rel):` helper — drop it (through `return
        # mod`). Anchored to the `name` first-arg so it never matches a class
        # method like FilesystemSoilStore._load(self).
        if re.match(r'def _load\(name', line):
            k = i
            while k < len(lines) and "return mod" not in lines[k]:
                k += 1
            i = k + 1
            # also skip a trailing blank line
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            continue

        # `<local> = _load("<mod>", "<file>")`
        lm = re.match(r'(\s*)(\w+) = _load\(\s*"(\w+)"', line)
        if lm:
            indent, local, mod = lm.group(1), lm.group(2), lm.group(3)
            out.append(_emit_import(mod, local, indent))
            i += 1
            continue

        # inline spec block
        if "spec_from_file_location(" in line:
            got = _consume_spec_block(lines, i)
            if got:
                mod, local, indent, nxt = got
                if mod in ALL_MODS or mod == "principal":
                    out.append(_emit_import(mod, local, indent))
                    i = nxt
                    continue

        out.append(line)
        i += 1

    text = "".join(out)
    # drop now-dead `_REPO = Path(__file__).resolve().parent.parent` lines
    text = re.sub(r'^_REPO = Path\(__file__\)\.resolve\(\)\.parent\.parent\n', "", text, flags=re.M)
    return text


def transform_test(src_text):
    """Tests spec-load from _REPO/stores; convert to absolute `from forge... import`."""
    lines = src_text.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if "spec_from_file_location(" in line:
            got = _consume_spec_block(lines, i)
            if got:
                mod, local, indent, nxt = got
                pkg = PKG_OF.get(mod)
                if pkg:
                    asclause = "" if local == mod else f" as {local}"
                    out.append(f"{indent}from {pkg} import {mod}{asclause}\n")
                    i = nxt
                    continue
        out.append(line)
        i += 1
    text = "".join(out)
    text = re.sub(r'^_REPO = Path\(__file__\)\.resolve\(\)\.parent\.parent\n', "", text, flags=re.M)
    return text


def _probe_patch(text, probe_name, shared_local):
    """The soft-Nestor 'degraded probe' tests spec-load a virgin copy of the
    module to defeat checkpoint_memory's success-cache. A package module can't
    be spec-loaded standalone (its relative imports need the package), so the
    faithful equivalent is to reset the shared module's cache. Replace the
    fresh-load block with that."""
    pat = re.compile(
        r'        fresh_spec = importlib\.util\.spec_from_file_location\(\n'
        r'            "' + probe_name + r'",[^\n]*\n'
        r'        \)\n'
        r'        (fresh_\w+) = importlib\.util\.module_from_spec\(fresh_spec\)\n'
        r'        sys\.modules\["' + probe_name + r'"\] = \1\n'
        r'        fresh_spec\.loader\.exec_module\(\1\)\n'
    )
    def repl(m):
        fresh = m.group(1)
        return (
            "        # package-native: reset checkpoint_memory's success-cache so this\n"
            "        # block observes the freshly-blocked environment on the SHARED\n"
            "        # module. The monorepo probe spec-loaded a virgin copy to the same\n"
            "        # end; a package module can't be spec-loaded standalone (relative\n"
            "        # imports need the package), so the cache reset is the equivalent.\n"
            f"        {shared_local}.checkpoint_memory._nestor_cache = None\n"
            f"        {fresh} = {shared_local}\n"
        )
    new, n = pat.subn(repl, text)
    assert n == 1, f"probe patch for {probe_name} matched {n} times (expected 1)"
    return new


def patch_test(stem, text):
    if stem == "test_checkpoint":
        return _probe_patch(text, "checkpoint_degraded_probe", "checkpoint")
    if stem == "test_checkpoint_calibration":
        return _probe_patch(text, "checkpoint_calibration_degraded_probe", "checkpoint_calibration")
    if stem == "test_calibration":
        # the byte-identity-vs-playground test is a store-side concern (it reads
        # apps/oakenscrolls-office, which does not exist in the extracted repo);
        # drop it. It is the last function in the file.
        marker = "\ndef test_vendored_copy_is_byte_identical_to_the_playground_source"
        assert marker in text, "byte-identity test not found to drop"
        return text[: text.index(marker)] + "\n"
    return text


# ── build ────────────────────────────────────────────────────────────────────
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "forge" / "core").mkdir(parents=True)
(OUT / "tests").mkdir()

for m in CORE:
    dst = OUT / "forge" / "core" / f"{m}.py"
    dst.write_text(transform_module(STORES.joinpath(f"{m}.py").read_text(), m))
for m in TOP:
    dst = OUT / "forge" / f"{m}.py"
    dst.write_text(transform_module(STORES.joinpath(f"{m}.py").read_text(), m))

# vendored _ids.py (principal._check_builder_id charset)
(OUT / "forge" / "core" / "_ids.py").write_text('''\
"""forge/core/_ids.py — builder-id charset (vendored from safe-app-store principal.py).

The model side keys every per-builder record on a builder_id; principal.py (D2/D11)
is the one place that charset is defined, and checkpoint_memory imported
`principal._check_builder_id` from it. Rather than drag the 900-line SAFE identity
core into a dependency-light library, this vendors the ~10 lines actually used —
the same "vendor the primitive, not the package" discipline calibration/human_loop/
friction_floor follow. Bound as `principal` at the import site so the reference is
unchanged. If principal.py's charset moves, reconcile this copy.
"""
from __future__ import annotations

import re
from typing import Any

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MAX_BUILDER_ID_LEN = 128


class PrincipalError(Exception):
    """Fail-closed refusal — a builder_id that is not a str or fails the
    path-safety charset (D11)."""


def _check_builder_id(builder_id: Any) -> str:
    if not isinstance(builder_id, str):
        raise PrincipalError(f"builder_id must be a str, got {type(builder_id).__name__}")
    if not builder_id or not _ID_PATTERN.match(builder_id):
        raise PrincipalError(f"builder_id {builder_id!r} fails the path-safety charset (D11)")
    if len(builder_id) > _MAX_BUILDER_ID_LEN:
        raise PrincipalError(f"builder_id is longer than {_MAX_BUILDER_ID_LEN} characters")
    return builder_id
''')

(OUT / "forge" / "__init__.py").write_text('"""The Forge — a refuse-a-confident-wrong-answer harness (model side)."""\n')
(OUT / "forge" / "core" / "__init__.py").write_text('"""The Forge core — checkpoint loop + measuring panel, import-pure."""\n')

# tests
skip = {"test_forge_build", "test_no_raw_soil_reads"}
copied = []
for tf in sorted(TESTS_SRC.glob("test_*.py")):
    if tf.stem in skip:
        continue
    # only include tests whose spec-loads target library modules
    txt = tf.read_text()
    mods = set(re.findall(r'spec_from_file_location\(\s*"(\w+)"', txt))
    if not mods or not (mods & ALL_MODS):
        continue
    (OUT / "tests" / tf.name).write_text(patch_test(tf.stem, transform_test(txt)))
    copied.append(tf.name)

print("core modules:", len(CORE), "| top:", len(TOP))
print("tests copied:", len(copied))
for c in copied:
    print("  ", c)
