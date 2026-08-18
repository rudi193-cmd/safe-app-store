#!/usr/bin/env python3
"""stores/instrument_execution.py — the panel's execution instrument
(docs/design/the-forge-measure.md): kartikeya per-file parse/lint.

The box's load-bearing tool was kartikeya, because it EXECUTED the suspect code
instead of trusting a reading of it (`dates.pl` runs fine and prints a 0-based
month; the whole mess lints clean — facts only running could establish). This
instrument is that discipline as a panel instrument: run each source file
through its language's PARSER, inside kartikeya's sandbox, and flag any file
that does not parse. A parse failure is ground truth a static reading can miss
(the model wrote code that doesn't even parse); it is per-file, so it converges
with `census`/`hygiene`/`call-graph` on a bad file.

Parse, not run: `py_compile`-style `ast.parse`, `php -l`, `node --check`,
`bash -n` — none EXECUTE the file's code, so this greps for "does it parse" without
running whatever the model (or an attacker via a poisoned build) wrote. Even so,
it runs inside kartikeya (rule 11: reuse bite 0's sandbox, don't shell out
raw), and it is SAFE BY DEFAULT: `require_isolation=True` means a run that is not
really sandboxed (no bwrap) raises `InstrumentUnavailable` rather than parsing
untrusted code unprotected — the panel then honestly names `execution` an
uncovered class. `require_isolation=False` is an explicit opt-in for a
parse-only plain run where a sandbox is unavailable but the low risk is accepted.

The kartikeya `runner` is injectable (default: `kartikeya.sandbox.run_shell`),
so the parse->finding and isolation logic is unit-testable without bwrap.

Store-side (D1): `apps/the-forge/` never imports this.
"""
from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Reuse the ONE already-loaded measure_panel if present — a second spec-load
# would give a DISTINCT InstrumentUnavailable class, so run_panel would catch
# this instrument's unavailability under its generic handler and mislabel it
# "errored" instead of "could not run" (found live). One module, one exception
# identity.
if "measure_panel" in sys.modules:
    measure_panel = sys.modules["measure_panel"]
else:
    _mp_spec = importlib.util.spec_from_file_location("measure_panel", _REPO / "stores" / "measure_panel.py")
    measure_panel = importlib.util.module_from_spec(_mp_spec)
    sys.modules["measure_panel"] = measure_panel
    _mp_spec.loader.exec_module(measure_panel)

Finding = measure_panel.Finding
InstrumentUnavailable = measure_panel.InstrumentUnavailable
_iter_files = measure_panel._iter_files  # real files, no symlinks, no .git — shared with the pure instruments

# One PARSE (non-executing) command per language, run on a temp file INSIDE the
# sandbox. The file's CONTENT is shipped in base64 (shell-safe: alnum + / + =),
# decoded to a sandbox-internal temp, and parsed there. Shipping content rather
# than a path is why this works even though the build dir is NOT mounted into
# kartikeya's sandbox — and it is strictly safer: the build's own code is never
# mounted or run in place, only its text is parsed. Python uses `ast.parse` (no
# `__pycache__`); the others are file-based linters that never execute the code.
_PARSER_ON_TEMP: dict[str, str] = {
    # Read the source as BYTES: `open().read()` would decode with the sandbox's
    # locale, so a valid UTF-8 file with a non-ASCII comment/string would raise
    # UnicodeDecodeError under a C-locale sandbox and read as a false "does not
    # parse". `ast.parse(bytes)` honors the file's own coding cookie/BOM, the way
    # real Python compilation does.
    ".py": "python3 -c 'import ast,sys; ast.parse(open(sys.argv[1], \"rb\").read())'",
    ".php": "php -l",
    ".js": "node --check",
    ".mjs": "node --check",
    ".cjs": "node --check",
    ".sh": "bash -n",
    ".bash": "bash -n",
}


def _parse_command(content: bytes, parser: str) -> str:
    """Build the sandbox command: decode the base64 content to a temp, run the
    parser on it, preserve the parser's exit code, clean up the temp."""
    b64 = base64.b64encode(content).decode("ascii")
    return (
        f'T=$(mktemp) && printf %s {b64!r} | base64 -d > "$T" && '
        f'{parser} "$T"; rc=$?; rm -f "$T"; exit $rc'
    )


