"""
Receipt trail tests — every Squirrel tool call leaves a row.

Schema is willow-data-vault/schema/03_receipts.sql verbatim; the invariants:
  - gate allow / deny / bypass / unattributed each write a receipt
  - the acting identity lands in app_id
  - @squirrel: commands write cmd:* receipts through the responder
  - tail() is newest-first, filterable by actor, capped
"""
import pytest

import sap.core.gate as gate
import sap.core.receipts as receipts


def _rows(**kw):
    return receipts.tail(**kw)


def test_gate_allow_writes_ok_receipt():
    with gate.actor("journal"):
        gate.authorized("read")
    row = _rows(limit=1)[0]
    assert row["app_id"] == "squirrel-journal"
    assert row["tool"] == "pii:read"
    assert row["outcome"] == "ok"
    assert row["detail"] == "family_history"


def test_gate_denial_writes_denied_receipt():
    with gate.actor("jeles"):
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("write")
    row = _rows(limit=1)[0]
    assert row["app_id"] == "squirrel-jeles"
    assert row["tool"] == "pii:write"
    assert row["outcome"] == "denied"


def test_bypass_writes_receipt_with_reason():
    with gate.bypass("test: backfill memorial 273702757"):
        gate.authorized("write")
    row = _rows(limit=1)[0]
    assert row["app_id"] == "operator-bypass"
    assert row["outcome"] == "bypass"
    assert "backfill memorial 273702757" in row["detail"]


def test_unattributed_call_is_receipted():
    prev = gate._state.actor_role
    gate._state.actor_role = None
    try:
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("read")
    finally:
        gate._state.actor_role = prev
    row = _rows(limit=1)[0]
    assert row["app_id"] == "unattributed"
    assert row["outcome"] == "denied"


def test_export_receipt_names_the_operation():
    with gate.actor("journal"):
        gate.authorized("export")
    assert _rows(limit=1)[0]["tool"] == "pii:export"


def test_tail_is_newest_first_and_filterable():
    with gate.actor("journal"):
        gate.authorized("read")
    with gate.actor("jeles"):
        gate.authorized("read")
    rows = _rows(limit=2)
    assert rows[0]["app_id"] == "squirrel-jeles"   # newest first
    assert rows[1]["app_id"] == "squirrel-journal"
    only_jeles = _rows(app_id="squirrel-jeles", limit=50)
    assert only_jeles and all(r["app_id"] == "squirrel-jeles" for r in only_jeles)


def test_responder_writes_command_receipts():
    from responder.state import AppState
    from squirrel_responder import make_responder

    class _NullState(AppState):
        def append(self, text):  # keep the test off the real Squirrel.md
            pass

    handle = make_responder(_NullState())
    handle("@squirrel: mode journal")
    row = _rows(limit=1)[0]
    assert row["app_id"] == "squirrel-journal"
    assert row["tool"] == "cmd:mode"
    assert row["outcome"] == "ok"
    assert row["detail"].startswith("mode journal")


def test_receipts_command_renders_the_trail():
    from responder.commands.control import cmd_receipts
    with gate.actor("jeles"):
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("export")
    out = cmd_receipts(["5"])
    assert "pii:export" in out and "denied" in out
    filtered = cmd_receipts(["5", "jeles"])
    assert "squirrel-jeles" in filtered and "squirrel-journal" not in filtered
