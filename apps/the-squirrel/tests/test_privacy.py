"""
Privacy divider tests.

Invariants pinned:
  - the app makes ZERO network calls of its own — search renders links even
    with the socket layer booby-trapped
  - consent.online: absent file -> factory ON; damaged file -> everything OFF
  - ONLINE off -> search renders no outbound paths at all
  - the trail renders receipts as plain sentences, denials called out
  - GO QUIET flips online off in one motion, and the flip is receipted
"""
import pytest

from sap.core import consent, receipts


def test_absent_settings_mean_factory_defaults():
    assert consent.online() is True
    assert consent.damaged() is False


def test_set_online_persists():
    consent.set_online(False)
    assert consent.online() is False
    consent.set_online(True)
    assert consent.online() is True


def test_damaged_settings_fail_closed():
    p = consent.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert consent.damaged() is True
    assert consent.online() is False          # a wound, not a preference
    consent.set_online(True)                  # flipping the switch is the repair
    assert consent.damaged() is False
    assert consent.online() is True


def test_search_never_touches_a_socket(monkeypatch):
    import urllib.request

    def _boom(*a, **kw):
        raise AssertionError("the app touched a socket — egress is links only")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    from responder.commands.search import cmd_search
    out = cmd_search(["wikipedia", "Oscar", "Mann"])
    assert "en.wikipedia.org/wiki/Oscar_Mann" in out   # a link, not a fetch


def test_search_offline_renders_no_outbound_paths():
    consent.set_online(False)
    from responder.commands.search import cmd_search
    out = cmd_search(["Oscar", "Mann"])
    assert "https://" not in out
    assert "ONLINE" in out                     # points at the switch, honestly


def test_trail_sentences_name_who_and_call_out_denials():
    import sap.core.gate as gate
    from squirrel_app import _trail_sentence
    with gate.actor("jeles"):
        with pytest.raises(gate.PermissionDenied):
            gate.authorized("export")
    row = receipts.tail(limit=1)[0]
    sentence = _trail_sentence(row)
    assert "Jeles" in sentence
    assert "carried the tree out (export)" in sentence
    assert "blocked" in sentence


def test_go_quiet_is_one_motion_and_receipted():
    import squirrel_app

    class _Sink:
        def _send_json(self, obj, status=200):
            self.sent = obj

    consent.set_online(True)
    sink = _Sink()
    squirrel_app._handle_quiet(sink, {})
    assert consent.online() is False
    assert sink.sent == {"quiet": True}
    row = receipts.tail(limit=1)[0]
    assert row["tool"] == "cmd:quiet" and row["outcome"] == "ok"


def test_online_flip_is_receipted():
    import squirrel_app

    class _Sink:
        def _send_json(self, obj, status=200):
            self.sent = obj

    squirrel_app._handle_privacy(_Sink(), {"online": True})
    row = receipts.tail(limit=1)[0]
    assert row["tool"] == "cmd:privacy.online" and row["detail"] == "on"
