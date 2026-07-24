"""`recommend` over StubProvider returns ranked ideas, each with a NON-EMPTY
provenance block tracing to a registered source."""
from njord.data.registry import default_registry
from njord.data.providers import StubProvider
from njord.signals.rank import rank_candidates


def _recommend(tickers):
    reg = default_registry()
    prov = StubProvider(reg)
    bars_by_symbol = {t: prov.bars(t, lookback=120) for t in tickers}
    return rank_candidates(bars_by_symbol, reg), reg


def test_returns_ranked_ideas():
    ideas, _ = _recommend(["AAPL", "MSFT", "NVDA", "GOOG"])
    assert len(ideas) == 4
    # Sorted descending by score.
    scores = [i.score for i in ideas]
    assert scores == sorted(scores, reverse=True)


def test_every_idea_has_nonempty_provenance():
    ideas, reg = _recommend(["AAPL", "MSFT", "NVDA"])
    for idea in ideas:
        p = idea.provenance
        assert p, "provenance block must be non-empty"
        assert p["source_ids"], "provenance must list source_ids"
        # Each cited source is actually registered.
        for sid in p["source_ids"]:
            assert reg.is_registered(sid)
        assert p["bar_count"] > 0
        assert p["first_bar"]["provenance"]["source_id"] in p["source_ids"]
        assert p["fetched_at"]  # fetch timestamps present


def test_ideas_carry_rationale():
    ideas, _ = _recommend(["AAPL", "MSFT"])
    for idea in ideas:
        assert idea.rationale
        assert idea.side in ("long", "flat")


def test_recommend_is_deterministic_offline():
    a, _ = _recommend(["AAPL", "MSFT", "NVDA"])
    b, _ = _recommend(["AAPL", "MSFT", "NVDA"])
    assert [(i.symbol, i.score) for i in a] == [(i.symbol, i.score) for i in b]
