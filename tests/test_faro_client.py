from src.faro_client import build_faro_payload
from tests.test_scoring import signal


def test_build_faro_payload_adds_agent_identity():
    payload = build_faro_payload(
        signal(),
        api_token="secret-token",
        process_id="jayu-equity-long-auditor",
        strategy_id="equity-long-swing-d1",
    )

    assert payload["token"] == "secret-token"
    assert payload["process_id"] == "jayu-equity-long-auditor"
    assert payload["terminal_id"] == "jayu-equity-long-auditor"
    assert payload["strategy_id"] == "equity-long-swing-d1"
    assert payload["magic"] == "equity-long-swing-d1"
    assert payload["direction"] == "LONG"
    assert payload["execution"] is False
    assert payload["audit"] is True

