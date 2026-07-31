from pathlib import Path

import pytest

from the_forge.plan import (
    FileWrite,
    McpCall,
    Plan,
    PlanError,
    entry_to_dict,
    plan_from_dict,
    plan_to_dict,
    validate_plan,
)


def test_plan_requires_app_name():
    with pytest.raises(PlanError):
        Plan(app_name="", entries=(FileWrite(dest_path="a.py", content="x"),))


def test_plan_requires_at_least_one_entry():
    with pytest.raises(PlanError):
        Plan(app_name="widget", entries=())


def test_valid_file_write_resolves_inside_builder_tree(tmp_path):
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="src/app.py", content="print(1)"),))
    resolved = validate_plan(plan, builder_id="alice", apps_root=tmp_path)
    assert resolved == [(tmp_path / "alice" / "widget" / "src" / "app.py").resolve()]


@pytest.mark.parametrize(
    "dest_path",
    [
        "../../etc/evil",
        "../sibling-app/x.py",
        "/etc/evil",
        "a/../../evil",
    ],
)
def test_escaping_or_absolute_dest_path_is_refused(tmp_path, dest_path):
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path=dest_path, content="x"),))
    with pytest.raises(PlanError):
        validate_plan(plan, builder_id="alice", apps_root=tmp_path)


def test_validate_plan_requires_a_builder_id(tmp_path):
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="a.py", content="x"),))
    with pytest.raises(PlanError):
        validate_plan(plan, builder_id="", apps_root=tmp_path)


def test_mcp_call_missing_server_or_tool_is_refused(tmp_path):
    plan = Plan(app_name="widget", entries=(McpCall(server="", tool="ask"),))
    with pytest.raises(PlanError):
        validate_plan(plan, builder_id="alice", apps_root=tmp_path)


def test_valid_mcp_call_passes_structural_validation(tmp_path):
    plan = Plan(app_name="widget", entries=(McpCall(server="nestor", tool="nestor_ask", args={"q": "hi"}),))
    # No FileWrite entries, so nothing to resolve — but it must not raise.
    assert validate_plan(plan, builder_id="alice", apps_root=tmp_path) == []


def test_plan_payload_asserting_its_own_builder_id_is_refused():
    payload = {
        "builder_id": "someone-else",
        "app_name": "widget",
        "entries": [{"kind": "file_write", "dest_path": "a.py", "content": "x"}],
    }
    with pytest.raises(PlanError):
        plan_from_dict(payload)


def test_entry_missing_required_field_is_refused():
    with pytest.raises(PlanError):
        plan_from_dict({"app_name": "widget", "entries": [{"kind": "file_write", "dest_path": "a.py"}]})


def test_unknown_entry_kind_is_refused():
    with pytest.raises(PlanError):
        plan_from_dict({"app_name": "widget", "entries": [{"kind": "delete_everything"}]})


def test_plan_round_trips_through_dict():
    plan = Plan(
        app_name="widget",
        entries=(
            FileWrite(dest_path="src/app.py", content="print(1)", executable=True),
            McpCall(server="nestor", tool="nestor_ask", args={"q": "hi"}),
        ),
    )
    payload = plan_to_dict(plan)
    assert "builder_id" not in payload
    restored = plan_from_dict(payload)
    assert restored == plan


def test_entry_to_dict_shape():
    fw = FileWrite(dest_path="a.py", content="x")
    d = entry_to_dict(fw)
    assert d == {"dest_path": "a.py", "content": "x", "executable": False, "kind": "file_write"}
