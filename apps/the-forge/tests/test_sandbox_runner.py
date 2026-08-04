"""Tests for the_forge.sandbox_runner (D2 — running a build inside Kart).

**Honest environment note, in the same spirit as `sap_gate.FilesystemKeyStore`'s
docstring.** `bwrap` is NOT installed in the container these tests were
written and run in. Everything below that actually executes a command
therefore runs through kartikeya's documented **plain** (unsandboxed)
fallback, with `require_isolation=False` passed explicitly. That means:

  - The Kart calls are REAL, not mocked — real `kartikeya.sandbox.run_shell`,
    real subprocesses, real timeouts, real exit codes. What is exercised is
    the orchestration: does a command run, does its stdout become a Plan,
    does a bad command raise the right typed error, is nothing written.
  - **bwrap-level isolation is NOT exercised by these tests, and no test
    here proves it.** No assertion in this file demonstrates that a build
    was contained. `test_plain_mode_is_never_silently_treated_as_isolated`
    and `test_require_isolation_refuses_when_bwrap_is_unavailable` pin the
    *handling* of that gap; they do not close it. Verifying real containment
    needs a host with bubblewrap — that is kartikeya's own 112-test suite's
    job, not this module's.

`_bwrap_here()` gates the one test that would need a real sandbox, so this
file does the right thing on a host that does have bwrap instead of quietly
skipping the distinction.
"""
from __future__ import annotations

import json
import shlex
import shutil
import sys

import pytest

from the_forge.plan import FileWrite, McpCall, Plan
from the_forge.sandbox_runner import (
    MAX_PLAN_STDOUT_BYTES,
    BuildResult,
    BuildTask,
    SandboxError,
    SandboxRun,
    parse_plan_stdout,
    run_build,
    run_in_sandbox,
)

# Declared in pyproject, so a `pip install -e ".[dev]"` has it. Skipping
# rather than erroring keeps the other suites runnable on a checkout with
# nothing installed — the same contract stores/seam.py relies on.
pytest.importorskip(
    "kartikeya.sandbox",
    reason="kartikeya is a real dependency (pyproject) — install it to run the D2 runner tests",
)


def _bwrap_here() -> bool:
    return shutil.which("bwrap") is not None


# `require_isolation=False` everywhere a command actually runs, because this
# container has no bwrap. Named as a constant so every use site is greppable
# rather than looking like an incidental keyword argument.
DEV_NO_ISOLATION = dict(require_isolation=False)

_PLAN_PAYLOAD = {
    "app_name": "widget",
    "entries": [{"kind": "file_write", "dest_path": "src/app.py", "content": "x = 1\n"}],
}


def _emit(payload: object, *, app_name: str = "widget", command_extra: str = "") -> BuildTask:
    """A BuildTask whose command prints `payload` as JSON to stdout — the
    v1 build-task contract, exercised end to end."""
    literal = json.dumps(json.dumps(payload))  # a python string literal of the JSON text
    script = f"import sys; sys.stdout.write({literal})"
    cmd = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    if command_extra:
        cmd = f"{cmd}; {command_extra}"
    return BuildTask(builder_id="alice", app_name=app_name, command=cmd, timeout_s=60)


# ── BuildTask validation ─────────────────────────────────────────────────────

def test_empty_command_is_refused_at_construction():
    """kart returns sandbox="none" for a blank command — a third isolation
    state meaning "nothing ran". Refuse before that can reach the
    classifier."""
    with pytest.raises(SandboxError):
        BuildTask(builder_id="alice", app_name="widget", command="   ")


@pytest.mark.parametrize("field", ["builder_id", "app_name"])
def test_missing_identity_fields_are_refused(field):
    kwargs = {"builder_id": "alice", "app_name": "widget", "command": "echo hi"}
    kwargs[field] = ""
    with pytest.raises(SandboxError):
        BuildTask(**kwargs)


def test_non_positive_timeout_is_refused():
    with pytest.raises(SandboxError):
        BuildTask(builder_id="alice", app_name="widget", command="echo hi", timeout_s=0)


