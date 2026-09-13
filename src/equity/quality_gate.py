"""JAYU EQUITY QUALITY GATE — umbrales y decisiones (secciones 22-24).

Transforma el posterior en un estado accionable para acciones USA LONG swing,
exigiendo calidad ANTES de considerar entrada. La decision le pertenece al
pipeline del auditor; aqui solo se define la logica de umbrales.

Buckets (pendiente de calibracion con datos):
    < 0.60         IGNORE
    [0.60, 0.68)   WATCH         -> se vigila, no se opera
    [0.68, 0.75)   CANDIDATE     -> datado para entrada (el posterior del
                                    engine se mantiene un tiempo por antes;
                                    evidencia fresca se requiere al ejecutar)
    >= 0.75        BUY           -> verde si ademas pasa los requisitos
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .evidence import EvidencePacket

BUCKET_IGNORE_HI = 0.60
BUCKET_WATCH_HI = 0.68
BUCKET_CANDIDATE_HI = 0.75

# Requisitos minimos de calidad (se define el de al menos una de cada dos
# cuando el posterior este alto; el riesgo se gestiona en la posicion).
MIN_EVIDENCE = 3
MIN_GROUPS = 2
MIN_AVG_RELIABILITY = 0.55
MIN_AVG_FRESHNESS = 0.60
MAX_UNCERTAINTY = 0.75
MIN_RR = 1.2        # reward:risk minimo (alineado con el auditor)

DECISION_ORDER = ("IGNORE", "WATCH", "CANDIDATE", "BUY")


@dataclass
class QualityResult:
    posterior: float
    threshold: float
    state: str                    # IGNORE / WATCH / CANDIDATE / BUY
    n_evidence: int
    n_groups: int
    avg_reliability: float
    avg_freshness: float
    uncertainty: float
    tt_n_evidence: Optional[int] = None
    tt_n_groups: Optional[int] = None
    tt_avg_reliability: Optional[float] = None
    tt_avg_freshness: Optional[float] = None
    tt_uncertainty: Optional[float] = None
    rr: Optional[float] = None
    ev_risk: Optional[float] = None            # expectancy de cruce (no gama)
    blocked_reasons: list[str] = field(default_factory=list)

    def passed(self) -> bool:
        return self.state == "BUY" and not self.blocked_reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "posterior": self.posterior,
            "threshold": self.threshold,
            "state": self.state,
            "n_evidence": self.n_evidence,
            "n_groups": self.n_groups,
            "avg_reliability": self.avg_reliability,
            "avg_freshness": self.avg_freshness,
            "uncertainty": self.uncertainty,
            "tt_n_evidence": self.tt_n_evidence,
            "tt_n_groups": self.tt_n_groups,
            "tt_avg_reliability": self.tt_avg_reliability,
            "tt_avg_freshness": self.tt_avg_freshness,
            "tt_uncertainty": self.tt_uncertainty,
            "rr": self.rr,
            "ev_risk": self.ev_risk,
            "blocked": self.blocked_reasons,
            "passed": self.passed(),
        }


def classify_state(posterior: float) -> str:
    if posterior < BUCKET_IGNORE_HI:
        return "IGNORE"
    if posterior < BUCKET_WATCH_HI:
        return "WATCH"
    if posterior < BUCKET_CANDIDATE_HI:
        return "CANDIDATE"
    return "BUY"


def state_rank(state: str) -> int:
    return DECISION_ORDER.index(state) if state in DECISION_ORDER else 0


# ---------------------------------------------------------------------------
# Requisitos minimos de calidad (evidencia suficiente y cercana en el tiempo)
# ---------------------------------------------------------------------------
def check_quality(posterior: float,
                  evidence: list[EvidencePacket],
                  engine_result: Optional[dict[str, Any]] = None,
                  rr: Optional[float] = None) -> QualityResult:
    state = classify_state(posterior)
    n_ev = len(evidence)
    n_groups = len({e.correlation_group for e in evidence})
    avg_rel = (sum(e.reliability for e in evidence) / n_ev) if n_ev else 0.0
    avg_fresh = (sum(e.freshness for e in evidence) / n_ev) if n_ev else 0.0
    unc = float(engine_result.get("uncertainty", 0.0)) if engine_result else 0.5

    res = QualityResult(
        posterior=posterior, threshold=BUCKET_CANDIDATE_HI, state=state,
        n_evidence=n_ev, n_groups=n_groups, avg_reliability=round(avg_rel, 3),
        avg_freshness=round(avg_fresh, 3), uncertainty=unc, rr=rr,
    )

    if state == "BUY":
        res.blocked_reasons.extend(_blocked(posterior, evidence, n_ev, n_groups,
                                            avg_rel, avg_fresh, unc, rr))
    return res


def _blocked(posterior, evidence, n_ev, n_groups, avg_rel, avg_fresh, unc, rr):
    reasons: list[str] = []
    if n_ev < MIN_EVIDENCE:
        reasons.append(f"n_evidence<{MIN_EVIDENCE} ({n_ev})")
    if n_groups < MIN_GROUPS:
        reasons.append(f"n_groups<{MIN_GROUPS} ({n_groups})")
    if avg_rel < MIN_AVG_RELIABILITY:
        reasons.append(f"avg_reliability<{MIN_AVG_RELIABILITY} ({avg_rel:.2f})")
    if avg_fresh < MIN_AVG_FRESHNESS:
        reasons.append(f"avg_freshness<{MIN_AVG_FRESHNESS} ({avg_fresh:.2f})")
    if unc > MAX_UNCERTAINTY:
        reasons.append(f"uncertainty>{MAX_UNCERTAINTY} ({unc:.2f})")
    if rr is not None and rr < MIN_RR:
        reasons.append(f"rr<{MIN_RR} ({rr:.2f})")
    return reasons


# ---------------------------------------------------------------------------
# Expectancy de cruce (EDGE) para la senal; NO se envia a FARO sin esto.
# ---------------------------------------------------------------------------
def expectancy(probability_win: float, rr: float, win_recovery: float = 1.0) -> float:
    """Multiplicador esperado del riesgo comprometido: prob_win*rr - (1-prob_win)."""
    p = max(0.0, min(1.0, float(probability_win)))
    r = max(0.0, float(rr))
    return p * r - (1.0 - p)


def brake_value(probability_win: float, win_amount: float, loss_amount: float) -> float:
    """Expectativa en EUR de la configuracion (participacion calculada fuera)."""
    p = max(0.0, min(1.0, float(probability_win)))
    return p * float(win_amount) - (1.0 - p) * abs(float(loss_amount))


def decide(posterior: float, evidence: list[EvidencePacket],
           engine_result: Optional[dict[str, Any]] = None,
           rr: Optional[float] = None) -> QualityResult:
    """Pasarela: posterior -> estado accionable."""
    return check_quality(posterior, evidence, engine_result, rr=rr)