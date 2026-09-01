from src.faro_client import build_faro_payload
from tests.test_scoring import signal


def test_build_faro_payload_uses_native_agent_contract():
    payload = build_faro_payload(
        signal(),
        api_token="secret-token",
        process_id="jayu-equity-long-auditor",
        strategy_id="equity-long-swing-d1",
    )

    assert payload["token"] == "secret-token"
    assert payload["terminal_id"] == "jayu-equity-long-auditor"
    assert payload["ticker"] == "NVDA"
    assert payload["bias"] == "long"
    assert payload["sl"] == 95
    assert payload["tp1"] == 111
    assert payload["tp2"] == 120
    assert payload["entry_market"] is True
    assert payload["reduce_to_size"] is True
    assert payload["audit"] is True