def test_build_task_defaults_to_no_network():
    """D7: network is a declared permission, never ambient."""
    assert BuildTask(builder_id="alice", app_name="widget", command="echo hi").allow_net is False


# ── parse_plan_stdout — the hostile-payload surface, no sandbox needed ───────

def test_well_formed_plan_stdout_parses():
    plan = parse_plan_stdout(json.dumps(_PLAN_PAYLOAD))
    assert isinstance(plan, Plan)
    assert plan.app_name == "widget"
    assert plan.entries[0] == FileWrite(dest_path="src/app.py", content="x = 1\n")


@pytest.mark.parametrize(
    "stdout",
    [
        "",                                   # printed nothing
        "   \n\t ",                           # whitespace only
        "not json at all",
        "{",                                  # truncated object
        '{"app_name": "widget",}',            # trailing comma
        "[1, 2, 3]",                          # JSON, but a list
        "null",
        "42",
        '"just a string"',
        "true",
        '{"app_name": "widget"}',             # no entries key
        '{"entries": []}',                    # no app_name key
        '{"app_name": "widget", "entries": []}',           # empty entries -> PlanError
        '{"app_name": "../../VICTIM", "entries": [{"kind": "file_write", '
        '"dest_path": "a.py", "content": "x"}]}',          # traversal app_name
        '{"app_name": "widget", "entries": [{"kind": "wat"}]}',      # unknown kind
        '{"app_name": "widget", "entries": [{"kind": "file_write"}]}',  # missing fields
        '{"app_name": "widget", "entries": "not-a-list"}',
        '{"app_name": 1, "entries": 7}',      # right keys, wrong types
        '{"app_name": "widget", "entries": [null]}',
        '{"app_name": "widget", "entries": [[]]}',
        # two JSON documents concatenated — "parse the first one" would be
        # exactly the shape-inference this parser refuses to do
        json.dumps(_PLAN_PAYLOAD) + json.dumps(_PLAN_PAYLOAD),
        # build noise on stdout instead of stderr
        "building...\n" + json.dumps(_PLAN_PAYLOAD),
        json.dumps(_PLAN_PAYLOAD) + "\ndone!",
    ],
)
def test_malformed_stdout_raises_sandbox_error_not_a_crash(stdout):
    """Every one of these is untrusted output from inside a sandbox. None
    of them may escape as JSONDecodeError, TypeError, AttributeError or
    PlanError — the caller catches one type."""
    with pytest.raises(SandboxError):
        parse_plan_stdout(stdout)


def test_plan_asserting_its_own_builder_id_is_refused():
    """plan.py refuses a plan that claims an identity (D11). That refusal
    must survive the trip through this parser as a SandboxError, not leak
    out as a PlanError."""
    payload = dict(_PLAN_PAYLOAD, builder_id="mallory")
    with pytest.raises(SandboxError) as exc:
        parse_plan_stdout(json.dumps(payload))
    assert "builder_id" in str(exc.value)


def test_plan_error_is_preserved_as_the_cause():
    """Wrapped the way stores/seam.py wraps PlanError — one exception type
    at the call site, the original still reachable on __cause__."""
    from the_forge.plan import PlanError

    with pytest.raises(SandboxError) as exc:
        parse_plan_stdout('{"app_name": "widget", "entries": []}')
    assert isinstance(exc.value.__cause__, PlanError)


def test_oversized_stdout_is_refused_before_parsing():
    huge = "x" * (MAX_PLAN_STDOUT_BYTES + 1)
    with pytest.raises(SandboxError) as exc:
        parse_plan_stdout(huge)
    assert "over the" in str(exc.value)


def test_app_name_mismatch_is_refused():
    with pytest.raises(SandboxError) as exc:
        parse_plan_stdout(json.dumps(_PLAN_PAYLOAD), expect_app_name="other-app")
    assert "different app" in str(exc.value)


def test_app_name_match_passes():
    plan = parse_plan_stdout(json.dumps(_PLAN_PAYLOAD), expect_app_name="widget")
    assert plan.app_name == "widget"


