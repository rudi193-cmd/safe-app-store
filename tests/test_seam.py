"""Tests for stores/seam.py — the whole D3/D4 pipeline wired together.

Same loading convention as tests/test_sap_gate.py and
tests/test_promote_check_record.py: load directly from stores/, no package
install. Every test builds its own key-store/ledger/apps-root under
tmp_path — nothing here touches the real stores/ or apps/ trees.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seam", _REPO / "stores" / "seam.py")
seam = importlib.util.module_from_spec(_spec)
sys.modules["seam"] = seam
_spec.loader.exec_module(seam)

sap_gate = seam.sap_gate
Plan = seam.Plan
FileWrite = seam.FileWrite
McpCall = seam.McpCall
McpRegistry = seam.McpRegistry


def _manifest(**overrides):
    m = {"app_id": "widget", "permissions": ["file_write"], "store_scope": ["widget_*"], "maker": "alice"}
    m.update(overrides)
    return m


def _rig(tmp_path):
    ks = sap_gate.FilesystemKeyStore(tmp_path / "keys")
    ledger = sap_gate.SigningLedger(tmp_path / "ledger.jsonl")
    apps_root = tmp_path / "apps"
    return ks, ledger, apps_root


def _simple_plan():
    return Plan(app_name="widget", entries=(FileWrite(dest_path="app.py", content="x = 1\n"),))


def test_full_pipeline_writes_the_file(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="app.py", content="print(1)\n"),))

    report = seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)

    assert report["builder_id"] == "alice"
    written_path = Path(report["written"][0])
    assert written_path == (apps_root / "alice" / "widget" / "app.py").resolve()
    assert written_path.read_text() == "print(1)\n"
    assert report["allowed_mcp_calls"] == []


def test_executable_flag_sets_the_mode(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="run.py", content="#!/usr/bin/env python3\n", executable=True),))

    report = seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)
    mode = Path(report["written"][0]).stat().st_mode
    assert mode & 0o111  # at least one execute bit set


def _nestor_registry():
    reg = McpRegistry()
    reg.register("nestor", launch_command=["nestor", "serve"], allowed_tools=["nestor_ask", "nestor_propose"])
    return reg


def test_mcp_call_with_no_registry_supplied_is_denied_by_default(tmp_path):
    """D5's default-deny holds at the seam's own boundary, not just inside
    a registry that happens to exist — no registry means nothing crosses."""
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(McpCall(server="nestor", tool="nestor_ask", args={}),))

    with pytest.raises(seam.SeamError, match="no registry was supplied"):
        seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)


def test_allowlisted_mcp_call_is_allowed_but_not_executed(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="app.py", content="x = 1\n"),
        McpCall(server="nestor", tool="nestor_ask", args={"q": "hi"}),
    ))

    report = seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger,
                         apps_root=apps_root, mcp_registry=_nestor_registry())

    assert len(report["written"]) == 1  # only the file_write actually crosses
    assert report["allowed_mcp_calls"] == [{"server": "nestor", "tool": "nestor_ask"}]


def test_mcp_call_for_a_withheld_tool_denies_the_whole_plan(tmp_path):
    """nestor_seal is never on the registry's allowlist — same shape as
    nestor.serve.Server's own WITHHELD set. A FileWrite entry alongside it
    must NOT cross either: one bad entry denies the whole plan, same
    all-or-nothing posture as the scope check and the scan."""
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="app.py", content="x = 1\n"),
        McpCall(server="nestor", tool="nestor_seal", args={}),
    ))

    with pytest.raises(seam.SeamError, match="not on server"):
        seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger,
                    apps_root=apps_root, mcp_registry=_nestor_registry())
    assert not (apps_root / "alice" / "widget" / "app.py").exists()


def test_mcp_call_to_an_unregistered_server_is_denied(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(McpCall(server="some-other-server", tool="anything", args={}),))

    with pytest.raises(seam.SeamError, match="not registered"):
        seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger,
                    apps_root=apps_root, mcp_registry=_nestor_registry())


def test_unsigned_manifest_is_denied_before_anything_crosses(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    forged = sap_gate.SignedManifest(manifest=_manifest(), builder_id="alice",
                                      signature="00" * 64, signed_at=1.0)
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="app.py", content="x = 1\n"),))

    with pytest.raises(seam.SeamError, match="gate denied"):
        seam.cross(signed_manifest=forged, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)
    assert not (apps_root / "alice" / "widget" / "app.py").exists()


def test_out_of_scope_plan_is_denied_even_with_a_valid_signature(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="../../etc/evil", content="x"),))

    with pytest.raises(seam.SeamError, match="out of scope"):
        seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)


def test_dangerous_content_is_denied_even_when_well_scoped_and_signed(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="app.py", content="import os\n\ndef go():\n    os.system('evil')\n"),
    ))

    with pytest.raises(seam.SeamError, match="scan refused"):
        seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)
    assert not (apps_root / "alice" / "widget" / "app.py").exists()


def test_compromised_key_is_denied_at_the_gate(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    ledger.append(builder_id="alice", event="compromise", reason="test",
                   timestamp=signed.signed_at - 1)  # backdated, so it covers this signature

    with pytest.raises(seam.SeamError, match="gate denied"):
        seam.cross(signed_manifest=signed, plan=_simple_plan(), keystore=ks, ledger=ledger, apps_root=apps_root)


def test_symlinked_intermediate_directory_planted_after_validation_is_refused(tmp_path, monkeypatch):
    """HIGH audit finding: validate_plan() resolves destinations before the
    write loop runs, and nothing re-checked containment once the write
    loop's mkdir() made the directory real. A symlink planted in that
    window redirected writes outside the builder's own tree.

    Genuinely simulates the TOCTOU window rather than pre-planting the
    symlink (which the EXISTING validate_plan containment check would
    already catch on its own, proving nothing about this fix specifically):
    wraps validate_plan so the symlink lands exactly between its return and
    the write loop that follows, in cross()'s own real call order."""
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="sub/app.py", content="x = 1\n"),))

    outside = tmp_path / "outside-victim"
    outside.mkdir()
    real_validate_plan = seam.validate_plan

    def _validate_then_plant_symlink(*args, **kwargs):
        resolved = real_validate_plan(*args, **kwargs)
        sub_dir = apps_root / "alice" / "widget" / "sub"
        sub_dir.parent.mkdir(parents=True, exist_ok=True)
        sub_dir.symlink_to(outside, target_is_directory=True)
        return resolved

    monkeypatch.setattr(seam, "validate_plan", _validate_then_plant_symlink)

    with pytest.raises(seam.SeamError, match="replaced with a symlink"):
        seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)
    assert not (outside / "app.py").exists()


def test_multiple_file_writes_all_cross_in_order(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="a.py", content="a\n"),
        FileWrite(dest_path="sub/b.py", content="b\n"),
    ))

    report = seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)

    assert len(report["written"]) == 2
    assert (apps_root / "alice" / "widget" / "a.py").read_text() == "a\n"
    assert (apps_root / "alice" / "widget" / "sub" / "b.py").read_text() == "b\n"
