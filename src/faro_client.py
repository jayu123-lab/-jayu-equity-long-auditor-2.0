from __future__ import annotations

import requests

from .models import Signal


def send_to_faro(webhook_url: str, signal: Signal, timeout_seconds: int = 15) -> requests.Response:
    payload = signal.model_dump()
    response = requests.post(webhook_url, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    return response

