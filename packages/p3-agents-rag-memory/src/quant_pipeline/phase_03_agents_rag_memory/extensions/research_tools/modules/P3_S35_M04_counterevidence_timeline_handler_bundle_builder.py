from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.index_contracts import validate_snapshot_readiness_pair
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.models import (
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.qualification import (
    CorpusQualificationBuilder,
)

MODULE_ID = "P3.S35.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "counterevidence_timeline_handler_bundle_builder"
SUBPHASE = "P3.S35"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S35_M04_counterevidence_timeline_handler_bundle_builder.yaml"
REQUIRED_INPUTS = ("corpus_index_snapshot", "corpus_index_readiness_report")
OPTIONAL_INPUTS = ("corpus_capabilities",)
PRODUCED_OUTPUTS = (
    "corpus_reasoning_handler_bundle",
    "corpus_reasoning_operation_qualification",
)


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    del context
    snapshot = CorpusIndexSnapshot.model_validate(inputs["corpus_index_snapshot"], strict=False)
    readiness = CorpusIndexReadinessReport.model_validate(
        inputs["corpus_index_readiness_report"], strict=False
    )
    validate_snapshot_readiness_pair(snapshot, readiness)
    capabilities = inputs.get("corpus_capabilities", {})
    bundle, qualification = CorpusQualificationBuilder().reasoning_bundle(
        snapshot=snapshot,
        readiness=readiness,
        version_graph_available=bool(
            capabilities.get("version_graph_available", False)
        ),
    )
    return {
        "corpus_reasoning_handler_bundle": bundle.model_dump(mode="json"),
        "corpus_reasoning_operation_qualification": qualification.model_dump(mode="json"),
    }