def test_mcp_call_entries_survive_parsing_unexecuted():
    """A staged MCP call is data crossing the seam, not a call being made.
    The runner must carry it through untouched — D5's allowlist decides
    later, in stores/seam.py, and nothing here executes anything."""
    payload = {
        "app_name": "widget",
        "entries": [{"kind": "mcp_call", "server": "nestor", "tool": "nestor_ask",
                      "args": {"q": "hi"}}],
    }
    plan = parse_plan_stdout(json.dumps(payload))
    assert plan.entries[0] == McpCall(server="nestor", tool="nestor_ask", args={"q": "hi"})


# ── real Kart execution (plain fallback in this container — see docstring) ───

def test_a_real_sandboxed_command_produces_a_plan():
    result = run_build(_emit(_PLAN_PAYLOAD), **DEV_NO_ISOLATION)
    assert isinstance(result, BuildResult)
    assert isinstance(result.plan, Plan)
    assert result.plan.app_name == "widget"
    assert result.builder_id == "alice"
    assert result.run.returncode == 0


def test_stderr_noise_does_not_pollute_the_plan():
    """The v1 contract: logs go to stderr, the plan owns stdout. A build
    that logs loudly must still produce a clean plan."""
    task = _emit(_PLAN_PAYLOAD, command_extra="echo 'compiling...' 1>&2; echo 'done' 1>&2")
    result = run_build(task, **DEV_NO_ISOLATION)
    assert result.plan.app_name == "widget"
    assert "compiling" in result.run.stderr


def test_build_printing_noise_to_stdout_is_refused():
    task = _emit(_PLAN_PAYLOAD, command_extra="echo 'oops, stdout'")
    with pytest.raises(SandboxError) as exc:
        run_build(task, **DEV_NO_ISOLATION)
    assert "stdout" in str(exc.value)


def test_a_command_that_exits_non_zero_raises_sandbox_error():
    task = BuildTask(builder_id="alice", app_name="widget",
                     command="echo 'failing now' 1>&2; exit 7", timeout_s=30)
    with pytest.raises(SandboxError) as exc:
        run_in_sandbox(task, **DEV_NO_ISOLATION)
    msg = str(exc.value)
    assert "returncode 7" in msg
    assert "failing now" in msg  # stderr is surfaced, not swallowed


def test_a_command_that_times_out_raises_sandbox_error():
    task = BuildTask(builder_id="alice", app_name="widget",
                     command="sleep 30", timeout_s=1)
    with pytest.raises(SandboxError) as exc:
        run_in_sandbox(task, **DEV_NO_ISOLATION)
    assert "timed out" in str(exc.value)


def test_a_command_that_prints_undecodable_bytes_raises_sandbox_error():
    """Deliberately hostile stdout: raw invalid UTF-8. kartikeya reads with
    text=True, so this fails inside run_shell rather than reaching the
    parser — either way the caller gets one typed error, never a
    UnicodeDecodeError from someone else's stream."""
    task = BuildTask(
        builder_id="alice", app_name="widget",
        command=f"{sys.executable} -c \"import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\x00bad')\"",
        timeout_s=30,
    )
    with pytest.raises(SandboxError):
        run_build(task, **DEV_NO_ISOLATION)


def test_a_build_emitting_a_plan_for_another_app_is_refused():
    """Consistency check only — the seam's containment math is still what
    stands between an app_name and the filesystem."""
    task = _emit({"app_name": "someone-elses-app",
                   "entries": _PLAN_PAYLOAD["entries"]}, app_name="widget")
    with pytest.raises(SandboxError) as exc:
        run_build(task, **DEV_NO_ISOLATION)
    assert "different app" in str(exc.value)


def test_workdir_is_honoured():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        task = BuildTask(builder_id="alice", app_name="widget", command="pwd",
                         workdir=d, timeout_s=30)
        run = run_in_sandbox(task, **DEV_NO_ISOLATION)
        assert run.stdout.strip().endswith(d.rsplit("/", 1)[-1])


