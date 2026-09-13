"""JAYU EQUITY DATA — acceso a datos reales (yfinance) para evidencias.

Principios:
  - Solo se usan fuentes reales disponibles. Si una fuente falta, se devuelve
    un valor neutro (None / 0.0) y la evidencia se omite o queda neutra.
    NUNCA se inventan datos.
  - Cache diaria en data/cache/ para no golpear tanto la API en runs horarios.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, date, timezone, timedelta
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from ..market_data import fetch_snapshot as _fetch_snapshot

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache",
)


def _cache_path(key: str) -> str:
    day = date.today().isoformat()
    return os.path.join(_CACHE_ROOT, day, f"{key}.json")


def _cache_load(key: str) -> Optional[Any]:
    p = _cache_path(key)
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return None


def _cache_save(key: str, obj: Any) -> None:
    try:
        p = _cache_path(key)
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f and f != float("inf") and f != -float("inf") else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Tecnicos / snapshots
# ---------------------------------------------------------------------------
def fetch_snapshot(symbol: str) -> Optional[Any]:
    """Wrapper de market_data.fetch_snapshot con cache diaria."""
    key = f"snapshot_{symbol}"
    cached = _cache_load(key)
    if cached is not None:
        return cached
    snap = _fetch_snapshot(symbol)
    if snap is not None:
        _cache_save(key, snap.__dict__)
        return snap.__dict__
    return None


# ---------------------------------------------------------------------------
# Fundamentales (Ticker.info de yfinance)
# ---------------------------------------------------------------------------
def fetch_fundamentals(symbol: str) -> Optional[dict[str, Any]]:
    key = f"fund_{symbol}"
    cached = _cache_load(key)
    if cached is not None:
        return cached
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    if not info or not info.get("marketCap"):
        return None
    out = {
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "marketCap": _num(info.get("marketCap")),
        "trailingPE": _num(info.get("trailingPE")),
        "forwardPE": _num(info.get("forwardPE")),
        "priceToBook": _num(info.get("priceToBook")),
        "priceToSalesTTM": _num(info.get("priceToSalesTrailing12Months")),
        "pegRatio": _num(info.get("pegRatio")),
        "revenue": _num(info.get("totalRevenue")),
        "revenueGrowth": _num(info.get("revenueGrowth")),
        "earningsGrowth": _num(info.get("earningsGrowth")),
        "freeCashflow": _num(info.get("freeCashflow")),
        "freeCashflowYield": _num(info.get("freeCashflowYield")),
        "operatingCashflow": _num(info.get("operatingCashflow")),
        "grossMargins": _num(info.get("grossMargins")),
        "operatingMargins": _num(info.get("operatingMargins")),
        "profitMargins": _num(info.get("profitMargins")),
        "returnOnEquity": _num(info.get("returnOnEquity")),
        "returnOnAssets": _num(info.get("returnOnAssets")),
        "totalCash": _num(info.get("totalCash")),
        "totalDebt": _num(info.get("totalDebt")),
        "currentRatio": _num(info.get("currentRatio")),
        "quickRatio": _num(info.get("quickRatio")),
        "debtToEquity": _num(info.get("debtToEquity")),
        "beta": _num(info.get("beta")),
        "heldPercentInstitutions": _num(info.get("heldPercentInstitutions")),
        "heldPercentInsiders": _num(info.get("heldPercentInsiders")),
        "recommendationKey": info.get("recommendationKey"),
        "recommendationMean": _num(info.get("recommendationMean")),
        "numberOfAnalystOpinions": _num(info.get("numberOfAnalystOpinions")),
        "targetMeanPrice": _num(info.get("targetMeanPrice")),
        "targetHighPrice": _num(info.get("targetHighPrice")),
        "targetLowPrice": _num(info.get("targetLowPrice")),
        "fiftyTwoWeekHigh": _num(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": _num(info.get("fiftyTwoWeekLow")),
        "sharesOutstanding": _num(info.get("sharesOutstanding")),
        "dividendYield": _num(info.get("dividendYield")),
        "longBusinessSummary": (info.get("longBusinessSummary") or "")[:300],
    }
    _cache_save(key, out)
    return out


# ---------------------------------------------------------------------------
# Earnings / calendario de resultados
# ---------------------------------------------------------------------------
def fetch_earnings_date(symbol: str) -> Optional[dict[str, Any]]:
    key = f"earn_{symbol}"
    cached = _cache_load(key)
    if cached is not None:
        return cached
    try:
        cal = yf.Ticker(symbol).get_calendar()
        if cal:
            d = cal.get("earnings", {})
            earndates = cal.get("earningsDate")
            edate = None
            if isinstance(earndates, list):
                for e in earndates:
                    try:
                        ts = pd.Timestamp(e)
                        if ts > pd.Timestamp.now():
                            edate = ts.isoformat()
                            break
                    except Exception:
                        continue
            out = {"earnings_date": edate, "earnings_estimate": _num(d.get("earningsEstimate"))}
        else:
            out = {"earnings_date": None, "earnings_estimate": None}
    except Exception:
        out = {"earnings_date": None, "earnings_estimate": None}
    _cache_save(key, out)
    return out


# ---------------------------------------------------------------------------
# Macro (indices, VIX, rates, USD, credit)
# ---------------------------------------------------------------------------
def fetch_macro() -> dict[str, Any]:
    cached = _cache_load("macro")
    if cached is not None:
        return cached

    out: dict[str, Any] = {
        "indexes": {}, "vix": None, "tnx_trend": None, "dxy_bias": None,
        "hyg_above_lqd": None,
    }
    # Indices de tendencia via snapshot (SPY/QQQ/IWM) usando market_data.
    for sym in ("SPY", "QQQ", "IWM"):
        s = _fetch_snapshot(sym)
        if s is not None:
            out["indexes"][sym] = s.__dict__

    def _series_pct_chg(ticker: str, period: str = "1mo") -> Optional[float]:
        try:
            df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close = df["Close"].dropna()
            if len(close) < 2:
                return None
            first = float(close.iloc[0])
            last = float(close.iloc[-1])
            return (last / first - 1.0) if first else None
        except Exception:
            return None

    # VIX nivel
    try:
        df = yf.download("^VIX", period="1mo", interval="1d", progress=False, auto_adjust=True)
        if df is not None and not df.empty and len(df) >= 2:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            out["vix"] = float(df["Close"].dropna().iloc[-1])
    except Exception:
        pass

    # TNX trend normalizado -1..1 (10y yield)
    tnx = _series_pct_chg("^TNX")
    if tnx is not None:
        out["tnx_trend"] = round(max(-1.0, min(1.0, tnx * 10.0)), 3)

    # DXY bias normalizado
    dxy = _series_pct_chg("DX-Y.NYB")
    if dxy is not None:
        out["dxy_bias"] = round(max(-1.0, min(1.0, dxy * 10.0)), 3)

    # Credit: HYG (<=> riesgo) vs LQD (investment grade). HYG > LQD => credit ok.
    hyg = _series_pct_chg("HYG")
    lqd = _series_pct_chg("LQD")
    if hyg is not None and lqd is not None:
        out["hyg_above_lqd"] = hyg >= lqd

    _cache_save("macro", out)
    return out


# ---------------------------------------------------------------------------
# Sector (ETF de sector proxy para tendencia sectorial / RS)
# ---------------------------------------------------------------------------
SECTOR_ETF: dict[str, str] = {
    "TECHNOLOGY": "XLK",
    "INFORMATION TECHNOLOGY": "XLK",
    "COMMUNICATION SERVICES": "XLC",
    "CONSUMER DISCRETIONARY": "XLY",
    "CONSUMER STAPLES": "XLP",
    "FINANCIAL SERVICES": "XLF",
    "FINANCIALS": "XLF",
    "HEALTHCARE": "XLV",
    "INDUSTRIALS": "XLI",
    "MATERIALS": "XLB",
    "ENERGY": "XLE",
    "UTILITIES": "XLU",
    "REAL ESTATE": "XLRE",
}

_CACHED_SECTOR: dict[str, Any] = {}


def fetch_sector_trend(sector: str, etf: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Tendencia del sector del simbolo (cuanto + el RS del sector vs SPY)."""
    etf = (etf or SECTOR_ETF.get((sector or "").upper()) or "").upper()
    if not etf:
        return None
    key = f"sector_{etf}"
    if key in _CACHED_SECTOR:
        return _CACHED_SECTOR[key]
    cached = _cache_load(key)
    if cached is not None:
        _CACHED_SECTOR[key] = cached
        return cached
    try:
        df = yf.download(etf, period="6mo", interval="1d", progress=False, auto_adjust=True)
        spy = yf.download("SPY", period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 60:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        if isinstance(close.index, pd.DatetimeIndex):
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
        else:
            ma20 = ma50 = float(close.iloc[-1])
        last = float(close.iloc[-1])
        trend = 0
        trend += 30 if last > ma20 else 0
        trend += 30 if last > ma50 else 0
        trend += 40 if ma20 > ma50 else 0
        month_pct = (last / float(close.iloc[0]) - 1.0) if float(close.iloc[0]) else 0.0
        spy_ret = None
        if spy is not None and not spy.empty and len(spy) >= 2:
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            spy_close = float(spy["Close"].dropna().iloc[-1])
            spy_first = float(spy["Close"].dropna().iloc[0])
            spy_ret = (spy_close / spy_first - 1.0) if spy_first else 0.0
        out = {
            "etf": etf, "trend": trend,
            "month_pct": round(month_pct, 4),
            "rs_vs_spy": round(month_pct - (spy_ret or 0.0), 4),
            "close": last, "ma20": ma20, "ma50": ma50,
        }
        _cache_save(key, out)
        _CACHED_SECTOR[key] = out
        return out
    except Exception:
        return None


def relative_strength_vs_spy(symbol_snapshot: dict[str, Any]) -> Optional[float]:
    """RS simple del simbolo: pct 1d vs SPY 1d (crudo pero honesto)."""
    spy = _fetch_snapshot("SPY")
    if spy is None or symbol_snapshot is None:
        return None
    sym_chg = _num(symbol_snapshot.get("change_1d_pct"))
    spy_chg = _num(spy.change_1d_pct)
    if sym_chg is None or spy_chg is None:
        return None
    return round(sym_chg - spy_chg, 3)