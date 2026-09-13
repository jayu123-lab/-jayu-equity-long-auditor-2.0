"""JAYU EQUITY POSITION STATES — seguimiento y outcomes (secciones 30-32).

Maquina de estados del ciclo de vida de una posicion LONG swing. Nunca SHORT.
Los outcomes alimentan la calibracion (posterior -> resultado), registrando
tambien MFE/MAE y duracion.

Estados:
    CANDIDATE   -> cumple calidad, a la espera de entrada
    WAIT_ENTRY  -> posterior alto pero precio no en zona -> no perseguir
    ENTRY_VALID -> zona de entrada alcanzada
    BUY         -> posicion abierta
    HOLD        -> en posicion, reevaluacion del posterior (reduce/exit)
    TP1_HIT     -> objetivo 1 cumplido (participacion parcial)
    TP2_HIT     -> objetivo 2 cumplido (cierre completo)
    STOPPED     -> SL alcanzado
    EXPIRED     -> el catalizador/tiempo caducó sin entrada o sin TP
    REDUCED     -> tamano reducido por gestion (HOLD continua con parte)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PositionRecord:
    symbol: str
    posterior: float
    state: str = "CANDIDATE"
    entry_price: Optional[float] = None
    stop: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    size: Optional[float] = None
    opened_ts: Optional[str] = None
    closed_ts: Optional[str] = None
    high_while_holding: Optional[float] = None
    low_while_holding: Optional[float] = None
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None
    outcome: Optional[str] = None          # WIN / PARTIAL / LOSS / BREAKEVEN / EXPIRED
    history: list[dict[str, Any]] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)

    def _log(self, action: str, note: str = "") -> None:
        from datetime import datetime, timezone
        self.history.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "from": self.state, "action": action, "note": note,
        })

    def enter(self, price: float, stop: float, tp1: float, tp2: float,
              size: float) -> None:
        from datetime import datetime, timezone
        self.entry_price = float(price)
        self.stop = float(stop)
        self.tp1 = float(tp1)
        self.tp2 = float(tp2)
        self.size = float(size)
        self.opened_ts = datetime.now(timezone.utc).isoformat()
        self.state = "BUY"
        self._log("ENTER", f"px={price} sl={stop} tp1={tp1} tp2={tp2} size={size}")

    def hold(self, price: float, note: str = "") -> None:
        if self.entry_price is None:
            return
        if self.high_while_holding is None or price > self.high_while_holding:
            self.high_while_holding = float(price)
        if self.low_while_holding is None or price < self.low_while_holding:
            self.low_while_holding = float(price)
        self.state = "HOLD"
        self._log("HOLD", note)

    def reduce(self, note: str = "") -> None:
        self.state = "REDUCED"
        self._log("REDUCE", note)

    def close_outcome(self, outcome: str, price: Optional[float] = None,
                      note: str = "") -> None:
        from datetime import datetime, timezone
        self.outcome = str(outcome).upper()
        self.closed_ts = datetime.now(timezone.utc).isoformat()
        self._compute_r(); self.state = {"WIN": "TP2_HIT", "PARTIAL": "TP1_HIT",
            "LOSS": "STOPPED", "BREAKEVEN": "STOPPED"}.get(self.outcome, self.state)
        self._log("CLOSE", f"outcome={self.outcome} {note}".strip())

    def _compute_r(self) -> None:
        if self.entry_price is None or self.stop is None or self.stop >= self.entry_price:
            return
        risk = self.entry_price - self.stop
        if self.high_while_holding is not None:
            self.mfe_r = round((self.high_while_holding - self.entry_price) / risk, 2)
        if self.low_while_holding is not None:
            self.mae_r = round((self.low_while_holding - self.entry_price) / risk, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "posterior": self.posterior,
            "state": self.state, "entry_price": self.entry_price,
            "stop": self.stop, "tp1": self.tp1, "tp2": self.tp2,
            "size": self.size, "opened_ts": self.opened_ts,
            "closed_ts": self.closed_ts, "mfe_r": self.mfe_r, "mae_r": self.mae_r,
            "outcome": self.outcome,
        }


def outcome_for_position(rec: PositionRecord, price: float,
                         tolerance: float = 0.01) -> Optional[str]:
    """Determina outcome segun precio actual (LINIES; tolerancia >0 evita falsos)."""
    if rec.entry_price is None or rec.stop is None:
        return None
    if price is None:
        return None
    if price <= rec.stop * (1.0 + tolerance):
        rec.close_outcome("LOSS", price)
        return rec.outcome
    if rec.tp2 and price >= rec.tp2 * (1.0 - tolerance):
        rec.close_outcome("WIN", price)
        return rec.outcome
    if rec.tp1 and price >= rec.tp1 * (1.0 - tolerance):
        rec.close_outcome("PARTIAL", price)
        return rec.outcome
    return None