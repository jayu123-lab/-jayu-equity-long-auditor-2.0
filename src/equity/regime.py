"""JAYU EQUITY MARKET REGIME — clasificacion de regimen de mercado (seccion 19).

Clasifica BULL/BEAR/CORRECTION/RISK_ON/RISK_OFF/HIGH_VOL/LOW_VOL/
SECTOR_ROTATION/MACRO_STRESS usando datos reales disponibles (yfinance):
SPY/QQQ/IWM (tendencia + breadth), VIX (vol), 10y (TNX), USD (DXY) y
credit (HYG vs LQD). En mercado hostil eleva el umbral de nuevos LONG.

Si alguna fuente falta, se degrada a neutra (nunca se inventa).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from ..models import MarketSnapshot


@dataclass(frozen=True)
class MarketRegime:
    tags: list[str]
    regime_score: int          # -100..100 (positivo = favorable a LONG)
    buy_threshold_offset: float  # se suma al posterior minimo para BUY
    prior_adjustment: float      # factor sobre P(LONG) por regimen
    evidence: list[dict[str, Any]]

    def with_threshold(self, base: float) -> float:
        return min(0.99, max(0.0, base + self.buy_threshold_offset))


def _trend(close: float, ma200: Optional[float], ma50: Optional[float],
           ma20: Optional[float]) -> int:
    s = 0
    if ma200 is not None and close > ma200:
        s += 40
    if ma50 is not None and close > ma50:
        s += 30
    if ma20 is not None and close > ma20:
        s += 30
    return s


def _clamp(v: float) -> float:
    if v is None or math.isnan(v):
        return 0.0
    return max(-1.0, min(1.0, float(v)))


def classify_market_regime(indexes: list[MarketSnapshot],
                           vix_level: Optional[float] = None,
                           tnx_trend: Optional[float] = None,
                           dxy_bias: Optional[float] = None,
                           hyg_above_lqd: Optional[bool] = None,
                           ) -> MarketRegime:
    """indexes: snapshots de SPY/QQQ/IWM (o los disponibles)."""
    if not indexes:
        return MarketRegime(
            tags=["DATA_MISSING"], regime_score=0, buy_threshold_offset=0.05,
            prior_adjustment=1.0, evidence=[{"type": "missing", "detail": "no index data"}],
        )

    avg_trend = round(sum(i.trend_score for i in indexes) / len(indexes)) if indexes else 0
    # Breadth: fraccion de indices por encima de su media 50 (muy simple).
    above_50 = sum(1 for i in indexes if i.trend_score >= 50)
    breadth = above_50 / len(indexes)

    tags: list[str] = []
    score = 0
    ev: list[dict[str, Any]] = []

    # -- Tendencia de mercado --
    if avg_trend >= 75:
        tags.append("BULL_MARKET") if breadth >= 2 / 3 else tags.append("SECTOR_ROTATION")
        score += 30
        ev.append({"type": "index_trend", "avg": avg_trend, "breadth": breadth})
    elif avg_trend <= 25:
        tags.append("BEAR_MARKET")
        score -= 40
        ev.append({"type": "index_trend_bear", "avg": avg_trend})
    elif avg_trend < 50 and breadth < 0.5:
        tags.append("CORRECTION")
        score -= 20
        ev.append({"type": "correction", "avg": avg_trend, "breadth": breadth})
    else:
        tags.append("NEUTRAL_MARKET")
        ev.append({"type": "neutral", "avg": avg_trend})

    # -- Volatilidad --
    vix = vix_level
    if vix is not None and not math.isnan(vix):
        if vix >= 28:
            tags.append("HIGH_VOL")
            tags.append("RISK_OFF")
            score -= 25
        elif vix <= 16:
            tags.append("LOW_VOL")
            tags.append("RISK_ON")
            score += 10
        else:
            tags.append("RISK_ON" if vix < 20 else "NEUTRAL_VOL")
        ev.append({"type": "vix", "value": vix})

    # -- Rates (TNX) --
    if tnx_trend is not None and not math.isnan(tnx_trend):
        # tnx_trend se pasa ya normalizado en -1..1; subida fuerte = viento en contra
        # para equity LONG con durations largas, pero no universal (sector).
        if tnx_trend > 0.5:
            tags.append("RATES_RISING")
            score -= 10
            ev.append({"type": "rates_rising", "trend": tnx_trend})
        elif tnx_trend < -0.3:
            tags.append("RATES_FALLING")
            score += 8
        else:
            ev.append({"type": "rates_neutral", "trend": tnx_trend})

    # -- USD --
    if dxy_bias is not None and not math.isnan(dxy_bias):
        # USD fuerte suele presionar earnings/commodity pero NO a todas las acciones;
        # impacto sectorial se evalúa en sector_evidence. Aquí solo un leve ajuste.
        if dxy_bias > 0.4:
            tags.append("USD_STRONG")
            score -= 5
        elif dxy_bias < -0.3:
            tags.append("USD_WEAK")
            score += 5
        ev.append({"type": "dxy", "bias": dxy_bias})

    # -- Credit --
    if hyg_above_lqd is not None:
        if hyg_above_lqd:
            tags.append("CREDIT_OK")
            score += 10
        else:
            tags.append("CREDIT_STRESS")
            tags.append("MACRO_STRESS" if score < 0 else "CREDIT_STRESS")
            score -= 20
        ev.append({"type": "credit", "hyg_above_lqd": hyg_above_lqd})

    score = max(-100, min(100, score))

    # Umbral de compra: en regimen hostil se exige más posterior.
    offset = 0.0
    if "BEAR_MARKET" in tags or "CORRECTION" in tags:
        offset = 0.06
    if "MACRO_STRESS" in tags or "HIGH_VOL" in tags:
        offset = max(offset, 0.04)
    if "RISK_OFF" in tags:
        offset = max(offset, 0.03)

    # Prior adjustment: 30% arriba/abajo según tendencia de mercado.
    prior_mult = 1.0 + 0.30 * (breadth - 0.5) * 2.0  # breadth 1 -> 1.3, 0 -> 0.7

    return MarketRegime(
        tags=tags, regime_score=score, buy_threshold_offset=offset,
        prior_adjustment=round(prior_mult, 3), evidence=ev,
    )