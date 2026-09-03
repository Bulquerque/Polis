from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.s19.errors import S19Error, S19InputError
from quant_pipeline.phase_03_agents_rag_memory.s19.forbidden import reject_forbidden_fields
from quant_pipeline.phase_03_agents_rag_memory.s19.heartbeat_scheduler import (
    build_cognitive_cycle_schedule,
)
from quant_pipeline.phase_03_agents_rag_memory.s19.models import (
    ActivationPanel,
    CurrentPersonStatePanelInput,
    HeartbeatConfig,
    ValidatedPopulationManifestInput,
)

MODULE_ID = "P3.S19.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "monthly_heartbeat_scheduler"
SUBPHASE = "P3.S19"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
IMPLEMENTED = True
CONTRACT = "modules/P3_S19_M02_monthly_heartbeat_scheduler.yaml"
REQUIRED_INPUTS = [
    "activation_panel",
    "current_person_state_panel",
    "validated_population_manifest",
    "heartbeat_config",
]
PRODUCED_OUTPUTS = ('cognitive_cycle_schedule',)


@deprecated_legacy_entrypoint("P3.S19.M02")
def run_module(inputs: dict, config: dict | None = None) -> dict:
    """Execute the functional P3.S19.M02 implementation."""

    try:
        reject_forbidden_fields(inputs)
        reject_forbidden_fields(config or {})
        missing = [name for name in REQUIRED_INPUTS if name not in inputs]
        if missing:
            raise ValueError(f"missing required inputs: {','.join(missing)}")
        result = build_cognitive_cycle_schedule(
            ActivationPanel.model_validate(inputs["activation_panel"]),
            CurrentPersonStatePanelInput.model_validate(
                inputs["current_person_state_panel"]
            ),
            ValidatedPopulationManifestInput.model_validate(
                inputs["validated_population_manifest"]
            ),
            HeartbeatConfig.model_validate(inputs["heartbeat_config"]),
        )
        return {"cognitive_cycle_schedule": result.model_dump(mode="json")}
    except S19Error:
        raise
    except Exception as exc:
        raise S19InputError(f"{MODULE_ID} input validation failed: {exc}") from exc

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

