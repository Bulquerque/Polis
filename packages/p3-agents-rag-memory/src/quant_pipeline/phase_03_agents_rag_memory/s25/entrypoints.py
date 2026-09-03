"""Compatibility helpers for legacy P3 module entrypoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import log_event
from .errors import S25ContractError

FORBIDDEN_FIELDS = {
    "target",
    "future_return",
    "label",
    "prediction",
    "candidate_id",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "realized_pnl",
    "buy_sell_signal",
}


def _scan(value: Any, *, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in FORBIDDEN_FIELDS:
                raise S25ContractError(f"forbidden field at {path}.{key}")
            _scan(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan(child, path=f"{path}[{index}]")


def prepare_inputs(
    *,
    module_id: str,
    inputs: Mapping[str, Any],
    required: tuple[str, ...],
    config_key: str,
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate declared input names and support the legacy config argument."""
    if not isinstance(inputs, Mapping):
        raise S25ContractError("inputs must be a mapping")
    materialized = dict(inputs)
    if config_key not in materialized and config is not None:
        materialized[config_key] = config.get(config_key, config)
    missing = sorted(set(required) - set(materialized))
    extra = sorted(set(materialized) - set(required))
    if missing:
        raise S25ContractError(f"{module_id} missing required inputs: {missing}")
    if extra:
        raise S25ContractError(f"{module_id} received undeclared inputs: {extra}")
    _scan(materialized)
    return materialized


def run_guarded(module_id: str, operation: Any) -> dict[str, Any]:
    """Log typed failure and never emit partial output."""
    try:
        return operation()
    except Exception as exc:
        log_event(
            "module_failed",
            module_id=module_id,
            status="FAILED",
            error_type=type(exc).__name__,
        )
        raise
