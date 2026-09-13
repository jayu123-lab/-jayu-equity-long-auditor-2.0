"""JAYU EQUITY RANKING & DIVERSIFICATION (secciones 34-35).

Traduce el ranking del scanner en una lista accionable profesional:
  1. UMBRAL: posterior >= threshold (con offset de regimen) y calidad (gate).
  2. PLAN: el plan debe ser valido (SL/TP consistentes, politica earnings OK).
  3. EV: expectativa en R ponderada 50/50 (TP1+TP2) debe ser > 0.
  4. DIVERSIFICACION: tope por numero de posiciones y por sector, eligiendo
     las de mayor EV (no 5 ideas correlacionadas).

NO retoca los likelihood ratios: la discriminacion fina viene de la
calibracion con outcomes reales (secciones 30-32), no de ajustar el modelo
para que quepa el dia.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

MAX_POSITIONS = 3
MAX_PER_SECTOR = 2


@dataclass
class Selection:
    symbol: str
    posterior: float
    event_value: float
    sector: Optional[str]
    reasons: list[str]
    rejected: list[str]


def expected_value(posterior: float, rr: float) -> float:
    """EV en unidades de R con la configuracion 50/50 de objetivos."""
    p = max(0.0, min(1.0, float(posterior)))
    r = max(0.0, float(rr))
    return round(p * r - (1.0 - p), 4)


def _threshold_with_regime(base: float = 0.75, offset: float = 0.0) -> float:
    return min(0.99, base + offset)


def evaluate_candidate(row: dict[str, Any], threshold: float) -> Selection:
    """Evalua un candidato del scanner. Devuelve decision con razones."""
    sym = row.get("symbol")
    posterior = float(row.get("posterior") or 0.0)
    gate = row.get("gate") or {}
    plan = row.get("plan") or {}
    sector = row.get("sector")

    reasons: list[str] = []
    rejected: list[str] = []

    if posterior < threshold:
        rejected.append(f"posterior {posterior:.3f}<{threshold:.3f}")
        return Selection(sym, posterior, 0.0, sector, reasons, rejected)

    if not gate.get("passed"):
        rejected.append("quality gate: " + ";".join(gate.get("blocked", [])))
        return Selection(sym, posterior, 0.0, sector, reasons, rejected)

    if not plan.get("valid"):
        rejected.append("plan invalido: " + ";".join(plan.get("errors", [])))
        return Selection(sym, posterior, 0.0, sector, reasons, rejected)

    rr = float(plan.get("rr") or 0.0)
    ev = expected_value(posterior, rr)
    if ev <= 0.0:
        rejected.append(f"EV<=0 ({ev:.3f}) con rr={rr:.2f}")
        return Selection(sym, posterior, ev, sector, reasons, rejected)

    reasons.append(f"posterior {posterior:.3f}>=threshold {threshold:.3f}")
    reasons.append(f"EV {ev:.3f} con rr {rr:.2f}")
    return Selection(sym, posterior, ev, sector, reasons, rejected)


def select_portfolio(candidates: list[dict[str, Any]],
                     regime_offset: float = 0.0,
                     base_threshold: float = 0.75,
                     max_positions: int = MAX_POSITIONS,
                     max_per_sector: int = MAX_PER_SECTOR) -> dict[str, Any]:
    """Elige las mejores ideas con controles de diversificacion."""
    threshold = _threshold_with_regime(base_threshold, regime_offset)

    selected: list[Selection] = []
    rejected: list[Selection] = []
    for row in candidates:
        sel = evaluate_candidate(row, threshold)
        (selected if not sel.rejected else rejected).append(sel)

    # Ordenar por EV (no por posterior puro: importa que el area sea buena).
    selected.sort(key=lambda s: s.event_value, reverse=True)

    # Diversificacion: top por EV con topes de posiciones y sector.
    final: list[Selection] = []
    per_sector: dict[str, int] = {}
    for sel in selected:
        if len(final) >= max_positions:
            rejected.append(_cap(sel, "max_positions"))
            continue
        sec = sel.sector or "UNKNOWN"
        if per_sector.get(sec, 0) >= max_per_sector:
            rejected.append(_cap(sel, f"sector {sec}"))
            continue
        per_sector[sec] = per_sector.get(sec, 0) + 1
        final.append(sel)

    return {
        "threshold": threshold,
        "regime_offset": regime_offset,
        "selected": [s.__dict__ for s in final],
        "ran_out_of_budget": [
            s.__dict__ for s in selected
            if s.symbol not in {f.symbol for f in final}
        ],
        "rejected": [s.__dict__ for s in rejected],
    }


def _cap(sel: Selection, why: str) -> Selection:
    sel.rejected.append(why)
    return sel