from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import S19ForbiddenFieldError

FORBIDDEN_FIELDS = {
    "future_return",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "buy_sell_signal",
    "realized_pnl",
    "holdout_label",
}


def reject_forbidden_fields(value: Any, path: str = "$") -> None:
    """Reject forbidden fields recursively before model validation."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_FIELDS:
                raise S19ForbiddenFieldError(
                    f"forbidden field {key_text!r} found at {path}"
                )
            reject_forbidden_fields(item, f"{path}.{key_text}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            reject_forbidden_fields(item, f"{path}[{index}]")
