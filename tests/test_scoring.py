from src.models import MarketSnapshot, Signal
from src.scoring import MIN_THESIS_LENGTH, market_regime_score, prefilter_symbol, reward_to_risk, validate_signal


def snapshot(symbol: str = "NVDA", trend_score: int = 100, relative_volume: float = 1.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        close=100,
        change_1d_pct=1.2,
        sma_20=95,
        sma_50=90,
        sma_200=80,
        volume=10_000_000,
        volume_avg_20=8_000_000,
        atr_14=3,
        relative_volume=relative_volume,
        trend_score=trend_score,
    )


def signal(confidence: int = 85) -> Signal:
    return Signal(
        symbol="NVDA",
        direction="LONG",
        entry=100,
        stop_loss=95,
        take_profit_1=111,
        take_profit_2=120,
        confidence=confidence,
        timeframe="swing",
        setup="breakout",
        reason="Strong trend with clean invalidation.",
        invalidation="Daily close below 95.",
    )


def test_market_regime_score_average():
    assert market_regime_score([snapshot("SPY", 100), snapshot("QQQ", 50)]) == 75


def test_prefilter_rejects_weak_regime():
    ok, reason = prefilter_symbol(snapshot(), regime_score=25)
    assert not ok
    assert "market regime" in reason


def test_prefilter_accepts_strong_symbol_and_regime():
    ok, reason = prefilter_symbol(snapshot(), regime_score=75)
    assert ok
    assert reason == "passed"


def test_validate_signal_requires_confidence():
    ok, reason = validate_signal(signal(confidence=79), min_confidence=80)
    assert not ok
    assert "confidence" in reason


def test_validate_signal_accepts_long_audit_signal():
    ok, reason = validate_signal(signal(), min_confidence=80)
    assert ok
    assert reason == "passed"


def test_validate_signal_rejects_empty_thesis():
    s = signal()
    s.reason = ""
    ok, reason = validate_signal(s, min_confidence=80)
    assert not ok
    assert "thesis" in reason
    assert f"{MIN_THESIS_LENGTH}" in reason


def test_validate_signal_rejects_short_thesis():
    s = signal()
    s.reason = "LONG"
    ok, reason = validate_signal(s, min_confidence=80)
    assert not ok
    assert "thesis" in reason


def test_validate_signal_rejects_short_invalidation():
    s = signal()
    s.invalidation = "  "
    ok, reason = validate_signal(s, min_confidence=80)
    assert not ok
    assert "invalidation" in reason


def test_reward_to_risk():
    assert reward_to_risk(signal()) == 2.2

