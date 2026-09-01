from src import main as app_main
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
