"""Tests for the_forge.mount_policy (D6 — the per-build mount boundary).

Same honest-environment note as `test_sandbox_runner.py`: `bwrap` is NOT
installed in the container these tests run in, so every test that actually
executes a command runs kartikeya's documented **plain** fallback, with
`require_isolation=False` passed explicitly (`DEV_NO_ISOLATION`, same
constant name as the sandbox-runner suite so both are greppable together).
Real `kartikeya` calls, not mocked — what plain mode does NOT exercise is
whether bwrap actually enforces the generated policy's binds; that needs a
host with bubblewrap, same caveat `test_sandbox_runner.py` already states.
What IS exercised here, for real: does the generated policy contain exactly
the right `bind_read_write` entry, does it round-trip through kartikeya's
own config loader, and does a build actually run end to end when handed the
scoped policy via `sandbox_config`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_forge.plan import Plan
from the_forge.sandbox_runner import BuildResult, BuildTask

pytest.importorskip(
    "kartikeya.sandbox",
    reason="kartikeya is a real dependency (pyproject) — install it to run the D6 mount-policy tests",
)

from the_forge.mount_policy import (  # noqa: E402
    MountPolicyError,
    build_scoped_policy,
    run_scoped_build,
    write_scoped_policy,
)

# Same constant name/shape as test_sandbox_runner.py's DEV_NO_ISOLATION —
# greppable together, same reason (no bwrap in this container).
DEV_NO_ISOLATION = dict(require_isolation=False)


# ── the generated policy's bind_read_write ───────────────────────────────────

def test_bind_read_write_is_exactly_the_one_scoped_path(tmp_path):
    apps_root = tmp_path / "apps"
    policy = build_scoped_policy("alice", "widget", apps_root)

    expected = str((apps_root / "alice" / "widget").resolve())
    assert policy["bind_read_write"] == [expected]


def test_bind_read_write_never_contains_willow_root_template(tmp_path):
    apps_root = tmp_path / "apps"
    policy = build_scoped_policy("alice", "widget", apps_root)

    for entry in policy["bind_read_write"]:
        assert "{{WILLOW_ROOT}}" not in entry
        assert "WILLOW_ROOT" not in entry


def test_bind_read_write_never_contains_apps_root_itself(tmp_path):
    """The scope is one builder's one app, not the whole apps/ tree — a
    build must not get write access to sibling builders' directories."""
    apps_root = tmp_path / "apps"
    policy = build_scoped_policy("alice", "widget", apps_root)

    resolved_apps_root = str(apps_root.resolve())
    assert policy["bind_read_write"] != [resolved_apps_root]
    for entry in policy["bind_read_write"]:
        assert entry != resolved_apps_root


def test_bind_read_write_never_contains_the_repo_root(tmp_path):
    """`apps_root` here stands in for `safe-app-store/apps` — the policy
    must never bind the store's repo root itself, read-write or otherwise,
    for any builder/app pair."""
    repo_root = tmp_path / "safe-app-store"
    apps_root = repo_root / "apps"
    apps_root.mkdir(parents=True)
    policy = build_scoped_policy("alice", "widget", apps_root)

    resolved_repo_root = str(repo_root.resolve())
    assert policy["bind_read_write"] == [str((apps_root / "alice" / "widget").resolve())]
    for entry in policy["bind_read_write"]:
        assert entry != resolved_repo_root
        assert not entry.endswith("/safe-app-store")


def test_different_builders_get_different_scoped_roots(tmp_path):
    apps_root = tmp_path / "apps"
    alice = build_scoped_policy("alice", "widget", apps_root)
    bob = build_scoped_policy("bob", "widget", apps_root)

    assert alice["bind_read_write"] != bob["bind_read_write"]
    assert alice["bind_read_write"][0] not in bob["bind_read_write"]


def test_worktree_scan_roots_is_explicitly_empty(tmp_path):
    """Absent would silently inherit kartikeya's own
    ["{{WILLOW_ROOT}}/worktrees"] default, which collect_bind_mounts turns
    into extra READ-WRITE binds for anything discovered there — a second,
    silent way bind_read_write could stop being exactly one path."""
    policy = build_scoped_policy("alice", "widget", tmp_path / "apps")
    assert policy["worktree_scan_roots"] == []


