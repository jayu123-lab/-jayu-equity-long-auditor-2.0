from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    faro_webhook_url: str
    faro_timeout_seconds: int
    audit_only: bool
    dry_run: bool
    min_confidence: int
    max_signals_per_run: int
    watchlist: list[str]
    regime_symbols: list[str]


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        faro_webhook_url=os.getenv("FARO_WEBHOOK_URL", ""),
        faro_timeout_seconds=int(os.getenv("FARO_TIMEOUT_SECONDS", "15")),
        audit_only=_bool("AUDIT_ONLY", True),
        dry_run=_bool("DRY_RUN", True),
        min_confidence=int(os.getenv("MIN_CONFIDENCE", "80")),
        max_signals_per_run=int(os.getenv("MAX_SIGNALS_PER_RUN", "3")),
        watchlist=_csv(
            "WATCHLIST",
            "AAPL,MSFT,NVDA,AMD,AVGO,META,GOOGL,AMZN,TSLA,PLTR,CRWD,NET,ORCL,SMCI",
        ),
        regime_symbols=_csv("REGIME_SYMBOLS", "SPY,QQQ,IWM"),
    )

