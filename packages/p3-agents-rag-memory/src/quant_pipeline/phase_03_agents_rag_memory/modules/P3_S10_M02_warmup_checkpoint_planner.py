from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..foundation.warmup_memory.scheduling import SchedulingIssue, WarmupCheckpointPlanError, build_warmup_checkpoint_plan

MODULE_ID = "P3.S10.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "warmup_checkpoint_planner"
SUBPHASE = "P3.S10"
CONTRACT = "modules/P3_S10_M02_warmup_checkpoint_planner.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ["warmup_event_schedule", "warmup_checkpoint_config"]
PRODUCED_OUTPUTS = ('warmup_checkpoint_plan',)


@deprecated_legacy_entrypoint("P3.S10.M02")
def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, object]:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise WarmupCheckpointPlanError([
            SchedulingIssue("P3_S10_M02_INPUT_MISSING", f"Missing required input: {name}", f"inputs.{name}")
            for name in missing
        ])
    event_sink = None
    if config is not None and callable(config.get("event_sink")):
        event_sink = config["event_sink"]
    result = build_warmup_checkpoint_plan(
        warmup_event_schedule=inputs["warmup_event_schedule"],
        warmup_checkpoint_config=inputs["warmup_checkpoint_config"],
        event_sink=event_sink,
    )
    return {"warmup_checkpoint_plan": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

