"""JAYU EQUITY SCANNER — orquesta el pipeline bayesiano por simbolo.

Para cada simbolo de la watchlist:
  1. contexto tecnico swing (EquityContext)
  2. datos: fundamentales, earnings, macro, sector, RS
  3. evidencias (evidence_engine)
  4. regimen de mercado (regime) y prior ajustado
  5. posterior (BayesianEngine)
  6. quality gate -> IGNORE/WATCH/CANDIDATE/BUY
  7. plan (entry/SL/TP) si aplica

Resultado: ranking ordenado por posterior con auditoria completa. No envia
nada a FARO; la publicacion la decide el invocador (main.py).
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..market_data import MarketSnapshot
from . import data as edata
from .context import EquityContext
from .engine import BayesianEngine, AdaptivePriors
from .evidence_engine import build_all_evidence
from .plan import compute_plan
from .quality_gate import check_quality
from .regime import classify_market_regime


def _snapshot_dict(sym: str) -> Optional[dict[str, Any]]:
    snap = edata.fetch_snapshot(sym)
    if snap is None:
        return None
    if isinstance(snap, MarketSnapshot):
        return snap.__dict__
    return snap


def _regime_from_macro(macro: dict[str, Any]) -> Any:
    indexes = []
    for name, snapd in macro.get("indexes", {}).items():
        if isinstance(snapd, dict):
            snapd = dict(snapd)
            snapd.setdefault("symbol", name)
            try:
                indexes.append(MarketSnapshot(**snapd))
            except Exception:
                continue
    return classify_market_regime(
        indexes,
        vix_level=macro.get("vix"),
        tnx_trend=macro.get("tnx_trend"),
        dxy_bias=macro.get("dxy_bias"),
        hyg_above_lqd=macro.get("hyg_above_lqd"),
    )


def scan_symbol(symbol: str, macro: dict[str, Any], engine: BayesianEngine,
                priors: AdaptivePriors, regime: Any,
                earnings_policy: str = "AVOID",
                horizon: str = "SWING") -> dict[str, Any]:
    """Evalua un simbolo. Devuelve dict con posterior/state/evidences/plan."""
    started = time.time()
    sym = str(symbol).upper()
    out: dict[str, Any] = {
        "symbol": sym, "ok": False, "errors": [],
        "data_missing": [], "posterior": None, "state": "IGNORE",
        "regime_tags": list(regime.tags if regime else []),
    }

    ctx = EquityContext.build(sym)
    if ctx.close is None:
        out["errors"].append("sin datos tecnicos")
        return out

    f = edata.fetch_fundamentals(sym)
    earnings = edata.fetch_earnings_date(sym)
    snap = _snapshot_dict(sym)
    sector_trend = edata.fetch_sector_trend((f or {}).get("sector")) if f else None
    rs = edata.relative_strength_vs_spy(snap) if snap else None

    for label, value in (
        ("fundamentals", f), ("earnings", earnings), ("snapshot", snap),
        ("sector", sector_trend),
    ):
        if value is None:
            out["data_missing"].append(label)

    evidence = build_all_evidence(
        sym, snap, f, earnings, macro, sector_trend, rs,
        regime=list(regime.tags if regime else []),
        horizon=horizon, earnings_policy=earnings_policy,
    )

    def _ev_count() -> int:
        return len(evidence)

    # Prior ajustado por regimen (y shrinkage por historial del simbolo).
    base_prior = priors.prior_long(sym, horizon, list(regime.tags if regime else []),
                                   default=0.5)
    prior = min(0.9, max(0.10, base_prior * getattr(regime, "prior_adjustment", 1.0)))

    result = engine.evaluate(sym, evidence, prior_long=prior,
                             horizon=horizon, regime=list(regime.tags if regime else []))
    posterior = result["posterior_long"]

    gate = check_quality(posterior, evidence, result, rr=None)

    plan = None
    if gate.state in ("CANDIDATE", "BUY"):
        plan = compute_plan(ctx, posterior, gate.state,
                            earnings_date=(earnings or {}).get("earnings_date"),
                            earnings_policy=earnings_policy)

    out.update({
        "ok": True,
        "close": ctx.close,
        "change_1d_pct": ctx.change_1d_pct,
        "atr_pct": ctx.atr_pct,
        "weekly_trend_score": ctx.weekly_trend_score,
        "trend_score": ctx.trend_score,
        "range_pos_52w": ctx.range_pos_52w,
        "sector": (f or {}).get("sector"),
        "marketCap": (f or {}).get("marketCap"),
        "n_evidence": _ev_count(),
        "posterior": round(posterior, 4),
        "prior": round(prior, 4),
        "state": gate.state,
        "gate": gate.to_dict(),
        "plan": plan.to_dict() if plan else None,
        "positive_evidence": result["positive_evidence"],
        "negative_evidence": result["negative_evidence"],
        "n_groups": result["n_groups"],
        "avg_reliability": result["avg_reliability"],
        "uncertainty": result["uncertainty"],
        "elapsed_s": round(time.time() - started, 2),
        "data_missing": out["data_missing"],
        "errors": out["errors"],
    })
    return out


def scan_watchlist(watchlist: list[str],
                   earnings_policy: str = "AVOID",
                   horizon: str = "SWING",
                   verbose: bool = False) -> list[dict[str, Any]]:
    engines = BayesianEngine()
    priors = AdaptivePriors()
    macro = edata.fetch_macro()
    regime = _regime_from_macro(macro)

    results = []
    for sym in watchlist:
        try:
            res = scan_symbol(sym, macro, engines, priors, regime,
                              earnings_policy=earnings_policy, horizon=horizon)
        except Exception as exc:  # noqa: BLE001
            res = {"symbol": sym, "ok": False,
                   "errors": [f"{type(exc).__name__}: {exc}"]}
        results.append(res)
        if verbose:
            print(f"{sym:<6} p={res.get('posterior')} {res.get('state')} "
                  f"ev={res.get('n_evidence')} err={res.get('errors')}")

    ranked = sorted(
        [r for r in results if r.get("ok")],
        key=lambda r: float(r.get("posterior") or 0.0), reverse=True,
    )
    failed = [r for r in results if not r.get("ok")]
    return {"ranked": ranked, "failed": failed, "regime": {
        "tags": regime.tags, "score": regime.regime_score,
        "buy_threshold_offset": regime.buy_threshold_offset, "evidence": regime.evidence,
    }}