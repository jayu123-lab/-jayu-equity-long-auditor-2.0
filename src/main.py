from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from .config import load_settings
from .equity.pipeline import candidate_thesis, candidate_to_signal, scan_and_select
from .faro_client import send_to_faro
from .market_data import fetch_snapshot
from .models import Signal
from .openai_decision import decide
from .scoring import market_regime_score, prefilter_symbol, validate_signal
from .telegram import build_legacy_summary, build_scan_summary, send_telegram_message


def log(event: str, **fields: object) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _require_faro(settings) -> bool:
    if not settings.faro_webhook_url:
        log("config_error", message="FARO_WEBHOOK_URL is required when DRY_RUN=false")
        return False
    if not settings.faro_api_token:
        log("config_error", message="FARO_API_TOKEN is required when DRY_RUN=false")
        return False
    return True


def _publish(settings, signal: Signal) -> bool:
    """Publica y devuelve True si se envió. Un rechazo de FARO no tumba el job."""
    try:
        send_to_faro(
            settings.faro_webhook_url,
            signal,
            settings.faro_api_token,
            settings.faro_process_id,
            settings.faro_strategy_id,
            settings.faro_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        log("faro_rejected", symbol=signal.symbol, signal=signal.model_dump(),
            error=str(exc))
        return False
    log("sent_to_faro", signal=signal.model_dump())
    return True


def _notify(settings, text: str) -> None:
    """Envía aviso a Telegram si está habilitado y configurado. Nunca rompe."""
    if not settings.telegram_enabled:
        log("telegram_skipped", reason="TELEGRAM_ENABLED=false")
        return
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log("telegram_skipped", reason="TELEGRAM_BOT_TOKEN/CHAT_ID no configurados")
        return
    ok = send_telegram_message(text, settings.telegram_bot_token,
                               settings.telegram_chat_id)
    log("telegram_sent" if ok else "telegram_failed",
        length=len(text), ok=ok)


def _run_legacy(settings) -> int:
    """Flujo original: OpenAI decide la señal, auditor publica (BAYES_MODE=false)."""
    regime = [snapshot for symbol in settings.regime_symbols
              if (snapshot := fetch_snapshot(symbol))]
    regime_score = market_regime_score(regime)
    log("regime", score=regime_score, symbols=[item.model_dump() for item in regime])

    sent = 0
    no_trade: list[str] = []
    rejected: list[str] = []
    symbols = [settings.force_symbol] if settings.force_symbol else settings.watchlist
    for symbol in symbols:
        snapshot = fetch_snapshot(symbol)
        if snapshot is None:
            log("skip", symbol=symbol, reason="no market data")
            continue

        ok, reason = prefilter_symbol(snapshot, regime_score)
        if not ok and not settings.force_send:
            log("skip", symbol=symbol, reason=reason, snapshot=snapshot.model_dump())
            rejected.append(symbol)
            continue
        if not ok and settings.force_send:
            log("force_override", symbol=symbol, prefilter_reason=reason, mode="bypass-prefilter")

        decision = decide(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            symbol_snapshot=snapshot,
            regime=regime,
            min_confidence=settings.min_confidence,
        )

        if decision.action == "NO_TRADE" or decision.signal is None:
            log("no_trade", symbol=symbol, notes=decision.notes)
            no_trade.append(symbol)
            continue

        valid, validation_reason = validate_signal(decision.signal, settings.min_confidence)
        if not valid:
            log("rejected_signal", symbol=symbol, reason=validation_reason,
                signal=decision.signal.model_dump())
            rejected.append(symbol)
            continue

        if not _require_faro(settings):
            return 2
        if _publish(settings, decision.signal):
            sent += 1
        if sent >= settings.max_signals_per_run:
            break

    _notify(settings, build_legacy_summary(sent, no_trade, rejected))
    log("scan_complete", mode="legacy", signals=sent, dry_run=settings.dry_run,
        audit_only=settings.audit_only, force_symbol=settings.force_symbol,
        force_send=settings.force_send)
    return 0


def _run_bayes(settings) -> int:
    """Flujo bayesiano: scanner -> ranking (EV+diversificación) -> plan -> tesis -> FARO."""
    log("bayes_start", threshold=settings.bayes_base_threshold,
        earnings_policy=settings.bayes_earnings_policy,
        horizon=settings.bayes_horizon,
        openai_thesis=settings.bayes_openai_thesis)

    out = scan_and_select(
        settings.watchlist,
        earnings_policy=settings.bayes_earnings_policy,
        horizon=settings.bayes_horizon,
        base_threshold=settings.bayes_base_threshold,
        max_positions=settings.max_signals_per_run,
        force_symbol=settings.force_symbol,
    )

    log("bayes_regime", tags=out["regime"]["tags"], score=out["regime"]["score"],
        threshold=out["threshold"])
    for fail in out["failed"]:
        log("bayes_scan_failed", symbol=fail.get("symbol"),
            errors=fail.get("errors"))
    for rank, row in enumerate(out["ranked"], 1):
        plan = row.get("plan") or {}
        log("bayes_ranked", rank=rank, symbol=row["symbol"],
            posterior=row.get("posterior"), state=row.get("state"),
            n_evidence=row.get("n_evidence"), n_groups=row.get("n_groups"),
            plan_valid=plan.get("valid"))

    if not _require_faro(settings):
        return 2

    sent = 0
    published: list[dict] = []
    for merged in out["selected"]:
        symbol = merged["symbol"]
        signal = candidate_to_signal(merged)
        if signal is None:
            log("bayes_candidate_incomplete", symbol=symbol)
            continue
        signal.reason = candidate_thesis(
            merged,
            api_key=settings.openai_api_key if settings.bayes_openai_thesis else None,
            model=settings.openai_model,
            use_openai=settings.bayes_openai_thesis,
        )

        valid, validation_reason = validate_signal(signal, settings.min_confidence)
        if not valid:
            log("rejected_signal", symbol=symbol, reason=validation_reason,
                signal=signal.model_dump())
            continue

        if _publish(settings, signal):
            sent += 1
            published.append({
                "symbol": symbol,
                "posterior": merged.get("posterior"),
                "event_value": merged.get("event_value"),
                "plan": (merged.get("row") or {}).get("plan"),
            })
        if sent >= settings.max_signals_per_run:
            break

    _notify(settings, build_scan_summary(out, published, mode="bayes"))
    log("scan_complete", mode="bayes", signals=sent, dry_run=settings.dry_run,
        audit_only=settings.audit_only, force_symbol=settings.force_symbol,
        force_send=settings.force_send, selected=len(out["selected"]),
        rejected=len(out["portfolio"]["rejected"]))
    return 0


def main() -> int:
    settings = load_settings()
    if settings.dry_run:
        log(
            "dry_run_ready",
            message="Configuration loaded. No OpenAI or FARO calls are made while DRY_RUN=true.",
            audit_only=settings.audit_only,
            process_id=settings.faro_process_id,
            strategy_id=settings.faro_strategy_id,
            watchlist_size=len(settings.watchlist),
            bayes_mode=settings.bayes_mode,
        )
        return 0

    if not settings.openai_api_key and settings.bayes_mode \
            and settings.bayes_openai_thesis:
        # La tesis bayes es funcional sin OpenAI (determinista); solo advertimos.
        log("notice",
            message="OPENAI_API_KEY not set: bayes thesis will be deterministic.")

    if settings.bayes_mode:
        return _run_bayes(settings)

    if not settings.openai_api_key:
        log("config_error", message="OPENAI_API_KEY is required")
        return 2

    return _run_legacy(settings)


if __name__ == "__main__":
    sys.exit(main())