def test_missing_workdir_is_refused_before_running():
    task = BuildTask(builder_id="alice", app_name="widget", command="pwd",
                     workdir="/nope/does/not/exist", timeout_s=30)
    with pytest.raises(SandboxError) as exc:
        run_in_sandbox(task, **DEV_NO_ISOLATION)
    assert "workdir" in str(exc.value)


# ── the plain-fallback contract ──────────────────────────────────────────────

@pytest.mark.skipif(_bwrap_here(), reason="bwrap IS installed here — the no-bwrap path can't be exercised")
def test_require_isolation_refuses_when_bwrap_is_unavailable():
    """Fail-closed by default. Without an explicit opt-out, a build on a
    host with no bubblewrap does not run at all — it does not quietly run
    unsandboxed."""
    with pytest.raises(SandboxError) as exc:
        run_in_sandbox(_emit(_PLAN_PAYLOAD))  # note: no require_isolation=False
    msg = str(exc.value)
    assert "without isolation" in msg
    assert "bubblewrap is not installed" in msg


@pytest.mark.skipif(_bwrap_here(), reason="bwrap IS installed here — plain fallback can't be exercised")
def test_plain_mode_is_never_silently_treated_as_isolated():
    """The whole point of the fallback handling: 'plain' is reported as
    plain, `isolated` is False, and a loud warning rides along with the
    result. Nothing here claims bwrap-level containment happened, because
    it did not."""
    result = run_build(_emit(_PLAN_PAYLOAD), **DEV_NO_ISOLATION)
    assert result.run.isolation == "plain"
    assert result.isolated is False
    assert result.run.isolated is False
    assert result.warnings, "an unisolated run must carry a warning"
    joined = " ".join(result.warnings)
    assert "NO ISOLATION" in joined
    assert "unsandboxed" in joined


@pytest.mark.skipif(_bwrap_here(), reason="bwrap IS installed here — plain fallback can't be exercised")
def test_the_warning_is_logged_not_just_returned(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="the_forge.sandbox_runner"):
        run_build(_emit(_PLAN_PAYLOAD), **DEV_NO_ISOLATION)
    assert any("NO ISOLATION" in r.getMessage() for r in caplog.records)


@pytest.mark.skipif(not _bwrap_here(), reason="needs a host with bubblewrap installed")
def test_real_bwrap_isolation_is_reported_as_isolated():
    """Only meaningful on a host that actually has bubblewrap. It is
    skipped in the container this module was developed in — recorded
    honestly rather than asserted."""
    result = run_build(_emit(_PLAN_PAYLOAD))
    assert result.run.isolation == "bwrap"
    assert result.isolated is True
    assert result.warnings == ()


def test_forced_plain_mode_restores_the_environment(monkeypatch):
    """`_scoped_env` mutates process-global env to force kart's plain mode
    (kartikeya reads WILLOW_KART_NO_BWRAP from os.environ, not from
    run_shell's env= argument). It must put back exactly what was there —
    including 'was not set at all'."""
    import os

    monkeypatch.delenv("WILLOW_KART_NO_BWRAP", raising=False)
    try:
        run_build(_emit(_PLAN_PAYLOAD), **DEV_NO_ISOLATION)
    except SandboxError:
        pass  # on a bwrap host this path isn't taken; the assertion still holds
    assert "WILLOW_KART_NO_BWRAP" not in os.environ


def test_scoped_env_restores_a_preexisting_value(monkeypatch):
    import os

    from the_forge.sandbox_runner import _scoped_env

    monkeypatch.setenv("FORGE_SCOPED_PROBE", "original")
    with _scoped_env(FORGE_SCOPED_PROBE="temporary", FORGE_SCOPED_ABSENT="set"):
        assert os.environ["FORGE_SCOPED_PROBE"] == "temporary"
        assert os.environ["FORGE_SCOPED_ABSENT"] == "set"
    assert os.environ["FORGE_SCOPED_PROBE"] == "original"
    assert "FORGE_SCOPED_ABSENT" not in os.environ


