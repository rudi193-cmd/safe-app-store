"""is_live_authorized() is False by default; stays False without the explicit
confirmation + paper record; only clears when ALL conditions are met."""
from njord.config import GateConfig
from njord.risk.gate import LiveGate, is_live_authorized


def test_false_by_default():
    assert is_live_authorized() is False
    assert LiveGate().is_live_authorized() is False


def test_false_with_only_credential(monkeypatch):
    monkeypatch.setenv("NJORD_LIVE_CREDENTIAL", "some-key")
    monkeypatch.delenv("NJORD_I_UNDERSTAND_LIVE", raising=False)
    g = LiveGate()
    # Even with a huge paper record, missing confirmation keeps it closed.
    assert g.is_live_authorized(paper_fills=999, paper_days=999) is False


def test_false_with_only_confirmation(monkeypatch):
    monkeypatch.delenv("NJORD_LIVE_CREDENTIAL", raising=False)
    monkeypatch.setenv("NJORD_I_UNDERSTAND_LIVE", "I-UNDERSTAND-LIVE")
    g = LiveGate()
    assert g.is_live_authorized(paper_fills=999, paper_days=999) is False


def test_false_without_paper_record(monkeypatch):
    monkeypatch.setenv("NJORD_LIVE_CREDENTIAL", "some-key")
    monkeypatch.setenv("NJORD_I_UNDERSTAND_LIVE", "I-UNDERSTAND-LIVE")
    g = LiveGate()
    # Credential + confirmation present, but no track record.
    assert g.is_live_authorized(paper_fills=0, paper_days=0) is False


def test_wrong_confirmation_phrase_stays_closed(monkeypatch):
    monkeypatch.setenv("NJORD_LIVE_CREDENTIAL", "some-key")
    monkeypatch.setenv("NJORD_I_UNDERSTAND_LIVE", "yes please")
    g = LiveGate()
    assert g.is_live_authorized(paper_fills=999, paper_days=999) is False


def test_clears_only_when_all_conditions_met(monkeypatch):
    cfg = GateConfig()
    monkeypatch.setenv("NJORD_LIVE_CREDENTIAL", "some-key")
    monkeypatch.setenv("NJORD_I_UNDERSTAND_LIVE", cfg.live_confirm_phrase)
    g = LiveGate(cfg)
    ok = g.is_live_authorized(
        paper_fills=cfg.min_paper_fills, paper_days=cfg.min_paper_days
    )
    assert ok is True
    status = g.status(paper_fills=cfg.min_paper_fills, paper_days=cfg.min_paper_days)
    assert status.authorized is True
    assert status.has_credential and status.has_confirmation and status.meets_paper_record
