from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from .config import load_settings
from .faro_client import send_to_faro
from .market_data import fetch_snapshot
from .openai_decision import decide
from .scoring import market_regime_score, prefilter_symbol, validate_signal


def log(event: str, **fields: object) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False), flush=True)


def main() -> int:
    settings = load_settings()
    if not settings.openai_api_key:
        log("config_error", message="OPENAI_API_KEY is required")
        return 2

    regime = [snapshot for symbol in settings.regime_symbols if (snapshot := fetch_snapshot(symbol))]
    regime_score = market_regime_score(regime)
    log("regime", score=regime_score, symbols=[item.model_dump() for item in regime])

    sent = 0
    for symbol in settings.watchlist:
        snapshot = fetch_snapshot(symbol)
        if snapshot is None:
            log("skip", symbol=symbol, reason="no market data")
            continue

        ok, reason = prefilter_symbol(snapshot, regime_score)
        if not ok:
            log("skip", symbol=symbol, reason=reason, snapshot=snapshot.model_dump())
            continue

        decision = decide(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            symbol_snapshot=snapshot,
            regime=regime,
            min_confidence=settings.min_confidence,
        )

        if decision.action == "NO_TRADE" or decision.signal is None:
            log("no_trade", symbol=symbol, notes=decision.notes)
            continue

        valid, validation_reason = validate_signal(decision.signal, settings.min_confidence)
        if not valid:
            log("rejected_signal", symbol=symbol, reason=validation_reason, signal=decision.signal.model_dump())
            continue

        if settings.dry_run:
            log("dry_run_signal", signal=decision.signal.model_dump())
        else:
            if not settings.faro_webhook_url:
                log("config_error", message="FARO_WEBHOOK_URL is required when DRY_RUN=false")
                return 2
            send_to_faro(settings.faro_webhook_url, decision.signal, settings.faro_timeout_seconds)
            log("sent_to_faro", signal=decision.signal.model_dump())

        sent += 1
        if sent >= settings.max_signals_per_run:
            break

    log("scan_complete", signals=sent, dry_run=settings.dry_run, audit_only=settings.audit_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())

