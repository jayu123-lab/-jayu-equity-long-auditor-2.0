from src.openai_decision import DECISION_SCHEMA, parse_decision


def test_decision_schema_forces_strict_signal_object():
    props = DECISION_SCHEMA["properties"]
    signal = props["signal"]
    assert signal["type"] == ["object", "null"]
    assert signal["additionalProperties"] is False
    required = set(signal["required"])
    assert {"entry", "stop_loss", "take_profit_1", "take_profit_2"}.issubset(required)
    assert props["action"]["enum"] == ["SIGNAL", "NO_TRADE"]
    assert "notes" in DECISION_SCHEMA["required"]


def test_invalid_signal_payload_can_be_downgraded_to_no_trade():
    raw = """
    {
      "action": "SIGNAL",
      "signal": {
        "symbol": "NVDA",
        "direction": "LONG",
        "entry": null,
        "stop_loss": null,
        "take_profit_1": null,
        "take_profit_2": null,
        "confidence": 82,
        "timeframe": "swing",
        "setup": null,
        "reason": "Incomplete payload.",
        "invalidation": "Incomplete payload."
      }
    }
    """

    decision = parse_decision(raw)

    assert decision.action == "NO_TRADE"
    assert decision.signal is None
    assert "invalid decision payload" in decision.notes

