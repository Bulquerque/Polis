from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.beliefs import bind_evidence
from ..runtime_shared.s21_models import RetrievalEvidenceMap, ValidatedToolResultPanel
from ..runtime_shared.s22_models import GraphEvidenceMap, RagIndexArtifact, ValidatedBeliefUpdatePanel
from ._s22_wrapper import parse_model, parse_policy

MODULE_ID = "P3.S22.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "evidence_binding_validator"
SUBPHASE = "P3.S22"
CONTRACT = "modules/P3_S22_M02_evidence_binding_validator.yaml"
REQUIRED_INPUTS = ["validated_belief_update_panel", "retrieval_evidence_map", "graph_evidence_map", "rag_index_artifact", "validated_tool_result_panel"]
PRODUCED_OUTPUTS = ('evidence_bound_belief_update_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S22.M02")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    output = bind_evidence(
        updates=parse_model(inputs, "validated_belief_update_panel", ValidatedBeliefUpdatePanel, module_id=MODULE_ID),
        retrieval=parse_model(inputs, "retrieval_evidence_map", RetrievalEvidenceMap, module_id=MODULE_ID),
        graph=parse_model(inputs, "graph_evidence_map", GraphEvidenceMap, module_id=MODULE_ID),
        rag=parse_model(inputs, "rag_index_artifact", RagIndexArtifact, module_id=MODULE_ID),
        tool_results=parse_model(inputs, "validated_tool_result_panel", ValidatedToolResultPanel, module_id=MODULE_ID),
        policy=parse_policy(config, module_id=MODULE_ID),
    )
    return {"evidence_bound_belief_update_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
