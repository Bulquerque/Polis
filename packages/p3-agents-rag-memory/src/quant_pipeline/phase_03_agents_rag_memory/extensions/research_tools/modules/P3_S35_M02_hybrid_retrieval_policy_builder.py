from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.index_contracts import validate_snapshot_readiness_pair
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.models import (
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.policy import (
    CorpusRetrievalPolicyBuilder,
)

MODULE_ID = "P3.S35.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "hybrid_retrieval_policy_builder"
SUBPHASE = "P3.S35"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S35_M02_hybrid_retrieval_policy_builder.yaml"
REQUIRED_INPUTS = ("corpus_index_snapshot", "corpus_index_readiness_report")
OPTIONAL_INPUTS = ("retrieval_policy_config",)
PRODUCED_OUTPUTS = ("corpus_retrieval_policy", "corpus_internal_work_budget")


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
    policy, budget = CorpusRetrievalPolicyBuilder().build(
        snapshot=snapshot,
        readiness=readiness,
        config=inputs.get("retrieval_policy_config"),
    )
    return {
        "corpus_retrieval_policy": policy.model_dump(mode="json"),
        "corpus_internal_work_budget": budget.model_dump(mode="json"),
    }
