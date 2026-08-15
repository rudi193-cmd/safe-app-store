"""End to end over a real loopback socket: ask, answer, and the gate closing.

The store copy of this app previously shipped only the two static UIs, whose
every `fetch()` went to a host that lived outside the repository. Nothing could
run and nothing could be tested. These tests exist mostly to make that
un-reoccurrable: they start the real server and drive the real routes.
"""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

import pytest

from playgate import catalog, install, server
from playgate.disposition import Log

ROSTER = ("kid1",)


@pytest.fixture()
def running(tmp_path, monkeypatch):
    entry = {
        "id": "example", "title": "Example", "blurb": "A game.",
        "age_band": "7+", "abi": "universal", "package": "com.example.game",
        "version": "1.0", "apk_path": "example.apk",
        "interruption": {"provenance": "assumed"},
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"apps": [entry]}))
    apps = catalog.load(catalog_path)

    apk = tmp_path / "example.apk"
    apk.write_bytes(b"bytes")
    entry_sha = install.digest(apk)
    catalog_path.write_text(json.dumps({"apps": [dict(entry, sha256=entry_sha)]}))
    apps = catalog.load(catalog_path)

    log = Log(path=tmp_path / "requests.jsonl", roster=ROSTER)
    httpd = server.serve(apps, log, port=0, apk_root=tmp_path)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], log, apk
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def call(port, method, path, body=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    parsed = json.loads(raw) if raw and response.getheader("Content-Type", "").startswith(
        "application/json") else raw
    return response.status, parsed


def test_the_kid_ui_is_served(running):
    port, _, _ = running
    status, body = call(port, "GET", "/kid/")
    assert status == 200 and b"Playgate" in body


def test_the_catalog_route_answers(running):
    """The route the kid UI's very first fetch() calls. In the state this app
    was merged in, this returned a 404 from a server that was not in the repo.
    """
    port, _, _ = running
    status, body = call(port, "GET", "/api/catalog")
    assert status == 200
    assert [a["id"] for a in body["apps"]] == ["example"]
    assert body["apps"][0]["interruption"]["provenance"] == "assumed"


def test_the_catalog_view_carries_no_score(running):
    port, _, _ = running
    _, body = call(port, "GET", "/api/catalog")
    assert "score" not in body["apps"][0]


def test_the_roster_is_served_so_the_kid_ui_need_not_ask_for_a_name(running):
    port, _, _ = running
    status, body = call(port, "GET", "/api/roster")
    assert status == 200 and body["subjects"] == list(ROSTER)


def test_a_request_appears_in_the_parent_inbox(running):
    port, _, _ = running
    status, created = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "example", "asked_by": "Maya",
    })
    assert status == 201
    status, inbox = call(port, "GET", "/api/requests?view=open")
    assert status == 200
    assert [r["request_id"] for r in inbox["requests"]] == [created["request"]["request_id"]]


def test_a_request_for_an_unknown_app_is_refused(running):
    port, _, _ = running
    status, body = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "not-in-catalog", "asked_by": "Maya",
    })
    assert status == 400 and "not-in-catalog" in body["error"]


def test_a_request_from_someone_off_the_roster_is_refused(running):
    port, _, _ = running
    status, body = call(port, "POST", "/api/requests", {
        "subject_id": "kid9", "app_id": "example", "asked_by": "Maya",
    })
    assert status == 400 and "roster" in body["error"]


def test_a_grant_without_a_reason_is_refused(running):
    port, _, _ = running
    _, created = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "example", "asked_by": "Maya",
    })
    rid = created["request"]["request_id"]
    status, body = call(port, "POST", f"/api/requests/{rid}/answer", {
        "granted": True, "by": "Parent", "reason": "",
    })
    assert status == 400 and "reason is required" in body["error"]


def test_granting_attempts_the_install_rather_than_printing_a_command(running, monkeypatch):
    """The gate closes here.

    Previously the UI's success message was an instruction to go and run
    `python3 -m playgate install --request-id X` in a terminal, which is a
    to-do list with a reason field rather than a gate.
    """
    port, log, _ = running
    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/adb")
    monkeypatch.setattr(
        install.subprocess, "run",
        lambda *a, **k: type("C", (), {"returncode": 0, "stdout": "Success", "stderr": ""})(),
    )

    _, created = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "example", "asked_by": "Maya",
    })
    rid = created["request"]["request_id"]
    status, body = call(port, "POST", f"/api/requests/{rid}/answer", {
        "granted": True, "by": "Parent", "reason": "quiet game, fine for Saturday",
    })
    assert status == 200
    assert body["install"]["ok"] is True
    assert [r["kind"] for r in log.history(rid)] == ["request", "answer", "install"]


