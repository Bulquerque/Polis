from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..foundation.warmup_memory.scheduling import SchedulingIssue, WarmupScheduleBuildError, build_warmup_schedule

MODULE_ID = "P3.S10.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "warmup_scheduler"
SUBPHASE = "P3.S10"
CONTRACT = "modules/P3_S10_M01_warmup_scheduler.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = [
    "validated_warmup_history", "validated_population_manifest",
    "validated_initial_social_graph", "activation_config", "heartbeat_config",
]
PRODUCED_OUTPUTS = ('warmup_event_schedule',)


@deprecated_legacy_entrypoint("P3.S10.M01")
def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, object]:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise WarmupScheduleBuildError([
            SchedulingIssue("P3_S10_M01_INPUT_MISSING", f"Missing required input: {name}", f"inputs.{name}")
            for name in missing
        ])
    event_sink = None
    if config is not None and callable(config.get("event_sink")):
        event_sink = config["event_sink"]
    result = build_warmup_schedule(
        validated_warmup_history=inputs["validated_warmup_history"],
        validated_population_manifest=inputs["validated_population_manifest"],
        validated_initial_social_graph=inputs["validated_initial_social_graph"],
        activation_config=inputs["activation_config"],
        heartbeat_config=inputs["heartbeat_config"],
        event_sink=event_sink,
    )
    return {"warmup_event_schedule": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

