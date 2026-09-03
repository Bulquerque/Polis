from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.tooling import validate_tool_results
from ..runtime_shared.s21_models import (
    Phase3RunSnapshot,
    RawToolResultPanel,
    RetrievalEvidenceMap,
    ToolCallAuditPanel,
)
from ._s21_wrapper import parse_model

MODULE_ID = "P3.S21.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "tool_result_validator"
SUBPHASE = "P3.S21"
CONTRACT = "modules/P3_S21_M04_tool_result_validator.yaml"
REQUIRED_INPUTS = ['raw_tool_result_panel', 'tool_call_audit_panel', 'phase3_run_snapshot', 'retrieval_evidence_map']
PRODUCED_OUTPUTS = ('validated_tool_result_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S21.M04")
def run_module(
    inputs: Mapping[str, object],
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    del config
    output = validate_tool_results(
        raw_results=parse_model(
            inputs, "raw_tool_result_panel", RawToolResultPanel, module_id=MODULE_ID
        ),
        audit_panel=parse_model(
            inputs, "tool_call_audit_panel", ToolCallAuditPanel, module_id=MODULE_ID
        ),
        snapshot=parse_model(
            inputs, "phase3_run_snapshot", Phase3RunSnapshot, module_id=MODULE_ID
        ),
        retrieval_evidence=parse_model(
            inputs, "retrieval_evidence_map", RetrievalEvidenceMap, module_id=MODULE_ID
        ),
    )
    return {"validated_tool_result_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
