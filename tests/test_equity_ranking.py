from src.equity.ranking import evaluate_candidate, expected_value, select_portfolio


def buy_row(symbol="NVDA", posterior=0.8, sector="Technology", rr=1.5):
    return {
        "symbol": symbol, "posterior": posterior, "sector": sector,
        "gate": {"passed": True, "blocked": []},
        "plan": {"valid": True, "errors": [], "rr": rr},
    }


def weak_row(symbol="TSLA", posterior=0.6):
    return {
        "symbol": symbol, "posterior": posterior, "sector": "Consumer Cyclical",
        "gate": {"passed": True, "blocked": []},
        "plan": {"valid": True, "errors": [], "rr": 1.5},
    }


def test_expected_value():
    assert abs(expected_value(0.5, 1.0) - 0.0) < 1e-9
    assert expected_value(0.8, 1.5) > 0.979  # 0.8*1.5-0.2
    assert expected_value(0.3, 1.5) < 0


def test_evaluate_requires_threshold():
    sel = evaluate_candidate(weak_row(), threshold=0.75)
    assert sel.rejected and not sel.reasons


def test_evaluate_blocks_invalid_plan():
    row = buy_row()
    row["plan"] = {"valid": False, "errors": ["SL fuera de rango"], "rr": 0.5}
    sel = evaluate_candidate(row, threshold=0.75)
    assert any("plan" in r for r in sel.rejected)


def test_evaluate_blocks_negative_ev():
    row = buy_row(rr=0.2, posterior=0.8)
    sel = evaluate_candidate(row, threshold=0.75)
    assert any("EV" in r for r in sel.rejected)


def test_select_sorts_by_ev_and_diversifies():
    cands = [
        buy_row("A", 0.82, "TECHNOLOGY", 1.7),
        buy_row("B", 0.85, "TECHNOLOGY", 1.6),
        buy_row("C", 0.80, "HEALTHCARE", 1.8),
        buy_row("D", 0.78, "CONSUMER", 1.9),
    ]
    res = select_portfolio(cands, max_positions=3, max_per_sector=1)
    selected = [s["symbol"] for s in res["selected"]]
    assert len(selected) == 3
    assert selected.count("A") + selected.count("B") <= 1  # mismo sector
    # por EV desc: D(1.9*0.78-0.22=1.26) > C(1.8*0.8-0.2=1.24) > A/B
    assert selected[0] == "D"


def test_select_respects_max_positions():
    cands = [buy_row(f"X{i}", 0.8 + i * 0.01, f"S{i}", 2.0) for i in range(5)]
    res = select_portfolio(cands, max_positions=2, max_per_sector=5)
    assert len(res["selected"]) == 2
    assert len(res["ran_out_of_budget"]) == 3


def test_select_rejects_low_posterior_when_regime_hostile():
    cands = [buy_row("A", 0.78, "T", 1.5)]
    res = select_portfolio(cands, regime_offset=0.10)  # threshold 0.85
    assert res["selected"] == []
    assert "posterior" in res["rejected"][0]["rejected"][0].lower()