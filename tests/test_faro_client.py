from src.faro_client import MIN_FARO_EXPLANATION_LENGTH, build_explanation, build_faro_payload
from src.models import Signal
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
    assert payload["strategy_id"] == "equity-long-swing-d1"
    explanation = payload["explanation"]
    assert len(explanation) >= MIN_FARO_EXPLANATION_LENGTH


def test_build_explanation_is_at_least_faro_minimum():
    explanation = build_explanation(signal())
    assert len(explanation) >= MIN_FARO_EXPLANATION_LENGTH
    assert "Strong trend" in explanation


def test_build_explanation_pads_when_signal_has_no_text():
    s = signal()
    s.reason = ""
    s.invalidation = ""
    s.setup = ""
    explanation = build_explanation(s)
    assert len(explanation) >= MIN_FARO_EXPLANATION_LENGTH
    assert s.symbol in explanation


def test_build_explanation_handles_minimal_signal():
    s = Signal(
        symbol="XYZ",
        direction="LONG",
        entry=10,
        stop_loss=9,
        take_profit_1=11,
        take_profit_2=12,
        confidence=80,
        timeframe="daily",
        setup="breakout",
        reason="Clear breakout above resistance with volume.",
        invalidation="Close below entry.",
    )
    explanation = build_explanation(s)
    assert len(explanation) >= MIN_FARO_EXPLANATION_LENGTH
