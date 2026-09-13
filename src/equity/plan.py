"""JAYU EQUITY PLAN — entrada, stop, objetivos e invalidacion (secciones 26-29).

Genera un plan de ejecucion para un LONG swing sobre el contexto del simbolo.
El plan es auditable: cada numero sale de una regla explicita (ATR, estructura
de energias, no de "analisis discrecional"). Si falta ATR se degrada a un
porcentaje fijo del precio, declarado en el plan.

Politica de earnings (seccion 25): AVOID (no abrir cerca de earnings),
REDUCE (reducir tamano si earnings inminentes), HOLD_THROUGH (asumir riesgo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .context import EquityContext
from .quality_gate import MIN_RR

ATR_STOP_MULT = 2.5          # inicial: 2.5 * ATR debajo del punto de entrada
ATR_TP1_MULT = 1.25          # TP1 en +1.25R (margen sobre RR>=1.2 del publicador)
ATR_TP2_MULT = 2.25          # TP2 en +2.25R (50/50 -> RR ponderado ~1.75R)
PULLBACK_TOLERANCE = 0.4     # el precio puede alejarse 40% del ATR antes de
                             # requerir esperar un pullback (CANDIDATE->WAIT_ENTRY)
FALLBACK_RISK_PCT = 0.02     # si no hay ATR: riesgo fijo = 2% del precio
MAX_RISK_SL_PCT = 0.08       # ningun SL mas alejado del 8% del precio
EARNINGS_AVOID_DAYS = 7      # dias a earnings que bloquean abrir con polit Avaid


@dataclass
class TradePlan:
    symbol: str
    posterior: float
    state: str
    entry_price: Optional[float]
    entry_type: str                      # BUY_MARKET / BUY_LIMIT / BUY_STOP
    entry_zone_lo: Optional[float]
    entry_zone_hi: Optional[float]
    stop: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    rr: float
    risk_pct: float                      # riesgo comprometido = SL dist % del px
    atr_used: Optional[float]
    structure: dict[str, Any] = field(default_factory=dict)
    invalidation: dict[str, Any] = field(default_factory=dict)
    earnings: dict[str, Any] = field(default_factory=dict)
    rationale: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def valid(self) -> bool:
        return (self.entry_price is not None and self.stop is not None
                and self.rr >= MIN_RR and not self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "posterior": self.posterior, "state": self.state,
            "entry_price": self.entry_price, "entry_type": self.entry_type,
            "entry_zone": [self.entry_zone_lo, self.entry_zone_hi],
            "stop": self.stop, "tp1": self.tp1, "tp2": self.tp2,
            "rr": self.rr, "risk_pct": self.risk_pct, "atr_used": self.atr_used,
            "structure": self.structure, "invalidation": self.invalidation,
            "earnings": self.earnings, "rationale": self.rationale,
            "valid": self.valid(), "errors": self.errors,
        }


def _round4(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return round(float(v), 4)


def _weeks_until_earnings(earnings_date: Optional[str]) -> Optional[float]:
    if not earnings_date:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(earnings_date).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).total_seconds() / 86400.0
    except Exception:
        return None


def compute_plan(ctx: EquityContext, posterior: float, state: str,
                 earnings_date: Optional[str] = None,
                 earnings_policy: str = "AVOID",
                 current_price: Optional[float] = None) -> TradePlan:
    """Construye el plan. `state` vendra del quality gate (CANDIDATE/BUY)."""
    symbol = ctx.symbol
    close = current_price or ctx.close

    plan = TradePlan(
        symbol=symbol, posterior=posterior, state=state,
        entry_price=None, entry_type="BUY_MARKET",
        entry_zone_lo=None, entry_zone_hi=None, stop=None, tp1=None, tp2=None,
        rr=0.0, risk_pct=0.0, atr_used=None,
    )

    if close is None:
        plan.errors.append("sin precio de cierre")
        return plan

    # --- ATR y riesgo ---
    atr = ctx.atr_14
    if atr:
        plan.atr_used = atr
        risk = max(atr * ATR_STOP_MULT, close * FALLBACK_RISK_PCT)
    else:
        plan.rationale.append("sin ATR disponible: riesgo fijo 2% del precio")
        risk = close * FALLBACK_RISK_PCT

    # -- estructura de soporte horizonte swing (lows semanales o 52w) --
    stop = close - risk
    if ctx.metadata.get("recent_swing_low") is not None:
        swing_low = float(ctx.metadata["recent_swing_low"])
        stop = min(stop, swing_low - 0.002 * close)
        plan.structure["recent_swing_low"] = swing_low
    elif ctx.low_52w and ctx.low_52w < close * 0.9:
        # No usamos el minimo de 52 semanas directamente (invalida demasiado
        # facil); queda documentado como referencia.
        plan.structure["note"] = "52w_low_reference_no_used"

    # limite absoluto de distancia
    if (close - stop) / close > MAX_RISK_SL_PCT:
        stop = close * (1.0 - MAX_RISK_SL_PCT)
        plan.rationale.append("SL limitado al 8% del precio")

    plan.stop = _round4(stop)
    plan.risk_pct = round((close - stop) / close, 4) if close else 0.0

    # --- Entry: LONG swing, preferir pullback controlado, no perseguir ---
    entry = close
    plan.entry_price = _round4(entry)
    plan.entry_zone_hi = _round4(close * (1.0 + PULLBACK_TOLERANCE * (risk / close)))
    plan.entry_zone_lo = _round4(close * (1.0 - PULLBACK_TOLERANCE * (risk / close)))
    plan.entry_type = "BUY_LIMIT" if current_price and entry < current_price else "BUY_MARKET"

    # --- Objetivos ---
    risk_unit = close - stop
    plan.tp1 = _round4(entry + ATR_TP1_MULT * risk_unit)
    plan.tp2 = _round4(entry + ATR_TP2_MULT * risk_unit)
    # RR ponderado: 50% de la posicion sale en TP1 (1R) y 50% en TP2 (2R).
    if (entry - stop) > 0:
        tp1_r = (plan.tp1 - entry) / (entry - stop)
        tp2_r = (plan.tp2 - entry) / (entry - stop)
        plan.rr = round(0.5 * tp1_r + 0.5 * tp2_r, 2)
    else:
        plan.rr = 0.0

    # --- Invalidacion (solo LONG): cierre diario/semanal bajo estructura ---
    plan.invalidation = {
        "rule": "cierre bajo el nivel de estructura (lows swing) o SL",
        "stop": plan.stop,
        "confirm": "cierre diario o semanal bajo el nivel, no intradiario",
    }

    # --- Earnings proximity policy ---
    days_to = _weeks_until_earnings(earnings_date)
    policy = str(earnings_policy or "AVOID").upper()
    plan.earnings = {"policy": policy, "date": earnings_date}
    if days_to is not None:
        plan.earnings["days_to"] = round(days_to, 1)
        if days_to <= EARNINGS_AVOID_DAYS:
            if policy == "AVOID":
                plan.errors.append(
                    f"earnings en {days_to:.0f}d: politica AVOID bloquea apertura")
                plan.rationale.append("apertura bloqueada por polit de earnings AVOID")
            elif policy == "REDUCE":
                plan.rationale.append("polit REDUCE: tamano minorado, SL antes de earnings")
            else:
                plan.rationale.append("polit HOLD_THROUGH: se asume riesgo de earnings")

    # --- Validacion final ---
    if plan.rr < MIN_RR:
        plan.errors.append(f"rr={plan.rr:.2f}<{MIN_RR}")
    if plan.stop <= 0 or plan.tp2 <= plan.entry_price:
        plan.errors.append("numeros de SL/TP no validos")

    return plan