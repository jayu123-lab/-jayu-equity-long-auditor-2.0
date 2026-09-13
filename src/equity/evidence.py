"""JAYU EQUITY CONTRACTS — evidencias del dominio EQUITY_LONG_SWING_V1.

Es el mismo contrato EvidencePacket del motor comun JAYU_BAYES_ENGINE_V1
pero con correlation groups y categorias propias de acciones USA LONG swing.

La LLM/agentes identifican, clasifican y contextualizan la evidencia.
El Bayesian Engine CUANTIFICA el posterior. Ningun agente asigna el posterior.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CorrelationGroup(str):
    FUNDAMENTALS = "FUNDAMENTALS"
    EARNINGS_EXPECTATIONS = "EARNINGS_EXPECTATIONS"
    VALUATION = "VALUATION"
    CASH_FLOW = "CASH_FLOW"
    MARGINS = "MARGINS"
    BALANCE_SHEET = "BALANCE_SHEET"
    CATALYST = "CATALYST"
    MACRO_RATES = "MACRO_RATES"
    MACRO_LIQUIDITY = "MACRO_LIQUIDITY"
    MACRO_RISK = "MACRO_RISK"
    RISK_SENTIMENT = "RISK_SENTIMENT"
    SECTOR = "SECTOR"
    INDUSTRY = "INDUSTRY"
    BREADTH = "BREADTH"
    TREND = "TREND"
    STRUCTURE = "STRUCTURE"
    MOMENTUM = "MOMENTUM"
    VOLATILITY = "VOLATILITY"
    RELATIVE_STRENGTH = "RELATIVE_STRENGTH"
    POSITIONING = "POSITIONING"


# Categoria -> correlation group por defecto (evita doble conteo).
CATEGORY_TO_CORRELATION: dict[str, str] = {
    "FUNDAMENTAL": CorrelationGroup.FUNDAMENTALS,
    "VALUATION": CorrelationGroup.VALUATION,
    "EARNINGS": CorrelationGroup.EARNINGS_EXPECTATIONS,
    "CATALYST": CorrelationGroup.CATALYST,
    "MACRO": CorrelationGroup.MACRO_RATES,
    "SECTOR": CorrelationGroup.SECTOR,
    "TECHNICAL": CorrelationGroup.STRUCTURE,
    "SENTIMENT": CorrelationGroup.RISK_SENTIMENT,
    "POSITIONING": CorrelationGroup.POSITIONING,
    "REGIME": CorrelationGroup.MACRO_RISK,
    "RISK": CorrelationGroup.MACRO_RISK,
}

EVIDENCE_CATEGORIES = (
    "FUNDAMENTAL", "VALUATION", "EARNINGS", "CATALYST", "MACRO",
    "SECTOR", "TECHNICAL", "SENTIMENT", "POSITIONING", "REGIME", "RISK",
)


@dataclass
class EvidencePacket:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=utcnow)
    symbol: str = ""
    horizon: str = "SWING"
    agent: str = "UNKNOWN"
    category: str = "TECHNICAL"
    evidence_type: str = ""
    direction: str = "NEUTRAL"
    strength: float = 0.5
    reliability: float = 0.5
    freshness: float = 1.0
    regime: list[str] = field(default_factory=list)
    correlation_group: str = CorrelationGroup.STRUCTURE
    source_timestamp: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sign(self) -> int:
        return {"BULLISH": 1, "BEARISH": -1}.get(str(self.direction).upper(), 0)


def make_evidence(symbol: str, agent: str, category: str, evidence_type: str,
                  direction: str, strength: float,
                  reliability: float = 0.6, freshness: float = 1.0,
                  regime: Optional[list[str]] = None,
                  correlation_group: Optional[str] = None,
                  horizon: str = "SWING",
                  metadata: Optional[dict[str, Any]] = None) -> EvidencePacket:
    return EvidencePacket(
        symbol=symbol.upper(),
        agent=str(agent).upper(),
        category=str(category).upper(),
        evidence_type=evidence_type,
        direction=str(direction).upper(),
        strength=max(0.0, min(1.0, float(strength or 0.0))),
        reliability=max(0.0, min(1.0, float(reliability or 0.0))),
        freshness=max(0.0, min(1.0, float(freshness or 0.0))),
        regime=regime or [],
        correlation_group=correlation_group or CATEGORY_TO_CORRELATION.get(
            str(category).upper(), CorrelationGroup.STRUCTURE),
        horizon=horizon,
        metadata=metadata or {},
    )