def test_scoped_env_restores_even_when_the_body_raises():
    import os

    from the_forge.sandbox_runner import _scoped_env

    with pytest.raises(RuntimeError):
        with _scoped_env(FORGE_SCOPED_PROBE2="temporary"):
            raise RuntimeError("boom")
    assert "FORGE_SCOPED_PROBE2" not in os.environ


def test_missing_sandbox_config_is_refused_before_running():
    """Found in review: kartikeya's resolve_sandbox_config() does not error
    on a missing/unparseable $KART_SANDBOX_CONFIG — it silently falls
    through to the repo's kart-sandbox.json, then its own vendored default.
    A typo'd sandbox_config path is D6's per-build mount boundary silently
    not applying, not an error a caller would ever see. Must fail closed
    the same way a missing workdir does."""
    task = BuildTask(builder_id="alice", app_name="widget", command="echo hi", timeout_s=10)
    with pytest.raises(SandboxError) as exc:
        run_in_sandbox(task, sandbox_config="/nope/does/not/exist/kart-sandbox.json",
                       **DEV_NO_ISOLATION)
    assert "sandbox_config" in str(exc.value)


def test_sandbox_config_is_scoped_to_the_call(tmp_path):
    """`sandbox_config` is the hook for D6's per-build mount policy — it
    points kart at a caller-authored $KART_SANDBOX_CONFIG for exactly one
    call. It must not leak into the process afterwards."""
    import os

    cfg = tmp_path / "kart-sandbox.json"
    cfg.write_text(json.dumps({"env_prefixes": ["FORGE_PROBE_"], "bind_try": []}))
    os.environ["FORGE_PROBE_VALUE"] = "reached-the-sandbox"
    try:
        task = BuildTask(builder_id="alice", app_name="widget",
                         command="printf '%s' \"$FORGE_PROBE_VALUE\"", timeout_s=30)
        run = run_in_sandbox(task, sandbox_config=cfg, **DEV_NO_ISOLATION)
        assert run.stdout.strip() == "reached-the-sandbox"
    finally:
        os.environ.pop("FORGE_PROBE_VALUE", None)
    assert "KART_SANDBOX_CONFIG" not in os.environ


# ── the module writes nothing — that is the seam's job ───────────────────────

def _tree(root):
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_the_runner_never_writes_the_files_in_the_plan(tmp_path):
    """D3: a build never writes to apps/<builder_id>/<app_name>/ — it emits
    a plan, and the SEAM applies it after the gate, the scope check, the
    content scan and the allowlist have all passed. A plan carrying three
    FileWrite entries must leave zero files behind here."""
    apps_root = tmp_path / "apps"
    (apps_root / "alice" / "widget").mkdir(parents=True)
    before = _tree(tmp_path)

    payload = {
        "app_name": "widget",
        "entries": [
            {"kind": "file_write", "dest_path": "src/app.py", "content": "x = 1\n"},
            {"kind": "file_write", "dest_path": "README.md", "content": "hi\n"},
            {"kind": "file_write", "dest_path": "run.sh", "content": "echo hi\n",
             "executable": True},
        ],
    }
    result = run_build(_emit(payload), **DEV_NO_ISOLATION)

    assert len(result.plan.entries) == 3
    assert _tree(tmp_path) == before, "the runner wrote something — that is the seam's job"


def test_the_runner_writes_nothing_even_when_the_workdir_is_writable(tmp_path):
    """Same claim, with the sandbox actually pointed at a writable
    directory: the runner itself still creates nothing. (A build COMMAND
    can obviously write inside its own workdir — that is what a build does,
    and inside bwrap it is contained. The assertion here is about the
    runner's own behaviour.)"""
    before = _tree(tmp_path)
    task = _emit(_PLAN_PAYLOAD)
    task = BuildTask(builder_id="alice", app_name="widget", command=task.command,
                     workdir=str(tmp_path), timeout_s=60)
    run_build(task, **DEV_NO_ISOLATION)
    assert _tree(tmp_path) == before


