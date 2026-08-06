"""
AI Explanation: every alert must ship with a natural-language reason.

Default mode is a deterministic template built from the actual numbers
(no external dependency, always available, fully testable/reproducible).
If ANTHROPIC_API_KEY is set in the environment, explain_alert() will instead
ask Claude to turn the same numbers into a more conversational explanation —
the template output is passed in as grounding context so the model cannot
invent numbers that aren't in the data.
"""
from __future__ import annotations

import os
from typing import Sequence


def _template_explanation(symbol: str, alert_type: str, change: float, sessions: int, rows: Sequence) -> str:
    direction = "risen" if alert_type == "flow_surge" else "fallen"
    latest = rows[-1]
    first = rows[0]

    price_change_pct = 0.0
    if first["price"]:
        price_change_pct = ((latest["price"] - first["price"]) / first["price"]) * 100

    relvol = latest["relative_volume"] or 0.0

    if alert_type == "flow_surge":
        return (
            f"{symbol}: Institutional Flow Score has {direction} by {change:+.1f} points "
            f"over the last {sessions} sessions (now {latest['institutional_flow_score']:.1f}). "
            f"Price moved {price_change_pct:+.1f}% over the same period, with the latest session's "
            f"relative volume at {relvol:.2f}x its recent average. This pattern is consistent with "
            f"accumulation-style buying pressure building faster than the price has reacted to it."
        )
    else:
        return (
            f"{symbol}: Institutional Flow Score has {direction} by {change:.1f} points "
            f"over the last {sessions} sessions (now {latest['institutional_flow_score']:.1f}). "
            f"Price moved {price_change_pct:+.1f}% over the same period, with the latest session's "
            f"relative volume at {relvol:.2f}x its recent average. This pattern is consistent with "
            f"institutional selling or a fading interest in the stock — treat it as a caution flag, "
            f"not necessarily an exit signal on its own."
        )


def explain_alert(symbol: str, alert_type: str, change: float, sessions: int, rows: Sequence) -> str:
    base_explanation = _template_explanation(symbol, alert_type, change, sessions, rows)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return base_explanation

    try:
        return _ai_enhanced_explanation(base_explanation, symbol, alert_type)
    except Exception:
        # Any failure (network, auth, rate limit) — fall back silently.
        # The alert must never be blocked by the explanation layer.
        return base_explanation


def _ai_enhanced_explanation(base_explanation: str, symbol: str, alert_type: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        "Rewrite the following institutional-flow alert explanation in clear, "
        "confident natural language for a retail trader. Keep every number exactly "
        "as given — do not invent or change any figure. Keep it to 2-3 sentences.\n\n"
        f"Alert type: {alert_type}\nSymbol: {symbol}\n\nGrounding data:\n{base_explanation}"
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
    result = "\n".join(text_blocks).strip()
    return result or base_explanation
