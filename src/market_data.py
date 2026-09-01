from __future__ import annotations

import math

import pandas as pd
import yfinance as yf

from .models import MarketSnapshot


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return float(true_range.rolling(period).mean().iloc[-1])


def fetch_snapshot(symbol: str, period: str = "1y") -> MarketSnapshot | None:
    df = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)
    if df.empty or len(df) < 210:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    sma_20 = float(df["Close"].rolling(20).mean().iloc[-1])
    sma_50 = float(df["Close"].rolling(50).mean().iloc[-1])
    sma_200 = float(df["Close"].rolling(200).mean().iloc[-1])
    volume = float(df["Volume"].iloc[-1])
    volume_avg_20 = float(df["Volume"].rolling(20).mean().iloc[-1])
    atr_14 = _atr(df)
    rel_volume = volume / volume_avg_20 if volume_avg_20 else 0.0

    trend_score = 0
    trend_score += 25 if close > sma_20 else 0
    trend_score += 25 if close > sma_50 else 0
    trend_score += 25 if close > sma_200 else 0
    trend_score += 25 if sma_20 > sma_50 > sma_200 else 0

    values = [close, sma_20, sma_50, sma_200, volume, volume_avg_20, atr_14, rel_volume]
    if any(math.isnan(value) or math.isinf(value) for value in values):
        return None

    return MarketSnapshot(
        symbol=symbol.upper(),
        close=round(close, 4),
        change_1d_pct=round(((close - prev_close) / prev_close) * 100, 3),
        sma_20=round(sma_20, 4),
        sma_50=round(sma_50, 4),
        sma_200=round(sma_200, 4),
        volume=volume,
        volume_avg_20=volume_avg_20,
        atr_14=round(atr_14, 4),
        relative_volume=round(rel_volume, 3),
        trend_score=trend_score,
    )