def _kartikeya_runner():
    """The default runner — kartikeya's sandbox. Raises `InstrumentUnavailable`
    if kartikeya isn't installed, so the panel records a coverage gap."""
    try:
        from kartikeya.sandbox import run_shell
    except ImportError as e:  # pragma: no cover - env-dependent
        raise InstrumentUnavailable("kartikeya not installed (`pip install kartikeya`)") from e

    def run(cmd: str, *, cwd: str, timeout: int) -> dict:
        return run_shell(cmd, cwd=cwd, timeout=timeout)

    return run


def _is_isolated(res: dict) -> bool:
    """Classify the run's isolation from kartikeya's result — the same truth
    bite 0's `SandboxRun.isolation` classifies: a `bwrap` label with no error is
    a real sandbox; a `bwrap` label WITH an error (the phantom-bwrap case, no
    bwrap binary) never entered one. `plain` is honest non-isolation."""
    return res.get("sandbox") == "bwrap" and not res.get("error")


def _parser_missing(res: dict) -> bool:
    """The parser binary itself is absent (e.g. no `php`) — the shell exits 127,
    the universal 'command not found' convention across bash/dash/sh. We key
    ONLY on that exit code. A textual scan of the parser's OWN diagnostics is
    unsafe: a real SyntaxError echoes the offending SOURCE line, which may itself
    contain the words 'not found' (`def not found():`, a `"widget not found"`
    literal) — matching that text would mask the very parse failures this
    instrument exists to catch. NOT a parse error (no parse-checker returns 127):
    we cannot check this file's language here, so it is skipped, not flagged."""
    return res.get("returncode") == 127


class ExecutionInstrument:
    """Runs each source file through its parser in the kartikeya sandbox;
    flags the ones that do not parse. `covers` the `execution` class."""

    name = "execution"
    covers = "execution"

    def __init__(self, runner=None, require_isolation: bool = True, timeout: int = 60):
        self._runner = runner  # injectable; default resolved lazily to kartikeya
        self.require_isolation = require_isolation
        self.timeout = timeout

    def measure(self, build_dir: Path) -> list["Finding"]:
        build_dir = Path(build_dir)
        targets = [
            (p, parser)
            for p in _iter_files(build_dir)
            if (parser := _PARSER_ON_TEMP.get(p.suffix.lower()))
        ]
        if not targets:
            return []  # nothing to parse — no sandbox probe, no coverage claim
        runner = self._runner or _kartikeya_runner()  # may raise InstrumentUnavailable

        if self.require_isolation:
            # Fail closed BEFORE any untrusted file is handed to the runner.
            # kartikeya runs in PLAIN mode when bwrap is unavailable, so checking
            # isolation only after a real run would already have parsed the first
            # file unsandboxed. Probe once with a trivial no-op, raise here, and
            # no file content is ever dispatched to a non-isolated runner.
            probe = runner("true", cwd=str(build_dir), timeout=self.timeout)
            if not _is_isolated(probe):
                raise InstrumentUnavailable(
                    f"execution grounding needs a working sandbox — kartikeya did not "
                    f"isolate ({probe.get('error') or probe.get('sandbox')!r}); no bwrap? "
                    f"Pass require_isolation=False to accept a plain parse-only run."
                )

        out: list[Finding] = []
        for p, parser in targets:
            rel = p.relative_to(build_dir).as_posix()
            try:
                content = p.read_bytes()
            except OSError:
                continue  # unreadable — cannot check, do not flag
            cmd = _parse_command(content, parser)
            res = runner(cmd, cwd=str(build_dir), timeout=self.timeout)
            if _parser_missing(res):
                continue  # parser binary absent — cannot check, do not flag
            if res.get("returncode", 0) != 0:
                err = (res.get("stderr") or res.get("stdout") or "").strip().splitlines()
                first = err[-1] if err else "parse failed"
                out.append(Finding(
                    instrument=self.name, artifact=rel, metric="parse", value="fail",
                    severity="high",
                    detail=f"does not parse ({p.suffix}) when actually run: {first[:160]}",
                ))
        return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="instrument_execution.py")
    ap.add_argument("build_dir")
    ap.add_argument("--no-require-isolation", action="store_true")
    a = ap.parse_args()
    try:
        found = ExecutionInstrument(require_isolation=not a.no_require_isolation).measure(Path(a.build_dir))
    except InstrumentUnavailable as e:
        print(f"unavailable: {e}", file=sys.stderr)
        raise SystemExit(2)
    for f in found:
        print(f"{f.artifact}: {f.detail}")
