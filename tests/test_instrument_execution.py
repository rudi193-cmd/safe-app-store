"""Tests for stores/instrument_execution.py — the panel's execution instrument
(kartikeya per-file parse/lint, docs/design/the-forge-measure.md).

"Run it, don't read it": each source file is run through its language's parser
INSIDE kartikeya's sandbox; a file that does not parse is a per-file finding
(converges with census/hygiene/call-graph). The kartikeya `runner` is injectable
so the parse->finding and isolation logic is fully tested without bwrap; a real
end-to-end drive is skipif'd when the sandbox can't run (as bite 0 skips).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "instrument_execution", _REPO / "stores" / "instrument_execution.py"
)
iex = importlib.util.module_from_spec(_spec)
sys.modules["instrument_execution"] = iex
_spec.loader.exec_module(iex)


def _isolated_ok(cmd, *, cwd, timeout):
    """A fake kartikeya runner: real bwrap isolation, parser succeeds."""
    return {"sandbox": "bwrap", "error": None, "returncode": 0, "stdout": "", "stderr": ""}


def _isolated_parsefail(stderr="SyntaxError: invalid syntax"):
    def run(cmd, *, cwd, timeout):
        return {"sandbox": "bwrap", "error": None, "returncode": 1, "stdout": "", "stderr": stderr}
    return run


def _no_bwrap(cmd, *, cwd, timeout):
    """The phantom-bwrap case (this env): labelled bwrap, never isolated."""
    return {"sandbox": "bwrap", "error": "No such file or directory: 'bwrap'",
            "returncode": -1, "stdout": "", "stderr": "[Errno 2] ... 'bwrap'"}


def _parser_missing(cmd, *, cwd, timeout):
    return {"sandbox": "bwrap", "error": None, "returncode": 127, "stdout": "",
            "stderr": "php: command not found"}


def _proj(tmp_path, files):
    d = tmp_path / "build"
    for name, body in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


# ── parse -> finding logic (injected runner, no bwrap needed) ────────────────

def test_a_file_that_does_not_parse_is_flagged(tmp_path):
    d = _proj(tmp_path, {"app.py": "def f(:\n  bad\n"})
    inst = iex.ExecutionInstrument(runner=_isolated_parsefail())
    findings = inst.measure(d)
    assert len(findings) == 1
    assert findings[0].artifact == "app.py"
    assert findings[0].metric == "parse" and findings[0].value == "fail"
    assert findings[0].instrument == "execution"


def test_a_clean_file_is_not_flagged(tmp_path):
    d = _proj(tmp_path, {"app.py": "def f():\n    return 1\n"})
    assert iex.ExecutionInstrument(runner=_isolated_ok).measure(d) == []


def test_only_files_with_a_known_parser_are_run(tmp_path):
    # a.py has a parser; notes.md/data.bin do not -> exactly ONE run happens.
    # (The filename is not in the command — content ships base64'd — so the
    # intent 'only parseable files run' is a count, not a substring, assertion.)
    d = _proj(tmp_path, {"a.py": "x=1\n", "notes.md": "# hi\n", "data.bin": "\x00"})
    seen = []
    def spy(cmd, *, cwd, timeout):
        seen.append(cmd)
        return _isolated_ok(cmd, cwd=cwd, timeout=timeout)
    iex.ExecutionInstrument(runner=spy).measure(d)
    # the isolation probe ('true') runs first, then exactly ONE file-parse
    # command (a.py); md/bin have no parser. Count the content commands, not the
    # probe.
    assert "true" in seen
    parse_cmds = [c for c in seen if "base64" in c]
    assert len(parse_cmds) == 1
    # and the shipped content decodes back to a.py's source
    import base64, re
    m = re.search(r"printf %s '([A-Za-z0-9+/=]+)'", parse_cmds[0])
    assert m and base64.b64decode(m.group(1)) == b"x=1\n"


def test_a_missing_parser_binary_is_skipped_not_flagged(tmp_path):
    # php absent (exit 127) -> can't check this file, but it is NOT a parse error
    d = _proj(tmp_path, {"index.php": "<?php echo 1;\n"})
    assert iex.ExecutionInstrument(runner=_parser_missing).measure(d) == []


def test_a_parse_failure_whose_message_contains_not_found_is_still_flagged(tmp_path):
    # regression (audit #1): a real SyntaxError echoes the offending SOURCE line,
    # which here contains the words "not found" — that must NOT be mistaken for a
    # missing parser binary. Only exit 127 means the binary is absent; a real
    # parse fail (exit 1) is flagged no matter what its text says.
    d = _proj(tmp_path, {"app.py": "def not found():\n"})
    def echoes_not_found(cmd, *, cwd, timeout):
        if cmd == "true":
            return {"sandbox": "bwrap", "error": None, "returncode": 0, "stdout": "", "stderr": ""}
        return {"sandbox": "bwrap", "error": None, "returncode": 1, "stdout": "",
                "stderr": '  File "T", line 1\n    def not found():\n            ^\nSyntaxError: invalid syntax'}
    findings = iex.ExecutionInstrument(runner=echoes_not_found).measure(d)
    assert len(findings) == 1 and findings[0].value == "fail"


# ── isolation safety: no sandbox -> unavailable, never runs unsandboxed ───────

def test_no_sandbox_raises_instrument_unavailable_by_default(tmp_path):
    d = _proj(tmp_path, {"app.py": "x = 1\n"})
    with pytest.raises(iex.InstrumentUnavailable):
        iex.ExecutionInstrument(runner=_no_bwrap).measure(d)  # require_isolation defaults True


def test_isolation_is_probed_before_any_file_content_is_run(tmp_path):
    # regression (audit #2): the isolation gate must fire BEFORE the first file's
    # content is handed to a non-isolated runner. A plain (unsandboxed) runner
    # must raise on the trivial probe, having dispatched NO file-parse command.
    d = _proj(tmp_path, {"app.py": "x = 1\n"})
    seen = []
    def plain(cmd, *, cwd, timeout):
        seen.append(cmd)
        return {"sandbox": "plain", "error": None, "returncode": 0, "stdout": "", "stderr": ""}
    with pytest.raises(iex.InstrumentUnavailable):
        iex.ExecutionInstrument(runner=plain).measure(d)
    assert seen == ["true"]  # only the probe ran
    assert all("base64" not in c for c in seen)  # no file content was ever dispatched


def test_require_isolation_false_allows_a_plain_run(tmp_path):
    # opt-in only: parse-checks don't execute code, so a plain run is acceptable
    # when explicitly allowed; the finding still lands
    d = _proj(tmp_path, {"app.py": "def f(:\n"})
    def plain_fail(cmd, *, cwd, timeout):
        return {"sandbox": "plain", "error": None, "returncode": 1, "stdout": "", "stderr": "SyntaxError"}
    findings = iex.ExecutionInstrument(runner=plain_fail, require_isolation=False).measure(d)
    assert len(findings) == 1


def test_no_parseable_files_means_no_sandbox_probe_and_no_error(tmp_path):
    # a build with nothing runnable doesn't spuriously raise unavailable
    d = _proj(tmp_path, {"README.md": "# hi\n"})
    assert iex.ExecutionInstrument(runner=_no_bwrap).measure(d) == []


# ── real kartikeya drive (skipped when the sandbox can't run) ────────────────

def _kartikeya_isolates():
    try:
        from kartikeya.sandbox import run_shell
    except ImportError:
        return False
    r = run_shell("true")
    return r.get("sandbox") == "bwrap" and not r.get("error")


@pytest.mark.skipif(not _kartikeya_isolates(), reason="kartikeya cannot isolate here (no bwrap)")
def test_drives_real_kartikeya_and_flags_a_syntax_error(tmp_path):
    d = _proj(tmp_path, {"good.py": "def f():\n    return 1\n", "bad.py": "def g(:\n  x\n"})
    findings = iex.ExecutionInstrument().measure(d)
    flagged = {f.artifact for f in findings}
    assert "bad.py" in flagged
    assert "good.py" not in flagged
