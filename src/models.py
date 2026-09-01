from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MarketSnapshot(BaseModel):
    symbol: str
    close: float
    change_1d_pct: float
    sma_20: float
    sma_50: float
    sma_200: float
    volume: float
    volume_avg_20: float
    atr_14: float
    relative_volume: float
    trend_score: int


class Signal(BaseModel):
    agent: str = "jayu_equity_long_auditor"
    mode: Literal["audit_only"] = "audit_only"
    symbol: str
    direction: Literal["LONG"]
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    confidence: int = Field(ge=0, le=100)
    timeframe: str
    setup: str
    reason: str
    invalidation: str
    execution: bool = False
    audit: bool = True

    @field_validator("take_profit_1", "take_profit_2")
    @classmethod
    def targets_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("targets must be positive")
        return value


class Decision(BaseModel):
    action: Literal["SIGNAL", "NO_TRADE"]
    signal: Signal | None = None
    notes: str = ""

