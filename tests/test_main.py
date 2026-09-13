from src import main as app_main
from src.models import Signal
from tests.test_scoring import signal, snapshot


def _run(monkeypatch, *, force_send, returned_decision, expect_sent):
    sent = {"count": 0}

    def fake_send(*args, **kwargs):
        sent["count"] += 1

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("FARO_WEBHOOK_URL", "https://farowebhook")
    monkeypatch.setenv("FARO_API_TOKEN", "tk-test")
    monkeypatch.setenv("FORCE_SYMBOL", "NVDA")
    monkeypatch.setenv("FORCE_SEND", force_send)
    monkeypatch.setenv("BAYES_MODE", "false")
    monkeypatch.setattr(app_main, "fetch_snapshot", lambda symbol: snapshot(trend_score=20))
    monkeypatch.setattr(app_main, "decide", lambda **kw: returned_decision)
    monkeypatch.setattr(app_main, "send_to_faro", fake_send)

    code = app_main.main()
    return code, sent["count"]


def test_dry_run_exits_before_external_calls(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert app_main.main() == 0


class _Decision:
    def __init__(self, action, sig):
        self.action = action
        self.signal = sig


def test_force_send_bypasses_prefilter_and_sends_valid_long(monkeypatch):
    code, count = _run(
        monkeypatch,
        force_send="true",
        returned_decision=_Decision("BUY", signal()),
        expect_sent=True,
    )
    assert code == 0
    assert count == 1


def test_force_send_still_blocks_invalid_signal(monkeypatch):
    bad = signal()
    bad.stop_loss = 105  # stop above entry -> invalid
    code, count = _run(
        monkeypatch,
        force_send="true",
        returned_decision=_Decision("BUY", bad),
        expect_sent=False,
    )
    assert code == 0
    assert count == 0


# ---------------------------------------------------------------------------
# Flujo bayesiano (BAYES_MODE=true): scanner -> ranking -> tesis -> FARO
# ---------------------------------------------------------------------------

def _bayes_run(monkeypatch, *, selected_ok=True):
    sent = {"count": 0}

    def fake_send(*args, **kwargs):
        sent["count"] += 1

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("FARO_WEBHOOK_URL", "https://farowebhook")
    monkeypatch.setenv("FARO_API_TOKEN", "tk-test")
    monkeypatch.setenv("BAYES_MODE", "true")
    monkeypatch.setenv("BAYES_OPENAI_THESIS", "false")
    monkeypatch.setattr(app_main, "send_to_faro", fake_send)

    row = {
        "symbol": "NVDA", "close": 100.0, "posterior": 0.81,
        "prior": 0.50, "state": "BUY", "n_groups": 11, "n_evidence": 15,
        "regime_tags": ["RISK_ON"], "positive_evidence": [],
        "negative_evidence": [], "gate": {"passed": True},
        "plan": {"valid": selected_ok, "entry_price": 100.0, "stop": 95.0,
                 "tp1": 110.0, "tp2": 120.0, "rr": 1.5,
                 "invalidation": {"rule": "cierre bajo estructura"}},
    }
    merged = {"symbol": "NVDA", "posterior": 0.81, "event_value": 0.9,
              "sector": "Technology", "reasons": [], "rejected": [], "row": row}
    out = {
        "selected": [merged] if selected_ok else [],
        "portfolio": {"rejected": []},
        "regime": {"tags": ["RISK_ON"], "score": 10, "buy_threshold_offset": 0.0},
        "ranked": [row], "failed": [], "threshold": 0.75,
    }
    monkeypatch.setattr(app_main, "scan_and_select", lambda *a, **k: out)

    code = app_main.main()
    return code, sent["count"]


def test_bayes_publishes_selected_candidates(monkeypatch):
    code, count = _bayes_run(monkeypatch, selected_ok=True)
    assert code == 0
    assert count == 1


def test_bayes_sends_nothing_when_no_selection(monkeypatch):
    code, count = _bayes_run(monkeypatch, selected_ok=False)
    assert code == 0
    assert count == 0


def _bayes_telegram_run(monkeypatch, selected_ok=True):
    sent = {"count": 0}
    tg = {"text": None, "calls": 0}

    def fake_send(*args, **kwargs):
        sent["count"] += 1

    def fake_tg(text, bot_token, chat_id):
        tg["text"] = text
        tg["calls"] += 1
        return True

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("FARO_WEBHOOK_URL", "https://farowebhook")
    monkeypatch.setenv("FARO_API_TOKEN", "tk-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tk-tg")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat-tg")
    monkeypatch.setenv("BAYES_MODE", "true")
    monkeypatch.setenv("BAYES_OPENAI_THESIS", "false")
    monkeypatch.setattr(app_main, "send_to_faro", fake_send)
    monkeypatch.setattr(app_main, "send_telegram_message", fake_tg)

    row = {
        "symbol": "NVDA", "close": 100.0, "posterior": 0.81,
        "prior": 0.50, "state": "BUY", "n_groups": 11, "n_evidence": 15,
        "regime_tags": ["RISK_ON"], "positive_evidence": [],
        "negative_evidence": [], "gate": {"passed": True},
        "plan": {"valid": selected_ok, "entry_price": 100.0, "stop": 95.0,
                 "tp1": 110.0, "tp2": 120.0, "rr": 1.5,
                 "invalidation": {"rule": "cierre bajo estructura"}},
    }
    merged = {"symbol": "NVDA", "posterior": 0.81, "event_value": 0.9,
              "sector": "Technology", "reasons": [], "rejected": [], "row": row}
    out = {
        "selected": [merged] if selected_ok else [],
        "portfolio": {"rejected": []},
        "regime": {"tags": ["RISK_ON"], "score": 10, "buy_threshold_offset": 0.0},
        "ranked": [row], "failed": [], "threshold": 0.75,
    }
    monkeypatch.setattr(app_main, "scan_and_select", lambda *a, **k: out)
    code = app_main.main()
    return code, sent["count"], tg


def test_bayes_notifies_telegram_when_no_setup(monkeypatch):
    code, count, tg = _bayes_telegram_run(monkeypatch, selected_ok=False)
    assert code == 0 and count == 0
    assert tg["calls"] == 1
    assert "No hay setup hoy, sorry guys" in tg["text"]


def test_bayes_notifies_telegram_when_published(monkeypatch):
    code, count, tg = _bayes_telegram_run(monkeypatch, selected_ok=True)
    assert code == 0 and count == 1
    assert tg["calls"] == 1
    assert "Señal(es) publicadas" in tg["text"]
