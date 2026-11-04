"""Token → USD estimates for spend tracking (Anthropic first-party list prices, $/MTok: input, cache read, cache write, output)."""
from __future__ import annotations

PRICES = {"claude-opus-5": (5.0, 0.5, 6.25, 25.0), "claude-sonnet-5": (2.0, 0.2, 2.5, 10.0), "claude-haiku": (1.0, 0.1, 1.25, 5.0)}


def usage_cost_usd(model: str, usage) -> float:
    u = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage or {})
    p = next((v for k, v in PRICES.items() if model.startswith(k)), PRICES["claude-opus-5"])
    return (u.get("input_tokens", 0) * p[0] + (u.get("cache_read_input_tokens") or 0) * p[1] + (u.get("cache_creation_input_tokens") or 0) * p[2] + u.get("output_tokens", 0) * p[3]) / 1e6
