from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.beliefs import log_commitments
from ..runtime_shared.s21_models import Phase3RunSnapshot
from ..runtime_shared.s22_models import EvidenceBoundBeliefUpdatePanel
from ._s22_wrapper import parse_model, parse_policy

MODULE_ID = "P3.S22.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "belief_outcome_commitment_logger"
SUBPHASE = "P3.S22"
CONTRACT = "modules/P3_S22_M03_belief_outcome_commitment_logger.yaml"
REQUIRED_INPUTS = ["evidence_bound_belief_update_panel", "phase3_run_snapshot"]
PRODUCED_OUTPUTS = ('belief_outcome_commitment_log',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S22.M03")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    output = log_commitments(
        bound_updates=parse_model(inputs, "evidence_bound_belief_update_panel", EvidenceBoundBeliefUpdatePanel, module_id=MODULE_ID),
        snapshot=parse_model(inputs, "phase3_run_snapshot", Phase3RunSnapshot, module_id=MODULE_ID),
        policy=parse_policy(config, module_id=MODULE_ID),
    )
    return {"belief_outcome_commitment_log": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
