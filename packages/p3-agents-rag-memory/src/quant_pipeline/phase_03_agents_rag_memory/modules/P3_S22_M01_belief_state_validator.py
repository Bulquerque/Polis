from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.beliefs import validate_belief_state
from ..runtime_shared.s21_models import Phase3RunSnapshot, PropositionRegistryConfig, StructuredBeliefProposalPanel
from ..runtime_shared.s22_models import CurrentBeliefStatePanel
from ._s22_wrapper import parse_model, parse_policy

MODULE_ID = "P3.S22.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "belief_state_validator"
SUBPHASE = "P3.S22"
CONTRACT = "modules/P3_S22_M01_belief_state_validator.yaml"
REQUIRED_INPUTS = ["structured_belief_proposal_panel", "current_belief_state_panel", "phase3_run_snapshot", "proposition_registry_config"]
PRODUCED_OUTPUTS = ('validated_belief_update_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S22.M01")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    output = validate_belief_state(
        proposals=parse_model(inputs, "structured_belief_proposal_panel", StructuredBeliefProposalPanel, module_id=MODULE_ID),
        current_state=parse_model(inputs, "current_belief_state_panel", CurrentBeliefStatePanel, module_id=MODULE_ID),
        snapshot=parse_model(inputs, "phase3_run_snapshot", Phase3RunSnapshot, module_id=MODULE_ID),
        proposition_registry=parse_model(inputs, "proposition_registry_config", PropositionRegistryConfig, module_id=MODULE_ID),
        policy=parse_policy(config, module_id=MODULE_ID),
    )
    return {"validated_belief_update_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