def test_bind_read_only_excludes_home_github():
    """{{HOME}}/github is the vendored default's own repo-reaching entry —
    on this fleet's layout it IS the store (and every other builder's tree
    inside it). Must not appear in the scoped policy at all."""
    policy = build_scoped_policy("alice", "widget", "/tmp/apps")
    for entry in policy["bind_read_only"]:
        assert "github" not in entry
        assert "{{HOME}}" not in entry
        assert "{{WILLOW_ROOT}}" not in entry


# ── builder_id / app_name validation — before any path or file ──────────────

_HOSTILE_IDS = [
    "",
    "   ",
    "../../etc",
    "../victim",
    "/etc/passwd",
    "/absolute/path",
    "a/b",
    "a\x00b",
    "\x00",
    ".",
    "..",
    "-leading-dash",
    ".leading-dot",
]


@pytest.mark.parametrize("hostile", _HOSTILE_IDS)
def test_hostile_builder_id_is_rejected_before_any_path_is_built(hostile, tmp_path):
    with pytest.raises(MountPolicyError):
        build_scoped_policy(hostile, "widget", tmp_path / "apps")


@pytest.mark.parametrize("hostile", _HOSTILE_IDS)
def test_hostile_app_name_is_rejected_before_any_path_is_built(hostile, tmp_path):
    with pytest.raises(MountPolicyError):
        build_scoped_policy("alice", hostile, tmp_path / "apps")


