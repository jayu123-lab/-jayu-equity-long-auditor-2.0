from __future__ import annotations

import requests

from .models import Signal


def build_faro_payload(signal: Signal, api_token: str, process_id: str, strategy_id: str) -> dict[str, object]:
    payload = signal.model_dump()
    payload.update(
        {
            "token": api_token,
            "process_id": process_id,
            "terminal_id": process_id,
            "strategy_id": strategy_id,
            "magic": strategy_id,
        }
    )
    return payload


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
    response.raise_for_status()
    return response

