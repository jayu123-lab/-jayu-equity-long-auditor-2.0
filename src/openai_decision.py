from __future__ import annotations

import json

from openai import OpenAI

from .models import Decision, MarketSnapshot


SYSTEM_PROMPT = """You are JAYU Equity Long Auditor.
You generate audit-only US equity trade ideas.
Hard rules:
- Only LONG signals are allowed.
- Never set execution=true.
- Prefer NO_TRADE unless the setup is statistically strong.
- Minimum reward/risk is 1:2 to TP1.
- Avoid weak trends, weak volume, and unclear invalidation.
- Return strict JSON matching the requested schema.
"""


def decide(
    api_key: str,
    model: str,
    symbol_snapshot: MarketSnapshot,
    regime: list[MarketSnapshot],
    min_confidence: int,
) -> Decision:
    client = OpenAI(api_key=api_key)
    payload = {
        "min_confidence": min_confidence,
        "symbol": symbol_snapshot.model_dump(),
        "market_regime": [item.model_dump() for item in regime],
        "schema": {
            "action": "SIGNAL or NO_TRADE",
            "signal": {
                "agent": "jayu_equity_long_auditor",
                "mode": "audit_only",
                "symbol": symbol_snapshot.symbol,
                "direction": "LONG",
                "entry": "number",
                "stop_loss": "number below entry",
                "take_profit_1": "number with RR >= 2",
                "take_profit_2": "number above TP1",
                "confidence": "0-100 integer",
                "timeframe": "swing/daily/4h",
                "setup": "breakout/pullback_to_value/reclaim/post_earnings_continuation",
                "reason": "short thesis",
                "invalidation": "clear invalidation",
                "execution": False,
                "audit": True,
            },
            "notes": "short notes",
        },
    }

    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    return Decision.model_validate_json(content)

