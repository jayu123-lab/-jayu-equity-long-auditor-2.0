from src.equity.evidence import CorrelationGroup, make_evidence
from src.equity.engine import BayesianEngine, compute_posterior, freshness_decay
from src.equity.quality_gate import classify_state, check_quality, expectancy
from src.equity.regime import classify_market_regime
from src.models import MarketSnapshot


def snap(symbol: str, trend_score: int, above50=True) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol, close=100, change_1d_pct=1.0, sma_20=99, sma_50=97,
        sma_200=90, volume=1_000_000, volume_avg_20=800_000, atr_14=3,
        relative_volume=1.0, trend_score=trend_score,
    )


def ev(category: str, direction: str = "BULLISH", strength: float = 0.6,
       group: str = None, rel: float = 0.7) -> "EvidencePacket":
    return make_evidence("NVDA", "TEST", category, f"e_{category}", direction,
                         strength, reliability=rel, correlation_group=group or category)


def test_make_evidence_normalizes():
    e = make_evidence("n vda", "test", "technical", "x", "bullish", 1.5, reliability=0.5)
    assert e.symbol == "N VDA"
    assert e.agent == "TEST"
    assert e.direction == "BULLISH"
    assert e.strength == 1.0
    assert e.correlation_group == "STRUCTURE"  # default de TECHNICAL


def test_correlation_reduces_double_counting():
    eng = BayesianEngine()
    eps = ev("FUNDAMENTAL", "BULLISH", 0.8, CorrelationGroup.FUNDAMENTALS)
    rev = ev("FUNDAMENTAL", "BULLISH", 0.8, CorrelationGroup.FUNDAMENTALS)
    r1 = eng.evaluate("NVDA", [eps])
    r2 = eng.evaluate("NVDA", [eps, rev])
    # el posterior sube menos con la segunda evidencia del mismo grupo
    assert r2["posterior_long"] > r1["posterior_long"]
    # la segunda evidencia pesa ~ 1/sqrt(2) de la primera
    second = [t for t in r2["traces"] if t["evidence_type"] == "e_FUNDAMENTAL" and t["group_rank"] == 2][0]
    first = [t for t in r2["traces"] if t["group_rank"] == 1][0]
    assert second["log_lr"] < first["log_lr"]


def test_no_evidence_posterior_equals_prior():
    eng = BayesianEngine()
    r = eng.evaluate("NVDA", [], prior_long=0.5)
    assert abs(r["posterior_long"] - 0.5) < 1e-9


def test_strong_bullish_pushes_posterior_up():
    eng = BayesianEngine()
    r = eng.evaluate("NVDA", [
        ev("FUNDAMENTAL", "BULLISH", 0.9),
        ev("TECHNICAL", "BULLISH", 0.9),
        ev("SECTOR", "BULLISH", 0.9),
        ev("MACRO", "BULLISH", 0.9),
        ev("EARNINGS", "BULLISH", 0.9),
        ev("CATALYST", "BULLISH", 0.9),
    ], prior_long=0.4)
    assert r["posterior_long"] > 0.6


def test_bearish_evidence_negates():
    eng = BayesianEngine()
    r = eng.evaluate("NVDA", [
        ev("FUNDAMENTAL", "BEARISH", 0.9),
        ev("TECHNICAL", "BEARISH", 0.9),
        ev("SECTOR", "BEARISH", 0.9),
        ev("MACRO", "BEARISH", 0.9),
        ev("EARNINGS", "BEARISH", 0.9),
        ev("CATALYST", "BEARISH", 0.9),
    ], prior_long=0.5)
    assert r["posterior_long"] < 0.5


def test_freshness_decay():
    assert freshness_decay(0, 10) == 1.0
    assert 0.3 < freshness_decay(10, 10) < 0.5
    assert freshness_decay(24 * 21, 24 * 21) < 0.5  # un half-life


def test_compute_posterior_returns_audit_trace():
    r = compute_posterior("NVDA", [ev("TECHNICAL", "BULLISH")], prior_long=0.5)
    assert r["engine"] == "JAYU_BAYES_ENGINE_V1"
    assert r["domain"] == "EQUITY_LONG_SWING_V1"
    assert len(r["traces"]) == 1
    assert "positive_evidence" in r


def test_classify_state_buckets():
    assert classify_state(0.55) == "IGNORE"
    assert classify_state(0.62) == "WATCH"
    assert classify_state(0.70) == "CANDIDATE"
    assert classify_state(0.80) == "BUY"


def test_check_quality_blocks_weak_evidence():
    r = check_quality(0.8, [ev("TECHNICAL")])  # 1 evidencia, 1 grupo
    assert r.state == "BUY"
    assert not r.passed()
    assert any("n_evidence" in b for b in r.blocked_reasons)


def test_check_quality_passes_rich_evidence():
    evidence = [
        ev("FUNDAMENTAL", "BULLISH", 0.7, CorrelationGroup.FUNDAMENTALS),
        ev("VALUATION", "BULLISH", 0.6, CorrelationGroup.VALUATION),
        ev("TECHNICAL", "BULLISH", 0.8, CorrelationGroup.TREND),
        ev("SECTOR", "BULLISH", 0.7, CorrelationGroup.SECTOR),
        ev("EARNINGS", "BULLISH", 0.7, CorrelationGroup.EARNINGS_EXPECTATIONS),
    ]
    r = check_quality(0.8, evidence, engine_result={
        "uncertainty": 0.2,
    })
    assert r.state == "BUY"
    assert r.passed()


def test_expectancy():
    assert abs(expectancy(0.5, 1.0) - 0.0) < 1e-9
    assert expectancy(0.5, 2.2) > 0.5
    assert expectancy(0.3, 2.2) < 0


def test_regime_bull_market_offsets_zero():
    r = classify_market_regime([snap("SPY", 100), snap("QQQ", 80), snap("IWM", 70)],
                               vix_level=14)
    assert "BULL_MARKET" in r.tags
    assert r.buy_threshold_offset == 0.0
    assert r.prior_adjustment > 1.0


def test_regime_bear_blocking():
    r = classify_market_regime([snap("SPY", 10), snap("QQQ", 15)],
                               vix_level=35)
    assert "BEAR_MARKET" in r.tags
    assert "HIGH_VOL" in r.tags
    assert r.buy_threshold_offset > 0.05
    assert r.prior_adjustment < 1.0


def test_regime_correction_threshold():
    r = classify_market_regime([snap("SPY", 45), snap("QQQ", 40)],
                               vix_level=22)
    assert "CORRECTION" in r.tags
    assert r.buy_threshold_offset == 0.06