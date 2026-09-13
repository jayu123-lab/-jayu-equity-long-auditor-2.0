import requests

from src.telegram import build_legacy_summary, build_scan_summary, send_telegram_message


def scan_out(published=True, ranked=None):
    return {
        "regime": {"tags": ["RISK_ON", "CREDIT_OK"], "score": 10},
        "ranked": ranked if ranked is not None else [
            {"symbol": "SMCI", "posterior": 0.858, "state": "BUY"},
            {"symbol": "AMD", "posterior": 0.819, "state": "BUY"},
            {"symbol": "AAPL", "posterior": 0.816, "state": "BUY"},
        ],
    }


def test_send_message_returns_false_without_credentials(monkeypatch):
    assert not send_telegram_message("hola", "", "")
    assert not send_telegram_message("", "tk", "chat")


def test_send_message_posts_to_bot_api(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    ok = send_telegram_message("hola mundo", "tk123", "chat456", timeout_seconds=7)
    assert ok
    assert "api.telegram.org/bot" in captured["url"] and "/sendMessage" in captured["url"]
    assert captured["json"]["chat_id"] == "chat456"
    assert captured["json"]["parse_mode"] == "HTML"
    assert captured["timeout"] == 7


def test_send_message_survives_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    assert send_telegram_message("hola", "tk", "chat") is False


def test_summary_includes_no_setup_when_nothing_published():
    text = build_scan_summary(scan_out(published=False), published=[])
    assert "No hay setup hoy, sorry guys" in text
    assert "SMCI" in text          # top-3 informativo
    assert "Régimen" in text


def test_summary_shows_published_signals():
    published = [{
        "symbol": "SMCI", "posterior": 0.858, "event_value": 1.36,
        "plan": {"stop": 36.892, "tp1": 44.11, "tp2": 47.318},
    }]
    text = build_scan_summary(scan_out(published=True), published=published)
    assert "Señal(es) publicadas" in text
    assert "SMCI" in text
    assert "No hay setup hoy" not in text


def test_legacy_summary_no_trade():
    text = build_legacy_summary(signals_sent=0, no_trade=["TSLA", "PLTR"], rejected=["NVDA"])
    assert "No hay setup hoy, sorry guys" in text
    assert "TSLA" in text and "PLTR" in text