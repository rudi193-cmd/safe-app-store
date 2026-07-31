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


@pytest.mark.parametrize(
    "app_name",
    [
        "../../VICTIM",
        "../sibling",
        "/etc/evil",
        "a/b",
        "..",
        ".",
    ],
)
def test_app_name_path_traversal_is_refused_at_construction(app_name):
    """Audit finding (2026-08-01, CRITICAL): app_name was only checked for
    non-emptiness, so Plan(app_name="../../VICTIM", ...) resolved its
    allow_root OUTSIDE apps_root entirely, and every later containment
    check passed because it was checking containment relative to the
    already-escaped root. This must be refused before a Plan can even be
    constructed, the same way builder_id's charset is enforced elsewhere."""
    with pytest.raises(PlanError):
        Plan(app_name=app_name, entries=(FileWrite(dest_path="a.py", content="x"),))


def test_app_name_traversal_is_also_refused_if_post_init_were_bypassed(tmp_path):
    """Defense in depth, not just documentation: validate_plan() re-checks
    app_name's charset independently of Plan.__post_init__, so a Plan
    constructed by skipping __post_init__ (object.__new__ +
    object.__setattr__, simulating some future refactor that stops calling
    it) still can't reach _contain_file_write's containment math with an
    unvalidated app_name."""
    plan = object.__new__(Plan)
    object.__setattr__(plan, "app_name", "../../escaped")
    object.__setattr__(plan, "entries", (FileWrite(dest_path="a.py", content="x"),))

    apps_root = tmp_path / "apps"
    with pytest.raises(PlanError, match="charset"):
        validate_plan(plan, builder_id="alice", apps_root=apps_root)
    assert not (tmp_path / "escaped").exists()


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


@pytest.mark.parametrize("dest_path", ["", ".", "./"])
def test_dest_path_resolving_to_the_app_directory_itself_is_refused(tmp_path, dest_path):
    """Audit finding (2026-08-01, HIGH): dest_path="" / "." / "./" all
    normalize to allow_root itself, and the old check explicitly permitted
    dest == allow_root (borrowed from seam_install.py, where the allow root
    may legitimately BE a single-file install target). A FileWrite's
    destination must always be strictly inside the app directory, never the
    directory path itself — letting this through meant a plan could
    clobber apps/<builder_id>/<app_name> with a regular file."""
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path=dest_path, content="x"),))
    with pytest.raises(PlanError, match="strictly inside"):
        validate_plan(plan, builder_id="alice", apps_root=tmp_path)


def test_embedded_null_byte_in_dest_path_is_refused_not_a_traceback(tmp_path):
    """Audit finding (MEDIUM): a null byte in dest_path made Path.resolve()
    raise a bare ValueError that escaped PlanError's contract. resolve()
    is what actually surfaces it (pathlib construction itself doesn't
    validate), so the wrap has to be around that call specifically."""
    plan = Plan(app_name="widget", entries=(FileWrite(dest_path="a\x00.py", content="x"),))
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
