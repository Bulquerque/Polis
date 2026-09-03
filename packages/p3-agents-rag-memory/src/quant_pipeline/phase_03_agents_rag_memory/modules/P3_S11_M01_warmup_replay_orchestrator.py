from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any


MODULE_ID = "P3.S11.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S11_M01_warmup_replay_orchestrator.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "warmup_event_schedule", "warmup_checkpoint_plan", "person_seed_panel",
    "validated_initial_social_graph", "active_retro_policy_patch",
    "canonical_cycle_pipeline_config", "warmup_replay_config",
)
PRODUCED_OUTPUTS = ("initial_cycle_state_snapshot", "warmup_replay_audit")


async def run_module(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise ValueError(f"P3.S11.M01 missing inputs: {missing}")
    service = context.get("warmup_replay_orchestrator")
    if service is None or not callable(getattr(service, "run", None)):
        raise ValueError("context.warmup_replay_orchestrator must provide async run(...) ")
    result = await service.run(**{name: inputs[name] for name in REQUIRED_INPUTS})
    if isinstance(result, dict):
        expected = set(PRODUCED_OUTPUTS)
        if set(result) != expected:
            raise ValueError(f"canonical warm-up service returned {sorted(result)}; expected {sorted(expected)}")
        return result
    return {
        "initial_cycle_state_snapshot": result.initial_cycle_state_snapshot.model_dump(mode="json"),
        "warmup_replay_audit": result.warmup_replay_audit.model_dump(mode="json"),
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
MODULE_NAME = 'warmup_replay_orchestrator'
SUBPHASE = 'P3.S11'
