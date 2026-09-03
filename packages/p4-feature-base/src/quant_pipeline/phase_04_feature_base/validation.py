from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .economic_errors import ContractError, TemporalIntegrityError
from .economic_models import CanonicalObservationPanel, ExecutionContext, ObserverExecutionRegistry

FORBIDDEN_FIELDS = {
    "target",
    "label",
    "future_return",
    "future_volatility",
    "prediction",
    "signal_direction",
    "buy_sell_signal",
    "candidate_id",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "realized_pnl",
    "execution_fill",
    "position_size",
}


def find_forbidden_fields(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key) in FORBIDDEN_FIELDS:
                found.append(child)
            found.extend(find_forbidden_fields(item, child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            found.extend(find_forbidden_fields(item, f"{path}[{index}]"))
    return found


def parse_inputs(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[
    CanonicalObservationPanel, ObserverExecutionRegistry, ExecutionContext
]:
    missing = [name for name in ("canonical_observation_panel", "approved_observer_execution_registry") if name not in inputs]
    if missing:
        raise ContractError("P4_S4_INPUT_INVALID", f"missing required inputs: {missing}")
    leaked = find_forbidden_fields(inputs)
    if leaked:
        raise ContractError("P4_S4_FORBIDDEN_FIELD", "forbidden fields detected", details={"paths": leaked})
    try:
        panel = CanonicalObservationPanel.model_validate(inputs["canonical_observation_panel"])
        registry = ObserverExecutionRegistry.model_validate(inputs["approved_observer_execution_registry"])
        context = ExecutionContext.model_validate(config)
    except ValueError as exc:
        raise ContractError("P4_S4_SCHEMA_INVALID", str(exc)) from exc
    if panel.run_id != context.run_id or registry.run_id != context.run_id:
        raise ContractError("P4_S4_RUN_MISMATCH", "run_id mismatch across inputs and execution context")
    if panel.cycle_id != context.cycle_id or registry.cycle_id != context.cycle_id:
        raise ContractError("P4_S4_CYCLE_MISMATCH", "cycle_id mismatch across inputs and execution context")
    if panel.as_of_time != context.as_of_time or registry.as_of_time != context.as_of_time:
        raise ContractError("P4_S4_AS_OF_MISMATCH", "as_of_time mismatch across inputs and execution context")
    future = [row.record_lineage_id for row in panel.records if row.available_at > context.as_of_time]
    if future:
        raise TemporalIntegrityError(
            "P4_S4_TEMPORAL_VIOLATION",
            "canonical panel contains observations unavailable at as_of_time",
            details={"lineage_ids": future[:20]},
        )
    return panel, registry, context
