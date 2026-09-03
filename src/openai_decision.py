from __future__ import annotations

import json

from openai import OpenAI
from pydantic import ValidationError

from .models import Decision, MarketSnapshot


SYSTEM_PROMPT = """You are JAYU Equity Long Auditor.
You generate audit-only US equity trade ideas.
Hard rules:
- Only LONG signals are allowed.
- Never set execution=true.
- Prefer NO_TRADE unless the setup is statistically strong.
- Minimum reward/risk is 1:2 to TP1.
- Do not reject solely for low relative volume: if the trend is strong, price is above key moving averages and there is a clear invalidation level, you may issue a LONG even with modest volume. Avoid weak trends and unclear invalidation.
- Return strict JSON matching the requested schema.
- When you return a SIGNAL, every numeric field (entry, stop_loss, take_profit_1, take_profit_2) must be a real number, never null. confidence must be an integer 0-100.
- When you return NO_TRADE, set signal to null.
"""

SIGNAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "agent": {"type": "string"},
        "mode": {"type": "string", "enum": ["audit_only"]},
        "symbol": {"type": "string"},
        "direction": {"type": "string", "enum": ["LONG"]},
        "entry": {"type": "number"},
        "stop_loss": {"type": "number"},
        "take_profit_1": {"type": "number"},
        "take_profit_2": {"type": "number"},
        "confidence": {"type": "integer"},
        "timeframe": {"type": "string"},
        "setup": {"type": "string"},
        "reason": {"type": "string"},
        "invalidation": {"type": "string"},
        "execution": {"type": "boolean", "enum": [False]},
        "audit": {"type": "boolean", "enum": [True]},
    },
    "required": [
        "agent",
        "mode",
        "symbol",
        "direction",
        "entry",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "confidence",
        "timeframe",
        "setup",
        "reason",
        "invalidation",
        "execution",
        "audit",
    ],
}

DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"enum": ["SIGNAL", "NO_TRADE"]},
        "signal": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": SIGNAL_SCHEMA["properties"],
            "required": SIGNAL_SCHEMA["required"],
        },
        "notes": {"type": "string"},
    },
    "required": ["action", "signal", "notes"],
}


def parse_decision(content: str) -> Decision:
    try:
        return Decision.model_validate_json(content or "{}")
    except ValidationError as exc:
        return Decision(
            action="NO_TRADE",
            notes=f"OpenAI returned an invalid decision payload: {exc.errors()}",
        )


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
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "jayu_decision",
                "strict": True,
                "schema": DECISION_SCHEMA,
            },
        },
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    return parse_decision(content)

