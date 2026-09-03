from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import S18ForbiddenFieldError

FORBIDDEN_FIELDS = {
    "future_return",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "buy_sell_signal",
    "realized_pnl",
    "holdout_target",
}


def reject_forbidden_fields(value: Any, path: str = "$") -> None:
    """Recursively reject economic authority and future-outcome fields."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_FIELDS:
                raise S18ForbiddenFieldError(f"forbidden field at {path}.{key_text}")
            reject_forbidden_fields(item, f"{path}.{key_text}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            reject_forbidden_fields(item, f"{path}[{index}]")
