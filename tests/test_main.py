from src import main as app_main


def test_dry_run_exits_before_external_calls(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert app_main.main() == 0

