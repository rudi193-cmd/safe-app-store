import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("OAKENSCROLL_DB", str(tmp_path / "office.db"))
    import office_db, web
    return office_db, web


def test_routes_without_a_socket(modules):
    db, web = modules
    status, ctype, body = web.handle("GET", "/")
    assert status == 200 and "Oakenscroll" in body
    assert web.handle("GET", "/nope")[0] == 404
    assert web.handle("POST", "/")[0] == 405


def test_scorecard_json_and_svg(modules):
    db, web = modules
    for outcome in (True, True, False):
        pid = db.state_claim(f"claim {outcome} {time.time()}", 0.7)
        db.resolve(pid, outcome)
    status, ctype, body = web.handle("GET", "/data.json")
    data = json.loads(body)
    assert data["summary"]["n"] == 3
    page = web.handle("GET", "/")[2]
    assert "<svg" in page and "circle" in page  # the curve is drawn
