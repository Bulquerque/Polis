from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.contracts.execution import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import create_gateway_runtime
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly_support import family_reports
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.models import QualificationStatus

from ._fixtures import echo_operation


def test_gateway_runtime_honors_explicit_snapshot_without_run_identity():
    context = ModuleExecutionContext(services={"research_tool_operations": (echo_operation(),)})
    gateway = create_gateway_runtime(context=context, inputs={"snapshot_id": "explicit-snapshot"})
    assert gateway._snapshot_id == "explicit-snapshot"


def test_family_report_mapping_preserves_family_tool_id():
    normalized = family_reports({
        "quant.diagnostics.v1": {
            "records": [{
                "operation_id": "return_statistics", "mode_id": "BASIC",
                "handler_id": "quant.return_statistics.v1",
                "status": QualificationStatus.QUALIFIED_LOCAL.value,
            }]
        }
    })
    record = normalized[0]["records"][0]
    assert record["family_tool_id"] == "quant.diagnostics.v1"
