"""CLI: `live` refuses (non-zero, no order); `recommend`/`fetch` produce JSON on
stub data."""
import io
import json
from contextlib import redirect_stdout

from njord.cli import main


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    out = buf.getvalue()
    return code, out


def test_recommend_produces_json():
    code, out = _run(["recommend", "AAPL", "MSFT", "NVDA"])
    assert code == 0
    data = json.loads(out)
    assert data["count"] == 3
    assert len(data["ideas"]) == 3
    for idea in data["ideas"]:
        assert idea["provenance"]["source_ids"]  # non-empty provenance


def test_fetch_produces_json():
    code, out = _run(["fetch", "AAPL"])
    assert code == 0
    data = json.loads(out)
    assert data["ticker"] == "AAPL"
    assert data["quote"]["provenance"]["source_id"] == "STUB"
    assert data["bar_count"] > 0


def test_live_refuses_nonzero_no_order():
    code, out = _run(["live", "AAPL"])
    assert code != 0  # non-zero exit
    data = json.loads(out)
    assert data["refused"] is True
    assert data["order_placed"] is False
    assert data["gate"]["authorized"] is False


def test_backtest_runs_on_stub():
    code, out = _run(["backtest", "AAPL"])
    assert code == 0
    data = json.loads(out)
    assert data["result"]["symbol"] == "AAPL"
    assert "look-ahead-safe" in data["result"]["note"].lower()


def test_paper_fills_via_stub():
    code, out = _run(["paper", "AAPL", "--qty", "5"])
    assert code == 0
    data = json.loads(out)
    assert data["mode"] == "paper"
    assert data["fill"]["simulated"] is True
    assert data["fill"]["filled_qty"] == 5


def test_kill_then_paper_refuses():
    code, _ = _run(["kill"])
    assert code == 0
    code2, out2 = _run(["paper", "AAPL"])
    data = json.loads(out2)
    assert data["refused"] is True
    assert code2 != 0
