from __future__ import annotations

import requests

from .models import Signal

# Contrato real del agente en FARO (ficha en getfaro.org), igual que el emisor
# automatico ORION: {token, terminal_id, ticker, bias, sl, tp1, tp2, entry_market}.
# La entrada por integracion es SIEMPRE a mercado (FARO la fija al precio real).
def build_faro_payload(signal: Signal, api_token: str, process_id: str, strategy_id: str) -> dict[str, object]:
    return {
        "token": api_token,
        "terminal_id": process_id,
        "ticker": signal.symbol,
        "bias": "long" if signal.direction == "LONG" else "short",
        "sl": signal.stop_loss,
        "tp1": signal.take_profit_1,
        "tp2": signal.take_profit_2,
        "entry_market": True,
        # Auditor: publica senal auditable con posicion reducida (no ejecuta tamano completo).
        "reduce_to_size": True,
        "audit": True,
        "strategy_id": strategy_id,
    }


def send_to_faro(
    webhook_url: str,
    signal: Signal,
    api_token: str,
    process_id: str,
    strategy_id: str,
    timeout_seconds: int = 15,
) -> requests.Response:
    payload = build_faro_payload(signal, api_token, process_id, strategy_id)
    response = requests.post(webhook_url, json=payload, timeout=timeout_seconds)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = ""
        try:
            body = response.text
        except Exception:
            body = "<no body>"
        raise requests.HTTPError(
            f"{exc} | faro_status={response.status_code} faro_body={body}",
            response=response,
        ) from exc
    return response