def test_a_failed_build_writes_nothing_either(tmp_path):
    before = _tree(tmp_path)
    task = BuildTask(builder_id="alice", app_name="widget",
                     command="exit 1", workdir=str(tmp_path), timeout_s=30)
    with pytest.raises(SandboxError):
        run_in_sandbox(task, **DEV_NO_ISOLATION)
    assert _tree(tmp_path) == before


# ── the module makes no trust decision ───────────────────────────────────────

def test_the_runner_does_not_import_store_side_authority():
    """D13 import-purity, and D2's separation of isolation from policy:
    this module must not reach sap_gate.py or seam.py. A runner that could
    verify a manifest would be a runner that could decide to trust one.

    AST-based, not a substring grep over the source — the module docstring
    legitimately *names* sap_gate and seam.py to explain what it deliberately
    doesn't do, and a text scan would flag that prose while missing a real
    `importlib.util.spec_from_file_location("sap_gate", ...)` load. Checks
    the actual import statements plus the dynamic-loading escape hatch
    stores/seam.py itself uses."""
    import ast
    import inspect

    from the_forge import sandbox_runner

    tree = ast.parse(inspect.getsource(sandbox_runner))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # `from .plan import ...` — this package's own
                continue
            imported.add(node.module or "")

    for name in sorted(imported):
        root = name.split(".", 1)[0]
        assert root not in {"stores", "sap_gate", "seam", "promote_check"}, \
            f"sandbox_runner imports store-side authority: {name!r}"
        # D13 in general: nothing from safe-app-store, only stdlib, kartikeya,
        # and this package's own modules.
        assert root in {"__future__", "contextlib", "dataclasses", "json", "logging",
                         "os", "pathlib", "typing", "kartikeya", "the_forge"}, \
            f"unexpected import in an import-pure module: {name!r}"

    # importlib.util.spec_from_file_location is how stores/seam.py loads
    # sap_gate.py off disk without importing it — the one way this module
    # could reach store-side authority while passing the import check above.
    assert "spec_from_file_location" not in inspect.getsource(sandbox_runner)


def test_a_dangerous_plan_is_returned_unjudged():
    """The runner is not the scan and not the gate. A plan whose content
    scan.py would refuse still comes back intact — refusing it is
    stores/seam.py's decision, at the seam, and duplicating that judgement
    here would create a second, drifting copy of the policy."""
    from the_forge.scan import scan_plan

    payload = {
        "app_name": "widget",
        "entries": [{"kind": "file_write", "dest_path": "evil.py",
                      "content": "import os\nos.system('rm -rf /')\n"}],
    }
    result = run_build(_emit(payload), **DEV_NO_ISOLATION)
    assert isinstance(result.plan, Plan)
    # ...and the seam's scan is what catches it, separately, afterwards.
    assert "evil.py" in scan_plan(result.plan.entries)


def test_sandbox_run_isolation_classification():
    """The classifier, over kart's real result shapes (taken from
    kartikeya 0.0.7's own run_shell return paths)."""
    from the_forge.sandbox_runner import _classify_isolation

    assert _classify_isolation({"sandbox": "bwrap"}) == "bwrap"
    assert _classify_isolation({"sandbox": "plain"}) == "plain"
    assert _classify_isolation({"sandbox": "none"}) == "none"
    assert _classify_isolation({"sandbox": "bwrap", "sandbox_setup": "ok"}) == "bwrap"
    assert _classify_isolation(
        {"sandbox": "bwrap", "sandbox_setup": "failed"}) == "bwrap_setup_failed"
    assert _classify_isolation(
        {"sandbox": "bwrap", "error": "sandbox_setup_failed"}) == "bwrap_setup_failed"
    assert _classify_isolation({}) == "unknown"


def test_sandbox_run_isolated_property_is_bwrap_only():
    for label in ("plain", "none", "bwrap_setup_failed", "unknown"):
        run = SandboxRun(command="x", returncode=0, stdout="", stderr="",
                         elapsed_s=0.0, isolation=label)
        assert run.isolated is False
    assert SandboxRun(command="x", returncode=0, stdout="", stderr="",
                      elapsed_s=0.0, isolation="bwrap").isolated is True
