from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..foundation.warmup_memory.history import validate_warmup_history

MODULE_ID = "P3.S9.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "warmup_history_validator"
SUBPHASE = "P3.S9"
CONTRACT = "modules/P3_S9_M01_warmup_history_validator.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = [
    "warmup_history_bundle",
    "phase3_run_snapshot",
    "evaluation_window_config",
]
PRODUCED_OUTPUTS = ('validated_warmup_history',)


@deprecated_legacy_entrypoint("P3.S9.M01")
def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Validate warm-up history and return only the declared S9 artifact.

    The module fails by raising WarmupHistoryValidationError. It never returns a
    partial validated_warmup_history artifact.
    """
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        from ..foundation.warmup_memory.history import (
            ValidationIssue,
            WarmupHistoryValidationError,
        )

        raise WarmupHistoryValidationError(
            [
                ValidationIssue(
                    code="P3_S9_M01_INPUT_MISSING",
                    message=f"Missing required input: {name}",
                    path=f"inputs.{name}",
                )
                for name in missing
            ]
        )

    event_sink = None
    if config is not None:
        candidate = config.get("event_sink")
        if callable(candidate):
            event_sink = candidate

    result = validate_warmup_history(
        warmup_history_bundle=inputs["warmup_history_bundle"],
        phase3_run_snapshot=inputs["phase3_run_snapshot"],
        evaluation_window_config=inputs["evaluation_window_config"],
        event_sink=event_sink,
    )
    return {"validated_warmup_history": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

