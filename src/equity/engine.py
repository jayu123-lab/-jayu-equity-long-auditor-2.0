"""JAYU BAYESIAN ENGINE V1 — dominio EQUITY_LONG_SWING_V1.

Misma matematica que Jayu-Orion / Jayu MT5:
    odds_prior = P(H)/(1-P(H))
    log_odds_prior = ln(odds_prior)
    log_odds_post = log_odds_prior + SUM(effective_log_LR)
    posterior = exp(lo)/(1+exp(lo))

effective_log_LR(e) = log_LR_raw(e) * reliability * freshness
                      * regime_penalty * correlation_penalty(group_rank)

Los likelihood ratios estan calibrados POR DOMINIO (EQUITY_LONG_SWING_V1),
no son los mismos que ORION. Priors adaptativos con shrinkage.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .evidence import EvidencePacket

ENGINE_VERSION = "JAYU_BAYES_ENGINE_V1"
DOMAIN_VERSION = "EQUITY_LONG_SWING_V1"
MODEL_VERSION = "EQUITY_LONG_SWING_2026_0"

# Horizonte swing: 1-8 semanas (configurable). Half-life largo: las evidencias
# fundamentales/catalizador aguantan semanas; las tecnicas decaen mas rapido.
HORIZON_HALF_LIFE_HOURS = {
    "INTRADAY": 6.0,
    "MULTI_DAY": 48.0,
    "SWING": 24 * 7 * 3.0,   # ~3 semanas: horn baseline de evidencias swing
    "WEEKLY": 24 * 7 * 3.0,
}


def freshness_decay(age_hours: float, half_life_hours: float) -> float:
    if age_hours is None or math.isnan(age_hours):
        return 0.5
    if age_hours <= 0:
        return 1.0
    return math.exp(-abs(age_hours) / max(0.01, half_life_hours))


# ---------------------------------------------------------------------------
# Priors adaptativos con shrinkage (persistencia en data/)
# ---------------------------------------------------------------------------
_PRIORS_DIR = None


def _priors_path() -> str:
    global _PRIORS_DIR
    if _PRIORS_DIR is None:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _PRIORS_DIR = os.path.join(base, "data", "integrations", "equity", "bayes_priors.json")
    return _PRIORS_DIR


class AdaptivePriors:
    def __init__(self, path: Optional[str] = None):
        self.path = path or _priors_path()
        self._store: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        return {}

    def save(self) -> None:
        try:
            d = os.path.dirname(self.path)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._store, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def _key(self, symbol: str, horizon: str, regime: Optional[list[str]]) -> str:
        reg = ",".join(sorted(regime or []))
        return f"{str(symbol).upper()}|{horizon.upper()}|{reg}"

    def prior_long(self, symbol: str, horizon: str = "SWING",
                   regime: Optional[list[str]] = None,
                   default: float = 0.5) -> float:
        key = self._key(symbol, horizon, regime)
        bucket = self._store.get(key, {})
        n = int(bucket.get("n", 0) or 0)
        wins = int(bucket.get("wins", 0) or 0)
        if n <= 0:
            return float(default)
        p_hat = wins / n
        k = float(bucket.get("shrinkage_k", 24.0) or 24.0)
        prior = (n * p_hat + k * float(default)) / (n + k)
        return round(min(0.95, max(0.05, prior)), 4)

    def record(self, symbol: str, horizon: str, regime: Optional[list[str]],
               outcome_win: bool) -> None:
        key = self._key(symbol, horizon, regime)
        bucket = self._store.setdefault(key, {"n": 0, "wins": 0, "shrinkage_k": 24.0})
        bucket["n"] = int(bucket.get("n", 0)) + 1
        if outcome_win:
            bucket["wins"] = int(bucket.get("wins", 0)) + 1


# ---------------------------------------------------------------------------
# Likelihood ratios por categoria (dominio EQUITY_LONG_SWING_V1).
# Valores iniciales conservadores; se calibran con outcomes reales (seccion 9).
# ---------------------------------------------------------------------------
DEFAULT_LR_BY_CATEGORY: dict[str, float] = {
    "FUNDAMENTAL": 1.30,
    "VALUATION": 1.15,
    "EARNINGS": 1.35,
    "CATALYST": 1.35,
    "MACRO": 1.20,
    "SECTOR": 1.25,
    "TECHNICAL": 1.40,
    "SENTIMENT": 1.15,
    "POSITIONING": 1.10,
    "REGIME": 1.20,
    "RISK": 1.05,
}

# Categorias que NO deben mover mucho el posterior (ruido de corto plazo).
LOW_TRUST_CATEGORIES = {
    "SENTIMENT": 1.12,
    "POSITIONING": 1.08,
    "ML": 1.08,
}


class BayesianEngine:
    def __init__(self, priors: Optional[AdaptivePriors] = None,
                 lr_map: Optional[dict[str, float]] = None):
        self.priors = priors or AdaptivePriors()
        self.lr_map = dict(DEFAULT_LR_BY_CATEGORY)
        self.lr_map.update(LOW_TRUST_CATEGORIES)
        if lr_map:
            self.lr_map.update(lr_map)

    def log_lr(self, evidence: EvidencePacket, group_rank: int = 0) -> float:
        cat = str(evidence.category).upper()
        max_lr = self.lr_map.get(cat, 1.2)
        strength = max(0.0, min(1.0, float(evidence.strength)))
        base_lr = 1.0 + strength * (max_lr - 1.0)
        if evidence.sign < 0:
            base_lr = 1.0 / base_lr
        log_lr = math.log(base_lr)
        reliability = max(0.0, min(1.0, float(evidence.reliability)))
        freshness = max(0.0, min(1.0, float(evidence.freshness)))
        regime_penalty = float(getattr(evidence, "_regime_penalty", 1.0) or 1.0)
        # penalty por doble conteo dentro del correlation group: la k-esima 1/sqrt(k)
        group_penalty = 1.0 / math.sqrt(max(1, group_rank))
        return log_lr * reliability * freshness * regime_penalty * group_penalty

    @staticmethod
    def posterior_from_log_odds(log_odds: float) -> float:
        return 1.0 / (1.0 + math.exp(-log_odds))

    def evaluate(self, symbol: str, evidence: list[EvidencePacket],
                 prior_long: Optional[float] = None,
                 horizon: str = "SWING",
                 regime: Optional[list[str]] = None) -> dict[str, Any]:
        symbol = str(symbol).upper()
        horizon = str(horizon).upper()

        prior = prior_long
        if prior is None:
            prior = self.priors.prior_long(symbol, horizon, regime)
        try:
            prior = float(prior)
        except (TypeError, ValueError):
            prior = 0.5
        prior = min(0.95, max(0.05, prior))
        log_odds_prior = math.log(prior / (1.0 - prior))

        groups: dict[str, list[EvidencePacket]] = {}
        for ev in evidence:
            groups.setdefault(ev.correlation_group, []).append(ev)

        positive: list[dict[str, Any]] = []
        negative: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        total_log_lr = 0.0

        for gname, group_evs in groups.items():
            ordered = sorted(group_evs, key=lambda e: e.strength, reverse=True)
            for idx, ev in enumerate(ordered):
                rank = idx + 1
                eff = self.log_lr(ev, group_rank=rank)
                total_log_lr += eff
                rec = {
                    "id": ev.id, "agent": ev.agent, "category": ev.category,
                    "evidence_type": ev.evidence_type, "direction": ev.direction,
                    "strength": ev.strength, "reliability": ev.reliability,
                    "freshness": ev.freshness, "correlation_group": ev.correlation_group,
                    "group_rank": rank, "log_lr": round(eff, 4),
                }
                traces.append(rec)
                target = positive if ev.sign > 0 else negative if ev.sign < 0 else None
                if target is not None:
                    target.append(rec)

        log_odds_post = log_odds_prior + total_log_lr
        posterior_long = self.posterior_from_log_odds(log_odds_post)

        n_groups = len(groups)
        n_evidence = len(evidence)
        avg_rel = (sum(e.reliability for e in evidence) / n_evidence) if n_evidence else 0.0
        avg_fresh = (sum(e.freshness for e in evidence) / n_evidence) if n_evidence else 0.0
        disagreement = self._agent_disagreement(evidence)
        uncertainty = round(min(1.0, (1.0 - avg_rel) * 0.5 + (1.0 - avg_fresh) * 0.3 + disagreement * 0.2), 3)

        return {
            "engine": ENGINE_VERSION,
            "domain": DOMAIN_VERSION,
            "model_version": MODEL_VERSION,
            "symbol": symbol,
            "horizon": horizon,
            "regime": [r for r in (regime or [])],
            "prior_long": round(prior, 4),
            "posterior_long": round(posterior_long, 4),
            "log_odds_prior": round(log_odds_prior, 4),
            "log_odds_posterior": round(log_odds_post, 4),
            "positive_evidence": positive,
            "negative_evidence": negative,
            "n_groups": n_groups,
            "n_evidence": n_evidence,
            "avg_reliability": round(avg_rel, 3),
            "avg_freshness": round(avg_fresh, 3),
            "agent_disagreement": round(disagreement, 3),
            "uncertainty": uncertainty,
            "traces": traces,
        }

    @staticmethod
    def _agent_disagreement(evidence: list[EvidencePacket]) -> float:
        if len(evidence) < 2:
            return 0.0
        signs = [e.sign for e in evidence if e.sign != 0]
        if not signs:
            return 0.2
        long_ratio = sum(1 for s in signs if s > 0) / len(signs)
        return round(abs(long_ratio - 0.5) * 2.0, 3)


# ---------------------------------------------------------------------------
# Registro de outcomes para calibracion (Brier / Log Loss / buckets)
# ---------------------------------------------------------------------------
class CalibrationStore:
    BUCKETS = [(0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.75),
               (0.75, 0.80), (0.80, 0.85), (0.85, 1.01)]

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "integrations", "equity", "bayes_calibration.json")
        self._store: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        return {"records": []}

    def save(self) -> None:
        try:
            d = os.path.dirname(self.path)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._store, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def record_outcome(self, posterior_long: float, direction: str, outcome: str,
                       symbol: str = "", horizon: str = "SWING",
                       regime: Optional[list[str]] = None,
                       model_version: str = MODEL_VERSION) -> None:
        confirmed_win = {"WIN": True, "PARTIAL": True}.get(str(outcome).upper(), False)
        self._store["records"].append({
            "posterior_long": round(float(posterior_long), 4),
            "direction": str(direction).upper(),
            "outcome": str(outcome).upper(),
            "symbol": str(symbol).upper(),
            "horizon": str(horizon).upper(),
            "regime": [r for r in (regime or [])],
            "model_version": model_version,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        self.save()

    def reference_prior(self, symbol: str, horizon: str = "SWING") -> Optional[float]:
        recs = [r for r in self._store.get("records", [])
                if r["symbol"] == str(symbol).upper() and r["horizon"] == str(horizon).upper()]
        if len(recs) < 10:
            return None
        wins = sum(1 for r in recs if r["outcome"] in ("WIN", "PARTIAL"))
        return wins / len(recs)


_engine_instances: dict[str, BayesianEngine] = {}


def get_engine() -> BayesianEngine:
    if "default" not in _engine_instances:
        _engine_instances["default"] = BayesianEngine()
    return _engine_instances["default"]


def compute_posterior(symbol: str, evidence: list[EvidencePacket],
                      prior_long: Optional[float] = None,
                      horizon: str = "SWING",
                      regime: Optional[list[str]] = None) -> dict[str, Any]:
    return get_engine().evaluate(symbol, evidence, prior_long=prior_long,
                                 horizon=horizon, regime=regime)