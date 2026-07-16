"""
Gate policy tests — sap.core.gate backed by willow-gate.

No database needed: the gate is the thing under test. The conftest autouse
fixture already runs each test inside actor("journal") with a throwaway
SQUIRREL_GATE_DIR; tests below re-enter actor() to switch roles.

The invariants these pin:
  - journal (user) may read, write, and export
  - jeles (LLM) may read, may NOT write, may NEVER export
  - no actor context -> denied, always (self-authorization is dead)
  - SAP_AUTHORIZED=1 grants nothing anymore
  - bypass(reason) remains the explicit script escape hatch
"""
import pytest

import sap.core.gate as gate


def test_journal_read_write_export_allowed():
    with gate.actor("journal"):
        gate.authorized("read")
        gate.authorized("write")
        gate.authorized("export")


def test_jeles_read_allowed():
    with gate.actor("jeles"):
        gate.authorized("read")


def test_jeles_write_denied():
    with gate.actor("jeles"):
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("write")


def test_jeles_export_denied():
    with gate.actor("jeles"):
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("export")


def test_no_actor_denied():
    # Leave the fixture's journal context: actor(None) isn't a thing, so we
    # simulate a bare call site by clearing the thread-local directly.
    prev = gate._state.actor_role
    gate._state.actor_role = None
    try:
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("read")
    finally:
        gate._state.actor_role = prev


def test_sap_authorized_env_grants_nothing(monkeypatch):
    monkeypatch.setenv("SAP_AUTHORIZED", "1")
    prev = gate._state.actor_role
    gate._state.actor_role = None
    try:
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("write")
    finally:
        gate._state.actor_role = prev


def test_bypass_still_works_without_actor():
    prev = gate._state.actor_role
    gate._state.actor_role = None
    try:
        with gate.bypass("test: explicit operator escape hatch"):
            gate.authorized("write")
    finally:
        gate._state.actor_role = prev


def test_bypass_requires_reason():
    with pytest.raises(ValueError):
        with gate.bypass("  "):
            pass


def test_actor_nesting_restores_previous():
    with gate.actor("jeles"):
        with gate.actor("journal"):
            gate.authorized("write")
        # back to jeles: write must be denied again
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("write")


def test_unknown_actor_rejected():
    with pytest.raises(ValueError):
        with gate.actor("elder"):
            pass


def test_denials_are_announced(tmp_path, monkeypatch):
    monkeypatch.setenv("SQUIRREL_GATE_DIR", str(tmp_path / "gate2"))
    gate.close()
    with gate.actor("jeles"):
        gate.authorized("read")
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("export")
    log = (tmp_path / "gate2" / "announcements.log").read_text()
    assert "BLOCKED" in log
    # Rookie announcements are LOUD — the blocked line is written 3x.
    blocked_lines = [l for l in log.splitlines() if "BLOCKED" in l]
    assert len(blocked_lines) >= 3
    gate.close()


def test_checkout_writes_exit_record(tmp_path, monkeypatch):
    monkeypatch.setenv("SQUIRREL_GATE_DIR", str(tmp_path / "gate3"))
    gate.close()
    with gate.actor("journal"):
        gate.authorized("read")
    gate.close()  # checks out the live session
    ledger = tmp_path / "gate3" / "ledger"
    kinds = {p.name.split(".")[1] for p in ledger.iterdir()}
    assert "entry" in kinds and "exit" in kinds
