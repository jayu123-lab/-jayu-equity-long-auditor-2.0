"""JAYU EQUITY CONTEXT — snapshot tecnico enriquecido y auditable por simbolo.

Incluye horizonte swing (weekly + daily), estructura, ATR, rango 52 semanas,
para que las evidencias tecnicas no dependan de ruido M1/M5 (seccion 5/11).
Si faltan datos, los campos se dejan en None (nunca se inventan).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
import yfinance as yf


def _atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    required = ["High", "Low", "Close"]
    if any(c not in df.columns for c in required):
        return None
    try:
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        val = tr.rolling(period).mean().iloc[-1]
        return float(val) if val == val else None
    except Exception:
        return None


def _sma(s: pd.Series, n: int) -> Optional[float]:
    try:
        v = s.rolling(n).mean().iloc[-1]
        return float(v) if v == v else None
    except Exception:
        return None


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


@dataclass
class EquityContext:
    symbol: str
    close: Optional[float] = None
    change_1d_pct: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    sma_20w: Optional[float] = None      # media simple de cierre semanal
    sma_50w: Optional[float] = None
    atr_14: Optional[float] = None
    atr_pct: Optional[float] = None
    relative_volume: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    range_pos_52w: Optional[float] = None
    weekly_trend_score: Optional[int] = None
    weekly_green_pct: Optional[float] = None  # % de semanas verdes en 12w
    trend_score: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(cls, symbol: str) -> "EquityContext":
        """Fetches daily+weekly, construye el contexto técnico swing."""
        ctx = cls(symbol=symbol.upper())
        try:
            daily = yf.download(ctx.symbol, period="1y", interval="1d",
                                progress=False, auto_adjust=True)
            weekly = yf.download(ctx.symbol, period="2y", interval="1wk",
                                 progress=False, auto_adjust=True)
        except Exception:
            return ctx

        if daily is None or daily.empty:
            return ctx
        if isinstance(daily.columns, pd.MultiIndex):
            daily.columns = daily.columns.get_level_values(0)
        close_s = daily["Close"].dropna()
        if close_s.empty:
            return ctx

        close = float(close_s.iloc[-1])
        ctx.close = round(close, 4)
        ctx.change_1d_pct = round((close / float(close_s.iloc[-2]) - 1.0) * 100, 3) if len(close_s) > 1 else None
        ctx.sma_20 = _sma(close_s, 20)
        ctx.sma_50 = _sma(close_s, 50)
        ctx.sma_200 = _sma(close_s, 200)

        vol_s = daily["Volume"].dropna()
        ctx.relative_volume = round(float(vol_s.iloc[-1]) / float(vol_s.rolling(20).mean().iloc[-1]), 3) \
            if not vol_s.empty and len(vol_s) > 20 else None

        atr = _atr(daily)
        ctx.atr_14 = round(atr, 4) if atr else None
        ctx.atr_pct = round(atr / close * 100, 3) if atr and close else None

        ctx.high_52w = round(float(close_s.max()), 4)
        ctx.low_52w = round(float(close_s.min()), 4)
        if ctx.high_52w and ctx.low_52w and ctx.low_52w < ctx.high_52w:
            ctx.range_pos_52w = round((close - ctx.low_52w) / (ctx.high_52w - ctx.low_52w), 4)

        # Score de tendencia diaria (misma formula que market_data).
        ts = 0
        ts += 25 if ctx.sma_20 and close > ctx.sma_20 else 0
        ts += 25 if ctx.sma_50 and close > ctx.sma_50 else 0
        ts += 25 if ctx.sma_200 and close > ctx.sma_200 else 0
        ts += 25 if ctx.sma_20 and ctx.sma_50 and ctx.sma_200 and ctx.sma_20 > ctx.sma_50 > ctx.sma_200 else 0
        ctx.trend_score = ts

        # Contexto semanal (swing): evita ruido diario.
        if weekly is not None and not weekly.empty:
            if isinstance(weekly.columns, pd.MultiIndex):
                weekly.columns = weekly.columns.get_level_values(0)
            wclose = weekly["Close"].dropna()
            if not wclose.empty:
                ctx.sma_20w = _sma(wclose, 20)
                ctx.sma_50w = _sma(wclose, 50)
                wct = 0
                wct += 34 if ctx.sma_20w and float(wclose.iloc[-1]) > ctx.sma_20w else 0
                wct += 33 if ctx.sma_50w and float(wclose.iloc[-1]) > ctx.sma_50w else 0
                wct += 33 if ctx.sma_20w and ctx.sma_50w and ctx.sma_20w > ctx.sma_50w else 0
                ctx.weekly_trend_score = wct
                last12 = wclose.tail(12)
                ctx.weekly_green_pct = round((last12 > last12.shift(1)).sum() / len(last12), 3) \
                    if len(last12) > 1 else None

        return ctx

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any]) -> "EquityContext":
        """Construye contexto desde un snapshot (market_data) ya capturado."""
        return cls(
            symbol=str(snap.get("symbol") or "").upper(),
            close=_num(snap.get("close")),
            change_1d_pct=_num(snap.get("change_1d_pct")),
            sma_20=_num(snap.get("sma_20")),
            sma_50=_num(snap.get("sma_50")),
            sma_200=_num(snap.get("sma_200")),
            relative_volume=_num(snap.get("relative_volume")),
            trend_score=_num(snap.get("trend_score")),
            metadata={"from_snapshot": True},
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "symbol": self.symbol, "close": self.close,
            "change_1d_pct": self.change_1d_pct, "sma_20": self.sma_20,
            "sma_50": self.sma_50, "sma_200": self.sma_200,
            "sma_20w": self.sma_20w, "sma_50w": self.sma_50w,
            "atr_14": self.atr_14, "atr_pct": self.atr_pct,
            "relative_volume": self.relative_volume,
            "high_52w": self.high_52w, "low_52w": self.low_52w,
            "range_pos_52w": self.range_pos_52w,
            "weekly_trend_score": self.weekly_trend_score,
            "weekly_green_pct": self.weekly_green_pct,
            "trend_score": self.trend_score,
        }
        return out