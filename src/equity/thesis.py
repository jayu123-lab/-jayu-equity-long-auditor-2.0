"""JAYU EQUITY THESIS — justificacion de la senal (campo `thesis` de FARO).

La tesis es la explicacion completa de POR QUE se publica: posterior, prior,
EV, regimen, evidencias a favor/contra y numeros del plan. Todo proviene de
los datos reales capturados (auditable). En modo bayes el posterior es
decimal del modelo, no confianza arbitraria.

OpenAI (opcional) refina el redactado usando la misma evidencia; si falla o
la respuesta es corta, se usa la tesis determinista (>= 200 chars para FARO).
"""

from __future__ import annotations

import json
from typing import Any, Optional

_EVIDENCE_TOP = 3          # cuantas evidencias positivas se citan
_EVIDENCE_BOTTOM = 2       # cuantas negativas se muestran


def _fmt_perc(v: Any) -> str:
    try:
        return f"{float(v):.0%}"
    except (TypeError, ValueError):
        return "n/d"


def _describe(rec: dict[str, Any]) -> str:
    """Una evidencia del trace del engine en texto corto y honesto."""
    cat = str(rec.get("category") or "?").lower()
    etype = str(rec.get("evidence_type") or "?").replace("_", " ")
    direction = str(rec.get("direction") or "NEUTRAL").lower()
    strength = float(rec.get("strength") or 0.0)
    return f"{etype} ({cat}, {direction}, fx {strength:.2f})"


def compose_thesis(selection: dict[str, Any]) -> str:
    """Tesis determinista completa desde el resultado del scanner+ranking."""
    symbol = selection.get("symbol")
    posterior = selection.get("posterior")
    prior = selection.get("prior")
    ev = selection.get("event_value")
    n_groups = selection.get("n_groups")
    n_ev = selection.get("n_evidence")
    regime_tags = selection.get("regime_tags") or []

    plan = selection.get("plan") or {}
    rr = plan.get("rr")
    stop = plan.get("stop")
    tp1 = plan.get("tp1")
    tp2 = plan.get("tp2")
    entry = plan.get("entry_price")

    negative = [r for r in selection.get("negative_evidence", [])]
    positive = [r for r in selection.get("positive_evidence", [])]
    top_pos = positive[: _EVIDENCE_TOP]
    bottom_neg = negative[: _EVIDENCE_BOTTOM]

    parts = [
        f"JAYU LONG {symbol} (EQUITY_LONG_SWING_V1): posterior LONG {_fmt_perc(posterior)}",
    ]
    if prior is not None:
        parts.append(f"prior {_fmt_perc(prior)}")
    if ev is not None:
        parts.append(f"EV +{float(ev):.2f} R" if float(ev) > 0 else f"EV {float(ev):.2f} R")
    parts.append(f"{n_groups} grupos / {n_ev} evidencias")
    if rr:
        parts.append(f"RR {rr:.2f} (50/50 TP1/TP2)")
    if entry and stop and tp1 and tp2:
        parts.append(
            f"plan: entrada ~{entry:.2f}, SL {stop:.2f}, TP1 {tp1:.2f}, TP2 {tp2:.2f}"
        )
    if regime_tags:
        parts.append("regimen: " + ", ".join(regime_tags))
    if top_pos:
        parts.append("a favor: " + "; ".join(_describe(r) for r in top_pos))
    if bottom_neg:
        parts.append("riesgos: " + "; ".join(_describe(r) for r in bottom_neg))

    inval = (plan.get("invalidation") or {}).get("rule")
    if inval:
        parts.append(f"invalidation: {inval}")

    return ". ".join(parts).strip()


def refine_with_openai(api_key: str, model: str, selection: dict[str, Any],
                       draft: str) -> str:
    """Refina la tesis con OpenAI. Nunca lanza: devuelve `draft` si falla."""
    if not api_key:
        return draft
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        system = (
            "Eres JAYU Equity Long Auditor. Reescribes la tesis de una senal "
            "LONG swing usando SOLO los datos reales proporcionados. "
            "No inventes numeros ni hechos. La tesis debe tener ~200-420 caracteres "
            ", tecnica, honesta, y terminar con el plan (SL/TP) e invalidacion."
        )
        user_content = json.dumps(
            {
                "selection": {k: selection.get(k) for k in (
                    "symbol", "posterior", "event_value", "n_groups",
                    "n_evidence", "regime_tags", "positive_evidence",
                    "negative_evidence")},
                "plan": selection.get("plan"),
            },
            ensure_ascii=False, default=str,
        )
        resp = client.chat.completions.create(
            model=model, temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            max_tokens=200,
        )
        text = (resp.choices[0].message.content or "").strip()
        if len(text) < 20:  # no sirve: volver al borrador honesto
            return draft
        return text[:500]
    except Exception:  # noqa: BLE001 - fallback determinista siempre
        return draft