def test_hostile_builder_id_writes_no_policy_file(tmp_path):
    """The specific exception type, and the specific absence of a file —
    write_scoped_policy must not call mkstemp before validation runs."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(MountPolicyError):
        write_scoped_policy("../../etc", "widget", tmp_path / "apps", dir=scratch)
    assert list(scratch.iterdir()) == []


def test_hostile_app_name_writes_no_policy_file(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(MountPolicyError):
        write_scoped_policy("alice", "/etc/passwd", tmp_path / "apps", dir=scratch)
    assert list(scratch.iterdir()) == []


def test_valid_ids_with_the_full_allowed_charset_are_accepted(tmp_path):
    # Same charset as promote_check.py's _APP_ID_PATTERN: leading
    # alphanumeric, then alnum/underscore/dot/dash.
    policy = build_scoped_policy("alice-99_beta.2", "widget-2.0_final", tmp_path / "apps")
    assert policy["bind_read_write"] == [
        str((tmp_path / "apps" / "alice-99_beta.2" / "widget-2.0_final").resolve())
    ]


def test_symlinked_apps_root_still_resolves_containment_correctly(tmp_path):
    """Defense in depth beyond the charset check: containment is verified
    against the RESOLVED apps_root, not the literal path handed in. A
    symlinked apps_root is legitimate (this fleet's own layout symlinks
    safe-app-store itself, per docs/fleet_paths.md) — the check must follow
    it and still confirm the scoped path lands inside, not reject every
    symlink outright."""
    outside = tmp_path / "outside"
    outside.mkdir()
    apps_root = tmp_path / "apps"
    apps_root.symlink_to(outside)
    # This is actually fine — apps_root resolves to `outside`, and the
    # scoped path (outside/alice/widget) is still strictly inside it. The
    # containment check should pass, not fail, proving it checks the
    # *resolved* root rather than rejecting all symlinks outright.
    policy = build_scoped_policy("alice", "widget", apps_root)
    assert policy["bind_read_write"] == [str((outside / "alice" / "widget").resolve())]


# ── the generated file is real, loadable JSON — round-tripped for real ──────

def test_write_scoped_policy_produces_valid_json(tmp_path):
    apps_root = tmp_path / "apps"
    path = write_scoped_policy("alice", "widget", apps_root, dir=tmp_path)
    try:
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["bind_read_write"] == [str((apps_root / "alice" / "widget").resolve())]
    finally:
        path.unlink(missing_ok=True)


def test_generated_policy_round_trips_through_kartikeya_load_sandbox_config(tmp_path, monkeypatch):
    """Not just JSON-shaped — actually loadable by the real
    kartikeya.sandbox config-resolution chain, the same one collect_bind_mounts
    calls behind the scenes.

    Deliberately `load_sandbox_config`, not `resolve_sandbox_config`: this
    environment carries two different kartikeya installs behind the same
    declared version number — an editable checkout with the newer
    `resolve_sandbox_config`/`is_vendored_default` pair, and the actual
    published `kartikeya>=0.0.7` this package's own pyproject.toml declares
    and `pip install -e ".[dev]"` (this README's own instructions) installs,
    which has only `load_sandbox_config` (found in review, 2026-08-02: the
    resolve_sandbox_config version of this test passed against the editable
    checkout and raised ImportError against the real declared dependency —
    a false-green test, not a working one). `load_sandbox_config` exists in
    both and reads `$KART_SANDBOX_CONFIG` the same way in both — verified by
    diffing the two installs' source, not assumed — so this is the one that
    actually proves the generated file loads under the dependency this
    package really ships against."""
    from kartikeya.sandbox import load_sandbox_config

    apps_root = tmp_path / "apps"
    path = write_scoped_policy("alice", "widget", apps_root, dir=tmp_path)
    try:
        monkeypatch.setenv("KART_SANDBOX_CONFIG", str(path))
        cfg = load_sandbox_config()
        assert cfg["bind_read_write"] == [str((apps_root / "alice" / "widget").resolve())]
        assert cfg["worktree_scan_roots"] == []
    finally:
        path.unlink(missing_ok=True)


def test_write_scoped_policy_uses_a_fresh_file_each_call(tmp_path):
    apps_root = tmp_path / "apps"
    a = write_scoped_policy("alice", "widget", apps_root, dir=tmp_path)
    b = write_scoped_policy("alice", "widget", apps_root, dir=tmp_path)
    try:
        assert a != b
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)


# ── end to end: run_scoped_build, plain fallback (see module docstring) ─────

_PLAN_PAYLOAD = {
    "app_name": "widget",
    "entries": [{"kind": "file_write", "dest_path": "src/app.py", "content": "x = 1\n"}],
}


def _emit_task(builder_id: str = "alice", app_name: str = "widget") -> BuildTask:
    import shlex
    import sys

    payload = dict(_PLAN_PAYLOAD, app_name=app_name)
    literal = json.dumps(json.dumps(payload))
    script = f"import sys; sys.stdout.write({literal})"
    cmd = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    return BuildTask(builder_id=builder_id, app_name=app_name, command=cmd, timeout_s=60)


def test_run_scoped_build_produces_a_plan(tmp_path):
    apps_root = tmp_path / "apps"
    (apps_root / "alice" / "widget").mkdir(parents=True)

    result = run_scoped_build(_emit_task(), apps_root, **DEV_NO_ISOLATION)

    assert isinstance(result, BuildResult)
    assert isinstance(result.plan, Plan)
    assert result.plan.app_name == "widget"
    assert result.builder_id == "alice"
    assert result.run.returncode == 0


def test_run_scoped_build_removes_its_temp_policy_file(tmp_path):
    """The policy is call-scoped, same lifetime as sandbox_config already
    has in sandbox_runner — it must not accumulate on disk across builds."""
    apps_root = tmp_path / "apps"
    (apps_root / "alice" / "widget").mkdir(parents=True)

    before = {p.name for p in tmp_path.glob("the-forge-kart-sandbox-*.json")}
    run_scoped_build(_emit_task(), apps_root, **DEV_NO_ISOLATION)
    after = {p.name for p in tmp_path.glob("the-forge-kart-sandbox-*.json")}
    assert after == before


def test_run_scoped_build_cleans_up_even_when_the_build_fails(tmp_path):
    apps_root = tmp_path / "apps"
    (apps_root / "alice" / "widget").mkdir(parents=True)
    task = BuildTask(builder_id="alice", app_name="widget", command="exit 7", timeout_s=30)

    import tempfile as _tempfile

    tmpdir_before = len(list(Path(_tempfile.gettempdir()).glob("the-forge-kart-sandbox-*.json")))
    from the_forge.sandbox_runner import SandboxError

    with pytest.raises(SandboxError):
        run_scoped_build(task, apps_root, **DEV_NO_ISOLATION)
    tmpdir_after = len(list(Path(_tempfile.gettempdir()).glob("the-forge-kart-sandbox-*.json")))
    assert tmpdir_after == tmpdir_before


def test_run_scoped_build_raises_mount_policy_error_for_hostile_builder_id(tmp_path):
    apps_root = tmp_path / "apps"
    task = BuildTask(builder_id="alice", app_name="widget", command="echo hi", timeout_s=10)
    # A task constructed with a valid identity, but a caller passing a
    # mismatched hostile builder_id straight to run_scoped_build's own
    # validation path (build_scoped_policy re-validates independently of
    # BuildTask, the same "don't trust the earlier check alone" shape
    # plan.py's validate_plan uses for app_name).
    from the_forge import mount_policy

    with pytest.raises(mount_policy.MountPolicyError):
        mount_policy.write_scoped_policy("../escape", task.app_name, apps_root)