def test_a_failed_install_is_reported_and_logged(running):
    """adb is genuinely absent on the CI runner, so this exercises the real
    failure path rather than a mocked one."""
    port, log, _ = running
    _, created = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "example", "asked_by": "Maya",
    })
    rid = created["request"]["request_id"]
    status, body = call(port, "POST", f"/api/requests/{rid}/answer", {
        "granted": True, "by": "Parent", "reason": "ok",
    })
    assert status == 200
    assert body["install"]["ok"] is False
    assert log.current(rid)["disposition"] == "install_failed"


def test_a_refusal_does_not_install(running):
    port, log, _ = running
    _, created = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "example", "asked_by": "Maya",
    })
    rid = created["request"]["request_id"]
    status, body = call(port, "POST", f"/api/requests/{rid}/answer", {
        "granted": False, "by": "Parent", "reason": "not before homework",
    })
    assert status == 200 and "install" not in body
    assert [r["kind"] for r in log.history(rid)] == ["request", "answer"]


def test_the_answer_row_snapshots_the_evidence(running):
    port, log, _ = running
    _, created = call(port, "POST", "/api/requests", {
        "subject_id": "kid1", "app_id": "example", "asked_by": "Maya",
    })
    rid = created["request"]["request_id"]
    call(port, "POST", f"/api/requests/{rid}/answer",
         {"granted": False, "by": "Parent", "reason": "no"})
    answer = [r for r in log.history(rid) if r["kind"] == "answer"][0]
    assert answer["interruption_at_decision"]["provenance"] == "assumed"


def test_answering_an_unknown_request_is_a_404(running):
    port, _, _ = running
    status, _ = call(port, "POST", "/api/requests/deadbeef/answer",
                     {"granted": True, "by": "P", "reason": "r"})
    assert status == 404


def test_static_traversal_is_refused(running):
    port, _, _ = running
    status, _ = call(port, "GET", "/kid/../../safe-app-manifest.json")
    assert status != 200


# -- the child's own view -----------------------------------------------------

def test_a_child_can_read_back_what_they_asked_for(running):
    """The kid UI's state read. Without it a child sees no trace of a request
    after a reload, and the only way to find out what happened is to ask again.
    """
    port, _, _ = running
    status, _ = call(port, "POST", "/api/requests",
                     {"subject_id": "kid1", "app_id": "example", "asked_by": "kid1"})
    assert status == 201

    status, body = call(port, "GET", "/api/requests?subject=kid1")
    assert status == 200
    assert [r["app_id"] for r in body["requests"]] == ["example"]
    assert body["requests"][0]["disposition"] == "open"


def test_the_childs_view_carries_the_answer_and_its_reason(running):
    port, log, _ = running
    _, created = call(port, "POST", "/api/requests",
                      {"subject_id": "kid1", "app_id": "example", "asked_by": "kid1"})
    request_id = created["request"]["request_id"]
    call(port, "POST", f"/api/requests/{request_id}/answer",
         {"granted": False, "by": "parent", "reason": "not before homework"})

    _, body = call(port, "GET", "/api/requests?subject=kid1")
    answered = body["requests"][0]
    assert answered["disposition"] == "refused"
    # Shown to the child, not merely recorded for the adult.
    assert answered["reason"] == "not before homework"


def test_the_childs_view_refuses_a_subject_not_on_the_roster(running):
    port, _, _ = running
    status, body = call(port, "GET", "/api/requests?subject=someone-else")
    assert status == 400
    assert "roster" in body["error"]


def test_a_request_with_no_chosen_subject_is_refused(running):
    """The picker used to default to the first child on the roster, so a reload
    reattributed the next request to a sibling. An empty subject is now a
    refusal the host can make, rather than a state it cannot see.
    """
    port, log, _ = running
    status, body = call(port, "POST", "/api/requests",
                        {"subject_id": "", "app_id": "example", "asked_by": ""})
    assert status == 400
    assert "not a choice" in body["error"]
    assert log.rows() == []          # and nothing was written
