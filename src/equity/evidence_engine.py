"""JAYU EQUITY EVIDENCE ENGINE — construye EvidencePackets desde datos reales.

Transforma los datos (fundamentals, macro, sector, tecnico, sentimiento,
institucional) en evidencias probabilisticas para el Bayesian Engine.
Las evidencias se construyen con reglas explicitas y auditable. No se inventa
ningun dato que la fuente no proporcione: si falta, se omite la evidencia.

Reglas de fuerza (strength 0..1) y fiabilidad (reliability 0..1) iniciales;
se calibran con outcomes reales (seccion 31/32).
"""

from __future__ import annotations

from typing import Any, Optional

from .context import EquityContext
from .evidence import CorrelationGroup, EvidencePacket, make_evidence


def _pct_to_strength(v: Optional[float], scale: float = 2.0) -> float:
    """Convierte un % (0.05 = 5%) en fuerza 0..1 (lineal hasta `scale`*100%)."""
    if v is None:
        return 0.0
    return max(0.0, min(1.0, abs(float(v)) / scale))


def _sign_pct(v: Optional[float]) -> int:
    if v is None:
        return 0
    return 1 if float(v) > 0 else -1 if float(v) < 0 else 0


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1. FUNDAMENTAL QUALITY (seccion 6)
# ---------------------------------------------------------------------------
def fundamental_evidence(f: dict[str, Any], symbol: str, horizon: str,
                         regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []

    def add(etype, direction, strength, rel, group, meta=None):
        packets.append(make_evidence(
            symbol, "FUNDAMENTAL_QUALITY", "FUNDAMENTAL", etype, direction,
            strength, reliability=rel, freshness=0.95, regime=regime,
            correlation_group=group, horizon=horizon, metadata=meta or {}))

    rev_growth = _num(f.get("revenueGrowth"))
    eps_growth = _num(f.get("earningsGrowth"))
    fcf = _num(f.get("freeCashflow"))
    gross_margin = _num(f.get("grossMargins"))
    op_margin = _num(f.get("operatingMargins"))
    roe = _num(f.get("returnOnEquity"))
    roa = _num(f.get("returnOnAssets"))
    total_debt = _num(f.get("totalDebt"))
    total_cash = _num(f.get("totalCash"))
    current_ratio = _num(f.get("currentRatio"))
    debt_to_equity = _num(f.get("debtToEquity"))
    mcap = _num(f.get("marketCap"))

    # Revenue growth
    if rev_growth is not None:
        add("REVENUE_GROWTH", "BULLISH" if rev_growth > 0.03 else "BEARISH" if rev_growth < 0 else "NEUTRAL",
            _pct_to_strength(rev_growth), 0.70, CorrelationGroup.FUNDAMENTALS,
            {"rev_growth": rev_growth})

    # EPS growth
    if eps_growth is not None:
        add("EPS_GROWTH", "BULLISH" if eps_growth > 0.05 else "BEARISH" if eps_growth < 0 else "NEUTRAL",
            _pct_to_strength(eps_growth), 0.75, CorrelationGroup.EARNINGS_EXPECTATIONS,
            {"eps_growth": eps_growth})

    # Cash generation (FCF positivo y razonable vs mcap)
    if fcf is not None and mcap:
        fcf_yield = fcf / mcap
        add("CASH_GENERATION", "BULLISH" if fcf_yield > 0.02 else "NEUTRAL",
            _pct_to_strength(fcf_yield, scale=0.10), 0.70, CorrelationGroup.CASH_FLOW,
            {"fcf_yield": fcf_yield})

    # Margins
    if gross_margin is not None and op_margin is not None:
        combined = (gross_margin + op_margin) / 2.0
        add("MARGINS", "BULLISH" if combined > 0.20 else "BEARISH" if combined < 0.05 else "NEUTRAL",
            _pct_to_strength(combined, scale=0.40), 0.70, CorrelationGroup.MARGINS,
            {"gross": gross_margin, "op": op_margin})

    # ROIC / ROE
    if roe is not None:
        add("ROIC_ROE", "BULLISH" if roe > 0.15 else "BEARISH" if roe < 0 else "NEUTRAL",
            _pct_to_strength(roe, scale=0.30), 0.70, CorrelationGroup.BALANCE_SHEET,
            {"roe": roe})

    # Debt / liquidity / balance sheet
    if debt_to_equity is not None:
        high_dte = debt_to_equity > 1.5
        add("DEBT", "BEARISH" if high_dte else "NEUTRAL",
            0.5 if high_dte else 0.25, 0.65, CorrelationGroup.BALANCE_SHEET,
            {"dte": debt_to_equity})
    elif total_debt is not None and total_cash is not None:
        net_debt = total_debt - total_cash
        if net_debt < 0:
            add("BALANCE_SHEET", "BULLISH", 0.5, 0.70, CorrelationGroup.BALANCE_SHEET,
                {"net_cash": True})
    if current_ratio is not None:
        if current_ratio < 1:
            add("LIQUIDITY", "BEARISH", 0.5, 0.60, CorrelationGroup.BALANCE_SHEET,
                {"current_ratio": current_ratio})

    return packets


# ---------------------------------------------------------------------------
# 2. VALUATION (seccion 7)
# ---------------------------------------------------------------------------
def valuation_evidence(f: dict[str, Any], symbol: str, horizon: str,
                       regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []

    def add(etype, direction, strength, rel, group, meta=None):
        packets.append(make_evidence(
            symbol, "VALUATION", "VALUATION", etype, direction, strength,
            reliability=rel, freshness=0.90, regime=regime,
            correlation_group=group, horizon=horizon, metadata=meta or {}))

    forward_pe = _num(f.get("forwardPE"))
    trailing_pe = _num(f.get("trailingPE"))
    peg = _num(f.get("pegRatio"))
    ps = _num(f.get("priceToSalesTTM"))

    if forward_pe is not None and forward_pe > 0:
        # valoracion relativa al crecimiento: barato si fPE < 20, caro si > 40
        direction = "BULLISH" if forward_pe < 18 else "BEARISH" if forward_pe > 40 else "NEUTRAL"
        strength = (1.0 - min(1.0, (forward_pe - 10.0) / 50.0)) if direction == "BULLISH" else \
                   min(1.0, (forward_pe - 40.0) / 40.0) if direction == "BEARISH" else 0.35
        add("FORWARD_PE", direction, max(0.15, strength), 0.70,
            CorrelationGroup.VALUATION, {"fpe": forward_pe})

    if peg is not None and peg > 0 and _num(f.get("earningsGrowth")) or 0 > 0:
        direction = "BULLISH" if peg < 1.2 else "BEARISH" if peg > 2.5 else "NEUTRAL"
        strength = 1.2 / peg if direction == "BULLISH" else min(1.0, peg / 4.0) if direction == "BEARISH" else 0.3
        add("PEG", direction, min(0.9, strength), 0.70, CorrelationGroup.VALUATION, {"peg": peg})

    if ps is not None and ps > 0:
        direction = "BULLISH" if ps < 3 else "BEARISH" if ps > 15 else "NEUTRAL"
        add("PRICE_TO_SALES", direction,
            (1.0 - ps / 5.0) if direction == "BULLISH" else min(0.9, ps / 25.0) if direction == "BEARISH" else 0.3,
            0.60, CorrelationGroup.VALUATION, {"ps": ps})

    return packets


# ---------------------------------------------------------------------------
# 3. CATALYST / EARNINGS RISK (secciones 8 & 25)
# ---------------------------------------------------------------------------
def catalyst_evidence(f: dict[str, Any], earnings: Optional[dict[str, Any]],
                      symbol: str, horizon: str, regime: list[str],
                      policy: str = "AVOID") -> list[EvidencePacket]:
    """Evidencia de catalizador + proximidad de earnings (riesgo)."""
    packets: list[EvidencePacket] = []

    def add(etype, direction, strength, rel, group, meta=None):
        packets.append(make_evidence(
            symbol, "CATALYST", "CATALYST", etype, direction, strength,
            reliability=rel, freshness=0.85, regime=regime,
            correlation_group=group, horizon=horizon, metadata=meta or {}))

    # Earnings date proximo.
    earnings_date = (earnings or {}).get("earnings_date")
    if earnings_date:
        weeks_to_earnings = _weeks_until(earnings_date)
        meta = {"earnings_date": earnings_date, "weeks": weeks_to_earnings}
        if weeks_to_earnings is not None and weeks_to_earnings <= 2.0:
            # Earnings inminente: dependiendo de la politica.
            if policy in ("REDUCE", "AVOID"):
                add("EARNINGS_PROXIMITY", "BEARISH", 0.6, 0.80,
                    CorrelationGroup.EARNINGS_EXPECTATIONS, meta)
            else:
                add("EARNINGS_PROXIMITY", "BULLISH", 0.4, 0.70,
                    CorrelationGroup.EARNINGS_EXPECTATIONS, meta)
        elif weeks_to_earnings is not None and weeks_to_earnings <= 6.0:
            # Earnings dentro del horizonte swing: catalizador legitimo.
            add("EARNINGS_CATALYST", "BULLISH", 0.35, 0.75,
                CorrelationGroup.CATALYST, meta)
    else:
        # Sin earnings conocido: sin gestion.
        pass

    # Revisiones de analistas (guidance / analyst revisions) desde info.
    rec_mean = _num(f.get("recommendationMean"))
    n_analysts = _num(f.get("numberOfAnalystOpinions"))
    target_mean = _num(f.get("targetMeanPrice"))
    price = _num(f.get("fiftyTwoWeekHigh"))
    # targetMeanPrice vs precio actual no lo tenemos aqui; usamos recomendacion.
    if rec_mean is not None and n_analysts and n_analysts >= 3:
        # recommendationMean: 1 = strong buy, 5 = sell.
        if rec_mean <= 1.8:
            add("ANALYST_UPGRADE_BIAS", "BULLISH", 0.45, 0.70,
                CorrelationGroup.EARNINGS_EXPECTATIONS,
                {"recommendation_mean": rec_mean})
        elif rec_mean >= 3.5:
            add("ANALYST_REVISION_DOWN", "BEARISH", 0.5, 0.70,
                CorrelationGroup.EARNINGS_EXPECTATIONS,
                {"recommendation_mean": rec_mean})

    return packets


def _weeks_until(iso_date: Optional[str]) -> Optional[float]:
    if not iso_date:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds() / (7 * 86400.0))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 4. MACRO (seccion 9) — impacto adaptado por sector
# ---------------------------------------------------------------------------
def macro_evidence(macro: dict[str, Any], sector: Optional[str],
                   symbol: str, horizon: str, regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    sector = (sector or "").upper()

    vix = _num(macro.get("vix"))
    if vix is not None:
        # Riesgo de mercado alto -> viento en contra para nuevas posiciones LONG.
        if vix > 28:
            packets.append(make_evidence(
                symbol, "MACRO", "MACRO", "vix_high", "BEARISH", 0.5, 0.80,
                0.9, regime, CorrelationGroup.MACRO_RISK, horizon,
                {"vix": vix}))
        elif vix < 15:
            packets.append(make_evidence(
                symbol, "MACRO", "MACRO", "vix_low", "BULLISH", 0.35, 0.75,
                0.9, regime, CorrelationGroup.MACRO_RISK, horizon,
                {"vix": vix}))

    tnx_trend = _num(macro.get("tnx_trend"))
    if tnx_trend is not None:
        # Impacto sectorial: growth/long-duration sufren mas con rates subiendo.
        sensitive = sector in (
            "INFORMATION TECHNOLOGY", "TECHNOLOGY", "COMMUNICATION SERVICES",
            "CONSUMER DISCRETIONARY", "HEALTHCARE", "REAL ESTATE",
        )
        defensive_neutral = sector in ("UTILITIES", "CONSUMER STAPLES")
        if tnx_trend > 0.3 and sensitive:
            packets.append(make_evidence(
                symbol, "MACRO", "MACRO", "rates_rising_duration", "BEARISH",
                0.45, 0.75, 0.9, regime, CorrelationGroup.MACRO_RATES, horizon,
                {"tnx_trend": tnx_trend, "sector": sector}))
        elif tnx_trend < -0.3 and sensitive:
            packets.append(make_evidence(
                symbol, "MACRO", "MACRO", "rates_falling_duration", "BULLISH",
                0.4, 0.70, 0.9, regime, CorrelationGroup.MACRO_RATES, horizon,
                {"tnx_trend": tnx_trend, "sector": sector}))

    dxy_bias = _num(macro.get("dxy_bias"))
    if dxy_bias is not None and abs(dxy_bias) > 0.3:
        direction = "BEARISH" if dxy_bias > 0 else "BULLISH"
        packets.append(make_evidence(
            symbol, "MACRO", "MACRO", "usd_bias", direction, 0.3, 0.65, 0.9,
            regime, CorrelationGroup.MACRO_LIQUIDITY, horizon,
            {"dxy_bias": dxy_bias}))

    hyg = macro.get("hyg_above_lqd")
    if hyg is not None:
        packets.append(make_evidence(
            symbol, "MACRO", "MACRO", "credit_conditions",
            "BULLISH" if hyg else "BEARISH", 0.45, 0.80, 0.9, regime,
            CorrelationGroup.MACRO_RISK, horizon,
            {"hyg_above_lqd": hyg}))

    return packets


# ---------------------------------------------------------------------------
# 5. SECTOR / INDUSTRY (seccion 10)
# ---------------------------------------------------------------------------
def sector_evidence(sector_trend: Optional[dict[str, Any]], rs_vs_spy: Optional[float],
                    symbol: str, horizon: str, regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    if not sector_trend:
        return packets

    trend = sector_trend.get("trend", 0)
    rs = _num(sector_trend.get("rs_vs_spy"))
    if trend >= 70:
        packets.append(make_evidence(
            symbol, "SECTOR", "SECTOR", "sector_trend_strong", "BULLISH", 0.55,
            0.72, 0.9, regime, CorrelationGroup.SECTOR, horizon,
            {"etf": sector_trend.get("etf"), "trend": trend}))
    elif trend <= 30:
        packets.append(make_evidence(
            symbol, "SECTOR", "SECTOR", "sector_trend_weak", "BEARISH", 0.55,
            0.72, 0.9, regime, CorrelationGroup.SECTOR, horizon,
            {"etf": sector_trend.get("etf"), "trend": trend}))

    if rs is not None and abs(rs) > 0.02:
        packets.append(make_evidence(
            symbol, "SECTOR", "SECTOR", "sector_relative_strength",
            "BULLISH" if rs > 0 else "BEARISH",
            min(0.8, abs(rs) * 5.0), 0.70, 0.9, regime,
            CorrelationGroup.RELATIVE_STRENGTH, horizon,
            {"rs_vs_spy": rs}))

    # RS del simbolo individual vs SPY (1d).
    if rs_vs_spy is not None and abs(rs_vs_spy) > 0.01:
        packets.append(make_evidence(
            symbol, "SECTOR", "SECTOR", "symbol_relative_strength_1d",
            "BULLISH" if rs_vs_spy > 0 else "BEARISH",
            min(0.6, abs(rs_vs_spy) * 3.0), 0.60, 1.0, regime,
            CorrelationGroup.RELATIVE_STRENGTH, horizon,
            {"rs_vs_spy_1d": rs_vs_spy}))

    return packets


# ---------------------------------------------------------------------------
# 6. TECHNICAL swing (seccion 11)
# ---------------------------------------------------------------------------
def technical_evidence(snap: dict[str, Any], symbol: str, horizon: str,
                       regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    if not snap:
        return packets
    snap_ctx = EquityContext.from_snapshot(snap)

    close = snap_ctx.close
    sma20 = snap_ctx.sma_20
    sma50 = snap_ctx.sma_50
    sma200 = snap_ctx.sma_200
    rel_vol = snap_ctx.relative_volume

    # Tendencia swing (diaria)
    bullish_trend = close > sma200 > 0 and sma50 > sma200
    price_above_20 = close > sma20
    if bullish_trend and price_above_20:
        packets.append(make_evidence(
            symbol, "TECHNICAL", "TECHNICAL", "swing_uptrend", "BULLISH", 0.6,
            0.80, 0.95, regime, CorrelationGroup.TREND, horizon,
            {"close": close, "sma20": sma20, "sma50": sma50, "sma200": sma200}))
    elif not bullish_trend:
        packets.append(make_evidence(
            symbol, "TECHNICAL", "TECHNICAL", "swing_downtrend", "BEARISH", 0.55,
            0.75, 0.95, regime, CorrelationGroup.TREND, horizon,
            {"close": close, "sma200": sma200}))

    # Eonicidad / volumen relativo (no penaliza solo por bajo volumen).
    if rel_vol is not None and rel_vol > 1.2:
        packets.append(make_evidence(
            symbol, "TECHNICAL", "TECHNICAL", "volume_interest", "BULLISH",
            0.35, 0.65, 0.9, regime, CorrelationGroup.MOMENTUM, horizon,
            {"relative_volume": rel_vol}))

    # Distancia a maximo 52 semanas (momentum swing, no ruido diario).
    high_52 = snap_ctx.high_52w
    if high_52:
        dist = (close - high_52) / high_52
        if dist >= -0.02:
            packets.append(make_evidence(
                symbol, "TECHNICAL", "TECHNICAL", "near_52w_high", "BULLISH", 0.5,
                0.70, 0.9, regime, CorrelationGroup.MOMENTUM, horizon,
                {"dist_high_52": dist}))

    return packets


# ---------------------------------------------------------------------------
# 7. SENTIMENT (seccion 12) — optimismo saludable vs crowded / capitulacion
# ---------------------------------------------------------------------------
def sentiment_evidence(f: dict[str, Any], snap: Optional[dict[str, Any]],
                       symbol: str, horizon: str, regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []

    # Distancia al maximo de 52 semanas como proxy de sentiment de precio.
    high = _num(f.get("fiftyTwoWeekHigh"))
    low = _num(f.get("fiftyTwoWeekLow"))
    px = _num(snap.get("close")) if snap else None
    if high and low and px:
        # Posicion en rango 52s (0 abajo .. 1 arriba). No es señal contraria
        # automatica: depende del regimen (se evalua en el engine).
        range_pos = (px - low) / (high - low) if high > low else 0.5
        if range_pos > 0.85 and px >= high * 0.98:
            packets.append(make_evidence(
                symbol, "SENTIMENT", "SENTIMENT", "healthy_uptrend_position",
                "BULLISH", 0.35, 0.60, 0.9, regime,
                CorrelationGroup.RISK_SENTIMENT, horizon,
                {"range_pos_52w": range_pos}))
        elif range_pos < 0.15:
            packets.append(make_evidence(
                symbol, "SENTIMENT", "SENTIMENT", "capitulation_zone",
                "BEARISH", 0.3, 0.55, 0.9, regime,
                CorrelationGroup.RISK_SENTIMENT, horizon,
                {"range_pos_52w": range_pos}))

    return packets


# ---------------------------------------------------------------------------
# 8. INSTITUCIONAL / POSITIONING (seccion 13)
# ---------------------------------------------------------------------------
def positioning_evidence(f: dict[str, Any], symbol: str, horizon: str,
                         regime: list[str]) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    inst = _num(f.get("heldPercentInstitutions"))
    if inst is not None:
        # Alta propiedad institucional = refinamiento; no señal direccional por
        # si sola, pero banda informativa.
        if inst > 0.7:
            packets.append(make_evidence(
                symbol, "POSITIONING", "POSITIONING", "institutional_owned",
                "BULLISH" if inst > 0.85 else "NEUTRAL",
                0.25 if inst > 0.85 else 0.15, 0.55, 0.9, regime,
                CorrelationGroup.POSITIONING, horizon,
                {"held_institutions": inst}))
    return packets


# ---------------------------------------------------------------------------
# ORQUESTA
# ---------------------------------------------------------------------------
def build_all_evidence(symbol: str, snap: Optional[dict[str, Any]],
                       f: Optional[dict[str, Any]],
                       earnings: Optional[dict[str, Any]],
                       macro: dict[str, Any],
                       sector_trend: Optional[dict[str, Any]],
                       rs_vs_spy: Optional[float],
                       regime: list[str],
                       horizon: str = "SWING",
                       earnings_policy: str = "AVOID") -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    sector = (f or {}).get("sector")

    if f:
        packets.extend(fundamental_evidence(f, symbol, horizon, regime))
        packets.extend(valuation_evidence(f, symbol, horizon, regime))
        packets.extend(catalyst_evidence(f, earnings, symbol, horizon, regime, earnings_policy))
        packets.extend(sentiment_evidence(f, snap, symbol, horizon, regime))
        packets.extend(positioning_evidence(f, symbol, horizon, regime))

    packets.extend(macro_evidence(macro, sector, symbol, horizon, regime))
    packets.extend(sector_evidence(sector_trend, rs_vs_spy, symbol, horizon, regime))
    packets.extend(technical_evidence(snap, symbol, horizon, regime))

    return packets