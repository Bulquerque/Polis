from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models import ExecutionContext


def context_from_config(config: Mapping[str, Any] | None) -> ExecutionContext:
    """Build an immutable execution context from a phase-compatible config mapping."""
    config_mapping = dict(config or {})
    context_value = dict(config_mapping.get("execution_context", config_mapping))
    # P2/P6 legacy boundary callers pass the pre-V14.9 phase config, which has
    # pipeline_version/created_at/as_of_date but no public ExecutionContext
    # envelope.  Keep that compatibility path deterministic and local while
    # leaving the integrated runner strict: new callers still provide all
    # context identifiers explicitly.
    if "run_id" not in context_value:
        context_value["run_id"] = "legacy-module-run"
    if "cycle_id" not in context_value:
        context_value["cycle_id"] = "legacy-module-cycle"
    if "as_of_time" not in context_value:
        context_value["as_of_time"] = context_value.get(
            "as_of_date", context_value.get("created_at")
        )
    return ExecutionContext.from_mapping(context_value)


def module_response(
    *,
    module_id: str,
    module_name: str,
    required_inputs: Sequence[str],
    outputs: Mapping[str, Any],
    subphase: str = "P4.S1",
) -> dict[str, Any]:
    """Return the stable module envelope used by the other project phases."""
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "phase_04_feature_base",
        "subphase": subphase,
        "required_inputs": list(required_inputs),
        "outputs": dict(outputs),
    }
