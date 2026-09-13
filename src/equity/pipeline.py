"""JAYU EQUITY PIPELINE — pega scanner + ranking + plan + tesis para publicar.

Es la entrada que main.py usa en modo bayes (BAYES_MODE). Flujo:
    scan (por simbolo) -> ranking (EV + diversificacion) -> Signal -> tesis.
Se respetan FORCE_SYMBOL / FORCE_SEND con las mismas garantias del pipeline
legacy: el signal final pasa tambien por validate_signal de src/scoring.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Signal
from .ranking import select_portfolio
from .scanner import scan_symbol, scan_watchlist
from .thesis import compose_thesis, refine_with_openai


def _regime_bundle(regime: Any) -> dict[str, Any]:
    if regime is None:
        return {"tags": [], "score": 0, "buy_threshold_offset": 0.0,
                "evidence": []}
    return {
        "tags": list(getattr(regime, "tags", [])),
        "score": getattr(regime, "regime_score", 0),
        "buy_threshold_offset": getattr(regime, "buy_threshold_offset", 0.0),
        "evidence": list(getattr(regime, "evidence", [])),
    }


def scan_and_select(
    watchlist: list[str],
    earnings_policy: str = "AVOID",
    horizon: str = "SWING",
    base_threshold: float = 0.75,
    max_positions: int = 3,
    max_per_sector: int = 2,
    force_symbol: Optional[str] = None,
) -> dict[str, Any]:
    """Escanea y selecciona el portfolio accionable (sin publicar todavia)."""
    res = scan_watchlist(watchlist, earnings_policy=earnings_policy,
                         horizon=horizon)
    regime = res["regime"]
    rows = res["ranked"]

    if force_symbol:
        rows = [r for r in rows if r["symbol"] == force_symbol]

    portfolio = select_portfolio(
        rows,
        regime_offset=float(regime.get("buy_threshold_offset", 0.0) or 0.0),
        base_threshold=base_threshold,
        max_positions=max_positions,
        max_per_sector=max_per_sector,
    )

    selected = []
    for sel in portfolio["selected"]:
        row = next((r for r in rows if r["symbol"] == sel["symbol"]), None)
        if row is None:
            continue
        merged = dict(sel)
        merged["row"] = row
        selected.append(merged)

    return {
        "selected": selected,
        "portfolio": portfolio,
        "regime": regime,
        "ranked": rows,
        "failed": res["failed"],
        "threshold": portfolio["threshold"],
    }


def candidate_to_signal(merged: dict[str, Any]) -> Optional[Signal]:
    """Convierte un candidato seleccionado en Signal (sin tesis todavia)."""
    row = merged["row"]
    plan = row.get("plan") or {}
    if not plan.get("valid"):
        return None
    entry = plan.get("entry_price") or row.get("close")
    if not entry:
        return None
    confidence = max(1, min(100, int(round(float(row.get("posterior") or 0.0) * 100))))
    return Signal(
        symbol=row["symbol"],
        direction="LONG",
        entry=float(entry),
        stop_loss=float(plan["stop"]),
        take_profit_1=float(plan["tp1"]),
        take_profit_2=float(plan["tp2"]),
        confidence=confidence,
        timeframe="swing",
        setup="bayes_equity_long_swing_v1",
        reason="",
        invalidation=str((plan.get("invalidation") or {}).get("rule", "")
                        .strip() or "cierre diario bajo estructura de soporte"),
    )


def candidate_thesis(merged: dict[str, Any], api_key: Optional[str] = None,
                     model: Optional[str] = None,
                     use_openai: bool = True) -> str:
    """Tesis para publicar: determinista siempre; OpenAI si se pide y existe."""
    row = merged["row"]
    selection_for_thesis = {
        "symbol": row.get("symbol"),
        "posterior": row.get("posterior"),
        "prior": row.get("prior"),
        "event_value": merged.get("event_value"),
        "n_groups": row.get("n_groups"),
        "n_evidence": row.get("n_evidence"),
        "regime_tags": row.get("regime_tags"),
        "positive_evidence": row.get("positive_evidence"),
        "negative_evidence": row.get("negative_evidence"),
        "gate": row.get("gate"),
        "plan": row.get("plan"),
    }
    draft = compose_thesis(selection_for_thesis)
    if use_openai and api_key:
        return refine_with_openai(api_key, model or "gpt-4.1-mini",
                                  selection_for_thesis, draft) or draft
    return draft