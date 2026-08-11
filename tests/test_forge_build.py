"""Tests for stores/forge_build.py — The Forge bite 0's spine.

Same loading convention as tests/test_seam.py and tests/test_sap_gate.py:
load the module directly from stores/, no package install required. Every
test builds its own apps_root/key_root/ledger under tmp_path — nothing here
ever touches the real stores/.sap_gate_keys, stores/.sap_gate_ledger.jsonl,
or apps/.

`require_isolation=False` everywhere a build actually runs — this container
has no bwrap, and kartikeya's documented plain fallback is what CI runs on
(same honest-environment note as apps/the-forge/tests/test_sandbox_runner.py
and test_mount_policy.py: real kartikeya calls, not mocked, just unsandboxed
ones). The isolation-provenance test below is exactly what pins that this
is reported honestly, not silently upgraded to "isolated".
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("forge_build", _REPO / "stores" / "forge_build.py")
forge_build = importlib.util.module_from_spec(_spec)
sys.modules["forge_build"] = forge_build
_spec.loader.exec_module(forge_build)

sap_gate = forge_build.sap_gate
seam = forge_build.seam
hello_world_command = forge_build.hello_world_command
dev_manifest = forge_build.dev_manifest
build_and_cross = forge_build.build_and_cross

pytest.importorskip(
    "kartikeya.sandbox",
    reason="kartikeya is a real dependency of apps/the-forge — install it to run the forge_build spine tests",
)

DEV_NO_ISOLATION = dict(require_isolation=False)


def _rig(tmp_path):
    keystore = sap_gate.FilesystemKeyStore(tmp_path / "keys")
    ledger = sap_gate.SigningLedger(tmp_path / "ledger.jsonl")
    apps_root = tmp_path / "apps"
    return keystore, ledger, apps_root


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _escaping_plan_command(app_name: str) -> str:
    """Hand-crafted, NOT via stub_builder.hello_world_command — a build
    that emits a plan whose FileWrite tries to escape its own app tree via
    `..` traversal. Same self-contained `python3 -c` shape as the stub
    builder (see the_forge/stub_builder.py), just with a hostile
    dest_path baked into the payload instead of the safe one."""
    payload = {
        "app_name": app_name,
        "entries": [
            {"kind": "file_write", "dest_path": "../../escape.py", "content": "pwned = True\n"},
        ],
    }
    script = f"import json; print(json.dumps({payload!r}))"
    return f"python3 -c {_shell_quote(script)}"


def _absolute_escaping_plan_command(app_name: str) -> str:
    """A second escape shape: an absolute destination path, not a relative
    traversal — plan.py's containment check refuses both, but for a
    slightly different reason in the code (`rel.is_absolute()` vs. `".."
    in rel.parts`), so both are worth pinning independently."""
    payload = {
        "app_name": app_name,
        "entries": [
            {"kind": "file_write", "dest_path": "/etc/evil", "content": "pwned = True\n"},
        ],
    }
    script = f"import json; print(json.dumps({payload!r}))"
    return f"python3 -c {_shell_quote(script)}"


# ── happy path ────────────────────────────────────────────────────────────

def test_happy_path_writes_hello_world_and_reports_it(tmp_path):
    keystore, ledger, apps_root = _rig(tmp_path)

    report = build_and_cross(
        builder_id="dev",
        app_name="hello",
        command=hello_world_command("hello"),
        apps_root=apps_root,
        keystore=keystore,
        ledger=ledger,
        **DEV_NO_ISOLATION,
    )

    assert report["builder_id"] == "dev"

    written = {Path(p).name: Path(p) for p in report["written"]}
    assert set(written) == {"README.md", "app.py"}

    readme = apps_root / "dev" / "hello" / "README.md"
    app_py = apps_root / "dev" / "hello" / "app.py"
    assert readme.is_file()
    assert app_py.is_file()
    assert written["README.md"].resolve() == readme.resolve()
    assert written["app.py"].resolve() == app_py.resolve()

    assert app_py.read_text() == "print('hello from hello')"
    assert "hello" in readme.read_text()

    assert report["allowed_mcp_calls"] == []


# ── crown jewel: containment denial ──────────────────────────────────────

def test_relative_traversal_escape_is_denied_and_nothing_escapes(tmp_path):
    """The property this whole bite exists to guarantee: a build that emits
    a plan trying to write outside its own apps/<builder_id>/<app_name>/
    tree is refused at the seam, and the escape target is never created —
    anywhere on disk, not just "not at the exact path we guessed"."""
    keystore, ledger, apps_root = _rig(tmp_path)

    with pytest.raises(seam.SeamError):
        build_and_cross(
            builder_id="dev",
            app_name="hello",
            command=_escaping_plan_command("hello"),
            apps_root=apps_root,
            keystore=keystore,
            ledger=ledger,
            **DEV_NO_ISOLATION,
        )

    # Nowhere under tmp_path (which contains apps_root and everything else
    # this test touches) may an "escape.py" file exist — not next to
    # apps_root, not two levels up from the scoped app dir, nowhere.
    escapees = list(tmp_path.rglob("escape.py"))
    assert escapees == [], f"containment escaped: {escapees}"

    # And the app's own tree stayed exactly as the sandbox left it: nothing
    # in it either, since the whole plan was denied (all-or-nothing, D3).
    scoped_root = apps_root / "dev" / "hello"
    if scoped_root.exists():
        assert list(scoped_root.rglob("*")) == []


def test_absolute_path_escape_is_denied_and_nothing_escapes(tmp_path):
    keystore, ledger, apps_root = _rig(tmp_path)

    with pytest.raises(seam.SeamError):
        build_and_cross(
            builder_id="dev",
            app_name="hello",
            command=_absolute_escaping_plan_command("hello"),
            apps_root=apps_root,
            keystore=keystore,
            ledger=ledger,
            **DEV_NO_ISOLATION,
        )

    assert not Path("/etc/evil").exists()


# ── signing binds identity ───────────────────────────────────────────────

def test_dev_manifest_binds_maker_to_builder_id():
    manifest = dev_manifest("dev", "hello")
    assert manifest["maker"] == "dev"
    assert manifest["app_id"] == "hello"
    assert manifest["store_scope"] == ["saps1/builder-dev"]
    assert manifest["permissions"] == []


def test_signing_refuses_a_manifest_whose_maker_does_not_match_builder_id(tmp_path):
    keystore, ledger, _apps_root = _rig(tmp_path)
    manifest = dev_manifest("dev", "hello")
    manifest["maker"] = "someone-else"

    with pytest.raises(sap_gate.GateError):
        sap_gate.sign_manifest(manifest, builder_id="dev", keystore=keystore, ledger=ledger)


# ── isolation provenance is honest ───────────────────────────────────────

def test_isolation_provenance_is_reported_honestly_under_plain_fallback(tmp_path):
    """A build that wasn't actually contained must say so in the report —
    D10's 'a seam-side record that doesn't say whether the build was
    contained is recording half a fact,' applied here. This container has
    no bwrap, so require_isolation=False runs kartikeya's plain fallback,
    and the report must reflect that rather than silently reading as
    isolated."""
    keystore, ledger, apps_root = _rig(tmp_path)

    report = build_and_cross(
        builder_id="dev",
        app_name="hello",
        command=hello_world_command("hello"),
        apps_root=apps_root,
        keystore=keystore,
        ledger=ledger,
        **DEV_NO_ISOLATION,
    )

    assert report["isolated"] is False
    assert any("NO ISOLATION" in w for w in report["warnings"])


# ── the CLI presents every denial type uniformly (bite 0 follow-up) ───────

def test_cli_presents_a_sandbox_denial_uniformly_not_as_a_traceback(tmp_path, capsys):
    """bite 0's own recorded follow-up: the `build` CLI caught SeamError and
    GateError for a clean `DENIED: ...` line but let SandboxError/PlanError
    escape as a raw traceback. On this bwrap-less host the default
    (require_isolation=True) path raises SandboxError before any signing or
    seam stage — so it is the honest way to reach that catch — and the CLI
    must now present it the same way: `DENIED: ...` on stderr, exit 1, no
    traceback, nothing written."""
    rc = forge_build.main([
        "build", "hello",
        "--apps-root", str(tmp_path / "apps"),
        "--key-root", str(tmp_path / "keys"),
        "--ledger", str(tmp_path / "ledger.jsonl"),
        # No --no-require-isolation on purpose: isolation is required, and this
        # container has no bwrap, so run_scoped_build raises SandboxError.
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert "DENIED:" in err
    # It never crossed the seam, so nothing landed under the scoped app tree.
    assert not (tmp_path / "apps" / "dev" / "hello").exists()


def test_cli_happy_path_returns_zero_and_prints_the_report(tmp_path, capsys):
    """The other side of the same CLI branch: a clean build (plain fallback,
    since no bwrap) exits 0 and prints the report JSON, so the uniform-denial
    change above did not swallow a success."""
    rc = forge_build.main([
        "build", "hello",
        "--apps-root", str(tmp_path / "apps"),
        "--key-root", str(tmp_path / "keys"),
        "--ledger", str(tmp_path / "ledger.jsonl"),
        "--no-require-isolation",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["builder_id"] == "dev"
    assert {Path(p).name for p in report["written"]} == {"README.md", "app.py"}
    assert report["isolated"] is False


# ── idempotent-ish / re-cross ─────────────────────────────────────────────

def test_a_second_build_overwrites_within_its_own_tree_and_stays_contained(tmp_path):
    keystore, ledger, apps_root = _rig(tmp_path)

    first = build_and_cross(
        builder_id="dev",
        app_name="hello",
        command=hello_world_command("hello"),
        apps_root=apps_root,
        keystore=keystore,
        ledger=ledger,
        **DEV_NO_ISOLATION,
    )
    second = build_and_cross(
        builder_id="dev",
        app_name="hello",
        command=hello_world_command("hello"),
        apps_root=apps_root,
        keystore=keystore,
        ledger=ledger,
        **DEV_NO_ISOLATION,
    )

    assert set(first["written"]) == set(second["written"])
    app_py = apps_root / "dev" / "hello" / "app.py"
    assert app_py.read_text() == "print('hello from hello')"

    # Still nothing outside the scoped tree, second time either.
    scoped_root = apps_root / "dev" / "hello"
    for p in apps_root.rglob("*"):
        if p.is_file():
            assert p.resolve().is_relative_to(scoped_root.resolve())
