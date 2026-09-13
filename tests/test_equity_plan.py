from datetime import date, timedelta

from src.equity.context import EquityContext
from src.equity.plan import compute_plan
from src.equity.states import PositionRecord, outcome_for_position


def soon_earnings(days: int = 3) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def ctx(close: float = 100.0, atr: float = 3.0) -> EquityContext:
    return EquityContext(
        symbol="NVDA", close=close, atr_14=atr, atr_pct=atr / close * 100,
        sma_20=97, sma_50=90, sma_200=80, range_pos_52w=0.9,
    )


def test_plan_atted_sl_and_rr():
    plan = compute_plan(ctx(), posterior=0.8, state="BUY", current_price=100)
    assert plan.valid()
    assert plan.rr >= 1.2
    assert plan.tp1 > plan.entry_price > plan.stop
    assert plan.entry_type == "BUY_MARKET"
    # TP1 debe cumplir el RR minimo del pipeline publicador (validate_signal).
    tp1_rr = (plan.tp1 - plan.entry_price) / (plan.entry_price - plan.stop)
    assert tp1_rr >= 1.2


def test_plan_blocks_earnings_under_avoid_policy():
    plan = compute_plan(ctx(), posterior=0.8, state="BUY",
                        earnings_date=soon_earnings(3), earnings_policy="AVOID")
    assert not plan.valid()
    assert any("earnings" in e.lower() for e in plan.errors)


def test_plan_earnings_reduce_policy_allows():
    plan = compute_plan(ctx(), posterior=0.8, state="BUY",
                        earnings_date=soon_earnings(3), earnings_policy="REDUCE")
    assert plan.valid()
    assert any("REDUCE" in r for r in plan.rationale)


def test_plan_sl_capped_at_8_pct():
    c = ctx(close=10.0, atr=2.0)  # ATR enorme -> 2.5*2 = 50% > 8%
    plan = compute_plan(c, posterior=0.8, state="BUY", current_price=10)
    assert plan.valid()
    assert (10 - plan.stop) / 10 <= 0.0801


def test_position_lifecycle():
    rec = PositionRecord(symbol="NVDA", posterior=0.8, state="CANDIDATE")
    rec.enter(price=100, stop=95, tp1=110, tp2=120, size=100)
    assert rec.state == "BUY"
    rec.hold(105)
    rec.hold(97)  # bajo, aun no stop
    assert rec.high_while_holding == 105
    assert rec.low_while_holding == 97
    assert outcome_for_position(rec, 94) == "LOSS"
    assert rec.outcome == "LOSS"
    assert rec.state == "STOPPED"


def test_position_tp_hit_partial():
    rec = PositionRecord(symbol="NVDA", posterior=0.8)
    rec.enter(100, 95, 110, 120, 100)
    rec.hold(115)
    out = outcome_for_position(rec, 115)
    assert out == "PARTIAL"
    assert rec.mfe_r == 3.0


def test_position_mfe_mae_r():
    rec = PositionRecord(symbol="NVDA", posterior=0.8)
    rec.enter(100, 95, 110, 120, 100)
    rec.hold(96)
    rec.hold(104)
    rec.close_outcome("LOSS", 94)
    assert rec.mae_r == -0.8
    assert rec.mfe_r == 0.8