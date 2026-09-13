from src.equity.thesis import compose_thesis

MIN_FARO_LEN = 200


def selection():
    return {
        "symbol": "SMCI",
        "posterior": 0.86,
        "prior": 0.50,
        "event_value": 1.36,
        "n_groups": 11,
        "n_evidence": 15,
        "regime_tags": ["RISK_ON", "CREDIT_OK"],
        "positive_evidence": [
            {"category": "FUNDAMENTAL", "evidence_type": "EPS_GROWTH",
             "direction": "BULLISH", "strength": 0.8},
            {"category": "TECHNICAL", "evidence_type": "swing_uptrend",
             "direction": "BULLISH", "strength": 0.9},
        ],
        "negative_evidence": [
            {"category": "MACRO", "evidence_type": "rates_rising_duration",
             "direction": "BEARISH", "strength": 0.4},
        ],
        "gate": {"posterior": 0.86},
        "plan": {
            "entry_price": 40.1, "stop": 36.892, "tp1": 44.11, "tp2": 47.318,
            "rr": 1.75,
            "invalidation": {"rule": "cierre diario bajo estructura"},
        },
    }


def test_thesis_is_long_enough_for_faro():
    t = compose_thesis(selection())
    assert len(t) >= MIN_FARO_LEN


def test_thesis_reports_prior_separately_from_posterior():
    t = compose_thesis(selection())
    assert "86%" in t          # posterior
    assert "50%" in t          # prior (no debe confundirse con el posterior)


def test_thesis_includes_plan_numbers_and_risks():
    t = compose_thesis(selection()).lower()
    assert "40.10" in t and "36.89" in t       # entry + stop redondeado a 2 dec
    assert "riesgos" in t                       # riesgos citados
    assert "regimen" in t                      # tags de regimen


def test_thesis_honest_with_minimal_data():
    t = compose_thesis({"symbol": "X", "posterior": 0.8, "prior": 0.5,
                        "n_groups": 1, "n_evidence": 2, "regime_tags": []})
    assert "0.80" in t or "80%" in t