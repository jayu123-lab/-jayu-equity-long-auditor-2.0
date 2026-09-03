from __future__ import annotations

from .models import MarketSnapshot, Signal

MIN_THESIS_LENGTH = 20


def _meaningful(text: str) -> bool:
    return len(text.strip()) >= MIN_THESIS_LENGTH


def market_regime_score(regime: list[MarketSnapshot]) -> int:
    if not regime:
        return 0
    return round(sum(item.trend_score for item in regime) / len(regime))


def prefilter_symbol(snapshot: MarketSnapshot, regime_score: int) -> tuple[bool, str]:
    if regime_score < 50:
        return False, "market regime is too weak"
    if snapshot.trend_score < 75:
        return False, "symbol trend is not strong enough"
    if snapshot.close < snapshot.sma_20:
        return False, "price is below 20-day average"
    if snapshot.relative_volume < 0.45:
        return False, "relative volume is too low"
    return True, "passed"


def reward_to_risk(signal: Signal) -> float:
    risk = signal.entry - signal.stop_loss
    reward = signal.take_profit_1 - signal.entry
    if risk <= 0:
        return 0.0
    return reward / risk


def validate_signal(signal: Signal, min_confidence: int) -> tuple[bool, str]:
    if signal.direction != "LONG":
        return False, "direction must be LONG"
    if signal.execution:
        return False, "execution must remain false"
    if not signal.audit:
        return False, "audit must remain true"
    if not _meaningful(signal.reason):
        return False, f"thesis (reason) must be at least {MIN_THESIS_LENGTH} characters"
    if not _meaningful(signal.invalidation):
        return False, f"invalidation must be at least {MIN_THESIS_LENGTH} characters"
    if signal.confidence < min_confidence:
        return False, "confidence below threshold"
    if signal.stop_loss >= signal.entry:
        return False, "stop loss must be below entry"
    if signal.take_profit_1 <= signal.entry or signal.take_profit_2 <= signal.take_profit_1:
        return False, "targets must be above entry and ordered"
    if reward_to_risk(signal) < 2:
        return False, "reward/risk below 1:2"
    return True, "passed"

