"""JAYU EQUITY TELEGRAM — notificacion diaria del scan (seccion integracion).

Usa el mismo patron que Jayu-Orion: Bot API `sendMessage` con parse_mode HTML.
Reutiliza el bot TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID de ORION (mismo chat).
Nunca lanza en caso de error ni rompe el job: si no hay credenciales o falla,
se registra y se continua. En DRY_RUN no se envia nada (no hacer calls externos).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests


def _fmt_perc(v: Any) -> str:
    try:
        return f"{float(v):.0%}"
    except (TypeError, ValueError):
        return "n/d"


def send_telegram_message(text: str, bot_token: str, chat_id: str,
                          timeout_seconds: int = 10) -> bool:
    """Envía el texto a Telegram. Sin token/chat o a error -> False, nunca lanza."""
    if not text or not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML"}
        response = requests.post(url, json=payload, timeout=timeout_seconds)
        return response.status_code == 200
    except Exception:  # noqa: BLE001 - un fallo de Telegram no tumba el job
        return False


# ---------------------------------------------------------------------------
# Construccion del mensaje del scan bayesiano
# ---------------------------------------------------------------------------
def build_scan_summary(out: dict[str, Any], published: list[dict[str, Any]],
                       mode: str = "bayes") -> str:
    """Resumen diario HTML: publicado / o 'no hay setup hoy' + top-3 del ranking."""
    day = datetime.now(timezone.utc).strftime("%d %b %Y")
    regime = out.get("regime") or {}
    tags = ", ".join(regime.get("tags", []) or []) or "sin datos"
    score = regime.get("score")
    if mode == "bayes":
        header = f"📊 <b>JAYU Equity Long</b> · {day}\n<b>Régimen:</b> {tags}"
    else:
        header = f"📊 <b>JAYU Equity Long</b> · {day} (legacy)"

    lines = [header]
    if score is not None:
        lines.append(f"Score régimen {score:+.0f}")

    if published:
        lines.append("")
        lines.append("✅ <b>Señal(es) publicadas:</b>")
        for pub in published:
            plan = pub.get("plan") or {}
            lines.append(
                f"🟢 {pub.get('symbol')} · posterior {_fmt_perc(pub.get('posterior'))}"
                f" · EV {pub.get('event_value'):+.2f}R"
                f" · SL {plan.get('stop')} TP {plan.get('tp1')}/{plan.get('tp2')}"
            )
    else:
        lines.append("")
        lines.append("❗ <b>No hay setup hoy, sorry guys</b> — nada cruza los umbrales "
                     "de calidad (posterior, gate y plan validado).")
        lines.append("")

        top3 = (out.get("ranked") or [])[:3]
        if top3:
            lines.append("🔎 <b>Top-3 del ranking</b> (información, no trade):")
            for row in top3:
                pos_ev = None
                # event_value solo existe en los seleccionados; usamos posterior.
                lines.append(
                    f"• {row.get('symbol')} · posterior {_fmt_perc(row.get('posterior'))}"
                    f" · {row.get('state')}"
                )
        else:
            lines.append("(sin candidatos evaluables hoy)")

    return "\n".join(lines)


def build_legacy_summary(signals_sent: int, no_trade: list[str],
                         rejected: list[str]) -> str:
    day = datetime.now(timezone.utc).strftime("%d %b %Y")
    lines = [f"📊 <b>JAYU Equity Long</b> · {day} (legacy)"]
    if signals_sent:
        lines.append(f"✅ Señales publicadas: {signals_sent}")
    else:
        lines.append("❗ <b>No hay setup hoy, sorry guys</b> — ningún símbolo "
                     "superó el análisis.")
    if no_trade:
        lines.append("Sin trade: " + ", ".join(no_trade) + ("" if len(no_trade) <= 5
                     else f" (+{len(no_trade)-5} más)"))
    if rejected:
        lines.append("Rechazadas: " + ", ".join(rejected[:5]))
    return "\n".join(lines)