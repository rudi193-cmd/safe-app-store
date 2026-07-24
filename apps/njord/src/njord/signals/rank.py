"""rank.py — turn candidate symbols into ranked ideas WITH provenance.

Each Idea carries:
  - a score and a side (long/flat),
  - a human-readable rationale naming the exact indicator values,
  - a provenance block: the source_ids and a sample of the bars that drove it.

An idea that cannot cite a registered source is rejected here — this is the
enforcement point for "a recommendation that can't cite a source is a bug".
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from ..data.models import Bar
from ..data.registry import SourceRegistry, UnregisteredSourceError
from . import features


@dataclass
class Idea:
    symbol: str
    score: float
    side: str                       # "long" or "flat"
    rationale: str
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _features_for(bars: list[Bar]) -> dict:
    closes = [b.close for b in bars]
    return {
        "last": closes[-1] if closes else None,
        "sma20": features.sma(closes, 20),
        "sma50": features.sma(closes, 50),
        "mom10": features.momentum(closes, 10),
        "rsi14": features.rsi(closes, 14),
    }


def _score(f: dict) -> tuple[float, str, str]:
    """Transparent scoring. Positive momentum + price above its moving averages,
    penalized when RSI looks overbought. Returns (score, side, rationale)."""
    score = 0.0
    parts: list[str] = []

    mom = f.get("mom10")
    if mom is not None:
        score += mom * 100.0
        parts.append(f"10-bar momentum {mom * 100:+.2f}%")

    last, sma20, sma50 = f.get("last"), f.get("sma20"), f.get("sma50")
    if last is not None and sma20 is not None:
        if last > sma20:
            score += 1.0
            parts.append("price > SMA20 (uptrend)")
        else:
            score -= 1.0
            parts.append("price < SMA20 (downtrend)")
    if sma20 is not None and sma50 is not None:
        if sma20 > sma50:
            score += 1.0
            parts.append("SMA20 > SMA50 (bullish cross)")
        else:
            score -= 0.5
            parts.append("SMA20 < SMA50")

    rsi = f.get("rsi14")
    if rsi is not None:
        parts.append(f"RSI14 {rsi:.1f}")
        if rsi > 70:
            score -= 1.5
            parts.append("overbought penalty")
        elif rsi < 30:
            score += 0.5
            parts.append("oversold bonus")

    side = "long" if score > 0 else "flat"
    rationale = "; ".join(parts) if parts else "insufficient data"
    return round(score, 4), side, rationale


def build_idea(symbol: str, bars: list[Bar], registry: SourceRegistry) -> Idea:
    """Build one ranked idea, enforcing that its bars cite registered sources."""
    if not bars:
        raise ValueError(f"no bars for {symbol!r} — cannot form an idea")

    # ENFORCEMENT: every bar's source must be registered. No registered source
    # => the idea is a bug and we refuse to emit it.
    source_ids = sorted({b.provenance.source_id for b in bars})
    for sid in source_ids:
        registry.require(sid)  # raises UnregisteredSourceError if not registered

    f = _features_for(bars)
    score, side, rationale = _score(f)

    provenance = {
        "source_ids": source_ids,
        "sources": [
            {
                "id": s.id,
                "authority": s.authority,
                "trust": int(s.trust),
                "public": s.public,
            }
            for s in (registry.get(sid) for sid in source_ids)
        ],
        "bar_count": len(bars),
        "first_bar": bars[0].to_dict(),
        "last_bar": bars[-1].to_dict(),
        "fetched_at": sorted({b.provenance.fetched_at for b in bars}),
        "features": f,
    }
    return Idea(
        symbol=symbol.upper(),
        score=score,
        side=side,
        rationale=rationale,
        provenance=provenance,
    )


def rank_candidates(
    bars_by_symbol: dict[str, list[Bar]], registry: SourceRegistry
) -> list[Idea]:
    """Rank all candidates highest-score-first. Every returned idea carries a
    non-empty provenance block or it is not returned at all."""
    ideas: list[Idea] = []
    for symbol, bars in bars_by_symbol.items():
        try:
            idea = build_idea(symbol, bars, registry)
        except UnregisteredSourceError:
            # A candidate whose data cannot cite a registered source is dropped,
            # never silently emitted. Re-raise so the bug is visible.
            raise
        ideas.append(idea)
    ideas.sort(key=lambda i: i.score, reverse=True)
    return ideas
