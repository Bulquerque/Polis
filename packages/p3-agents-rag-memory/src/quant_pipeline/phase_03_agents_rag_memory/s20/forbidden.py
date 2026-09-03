from __future__ import annotations

from typing import Any

FORBIDDEN = {
    "future_return",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "buy_sell_signal",
    "api_key",
    "authorization",
    "bearer_token",
    "holdout_target",
}


def reject_forbidden_fields(value: Any, path: str = "root") -> None:
    """Reject forbidden fields recursively at every untrusted boundary."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN:
                raise ValueError(f"forbidden field at {path}.{key}")
            reject_forbidden_fields(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            reject_forbidden_fields(nested, f"{path}[{index}]")
