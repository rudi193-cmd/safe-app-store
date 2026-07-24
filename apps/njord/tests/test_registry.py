"""Providers register; datapoints carry source_id + fetched_at; an idea whose
data cites no registered source is rejected."""
import pytest

from njord.data.registry import (
    SourceRegistry,
    Source,
    TrustTier,
    UnregisteredSourceError,
    default_registry,
)
from njord.data.providers import StubProvider
from njord.data.models import Bar, Provenance
from njord.signals.rank import build_idea


def test_default_registry_has_stub():
    reg = default_registry()
    assert reg.is_registered("STUB")
    assert reg.get("STUB").trust == TrustTier.STUB


def test_stub_provider_registers_and_stamps_provenance():
    reg = SourceRegistry()  # bare — provider must self-register
    prov = StubProvider(reg)
    assert reg.is_registered("STUB")
    bars = prov.bars("AAPL", lookback=30)
    assert len(bars) == 30
    for b in bars:
        assert isinstance(b, Bar)
        assert b.provenance.source_id == "STUB"
        assert b.provenance.fetched_at  # non-empty ISO timestamp


def test_datapoint_carries_source_and_timestamp():
    reg = default_registry()
    prov = StubProvider(reg)
    q = prov.quote("MSFT")
    assert q.provenance.source_id == "STUB"
    d = q.to_dict()
    assert d["provenance"]["source_id"] == "STUB"


def test_unregistered_source_is_rejected():
    reg = default_registry()  # has STUB, but NOT "GHOST"
    ghost = Provenance(source_id="GHOST")
    bars = [
        Bar("XYZ", "2026-01-01", 1, 1, 1, 1, 100, ghost),
        Bar("XYZ", "2026-01-02", 1, 1, 1, 1, 100, ghost),
    ]
    with pytest.raises(UnregisteredSourceError):
        build_idea("XYZ", bars, reg)


def test_double_register_raises():
    reg = default_registry()
    with pytest.raises(ValueError):
        reg.register(Source(id="STUB", authority="STUB", trust=TrustTier.STUB))


def test_deterministic_stub_is_reproducible():
    reg = default_registry()
    p = StubProvider(reg)
    a = [b.close for b in p.bars("NVDA", lookback=50)]
    b = [x.close for x in p.bars("NVDA", lookback=50)]
    assert a == b
