from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.index_contracts import validate_snapshot_readiness_pair
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.models import (
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
    CorpusOperationQualificationPanel,
    CorpusRetrievalPolicy,
    CorpusInternalWorkBudget,
    HandlerBundleManifest,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.qualification import (
    CorpusQualificationBuilder,
)

MODULE_ID = "P3.S35.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "corpus_tool_bundle_qualification_builder"
SUBPHASE = "P3.S35"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S35_M05_corpus_tool_bundle_qualification_builder.yaml"
REQUIRED_INPUTS = ('corpus_index_snapshot', 'corpus_index_readiness_report', 'corpus_retrieval_policy', 'corpus_internal_work_budget', 'corpus_document_handler_bundle', 'corpus_reasoning_handler_bundle', 'corpus_document_operation_qualification', 'corpus_reasoning_operation_qualification')
PRODUCED_OUTPUTS = (
    "corpus_tool_handler_bundle",
    "corpus_operation_mode_qualification",
    "corpus_tool_readiness_report",
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
    policy = CorpusRetrievalPolicy.model_validate(inputs["corpus_retrieval_policy"], strict=False)
    budget = CorpusInternalWorkBudget.model_validate(inputs["corpus_internal_work_budget"], strict=False)
    if policy.snapshot_id != snapshot.snapshot_id:
        raise ValueError("corpus retrieval policy snapshot_id does not match corpus snapshot")
    if budget.policy_id != policy.policy_id:
        raise ValueError("corpus work budget policy_id does not match retrieval policy")
    document_bundle = HandlerBundleManifest.model_validate(
        inputs["corpus_document_handler_bundle"], strict=False
    )
    reasoning_bundle = HandlerBundleManifest.model_validate(
        inputs["corpus_reasoning_handler_bundle"], strict=False
    )
    document_qualification = CorpusOperationQualificationPanel.model_validate(
        inputs["corpus_document_operation_qualification"], strict=False
    )
    reasoning_qualification = CorpusOperationQualificationPanel.model_validate(
        inputs["corpus_reasoning_operation_qualification"], strict=False
    )
    bundle, qualification, report = CorpusQualificationBuilder().consolidate(
        snapshot=snapshot,
        readiness=readiness,
        document_bundle=document_bundle,
        reasoning_bundle=reasoning_bundle,
        panels=(document_qualification, reasoning_qualification),
    )
    return {
        "corpus_tool_handler_bundle": bundle.model_dump(mode="json"),
        "corpus_operation_mode_qualification": qualification.model_dump(mode="json"),
        "corpus_tool_readiness_report": report.model_dump(mode="json"),
    }
