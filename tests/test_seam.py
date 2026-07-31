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
    assert report["deferred_mcp_calls"] == []


def test_executable_flag_sets_the_mode(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="run.py", content="#!/usr/bin/env python3\n", executable=True),))

    report = seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)
    mode = Path(report["written"][0]).stat().st_mode
    assert mode & 0o111  # at least one execute bit set


def test_mcp_call_entries_are_deferred_not_executed(tmp_path):
    ks, ledger, apps_root = _rig(tmp_path)
    signed = sap_gate.sign_manifest(_manifest(), builder_id="alice", keystore=ks, ledger=ledger)
    plan = Plan(app_name="widget", entries=(
        FileWrite(dest_path="app.py", content="x = 1\n"),
        McpCall(server="nestor", tool="nestor_ask", args={"q": "hi"}),
    ))

    report = seam.cross(signed_manifest=signed, plan=plan, keystore=ks, ledger=ledger, apps_root=apps_root)

    assert len(report["written"]) == 1  # only the file_write crossed
    assert report["deferred_mcp_calls"] == [{"server": "nestor", "tool": "nestor_ask"}]


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
