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
