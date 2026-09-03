"""Adapter from P3.S35 corpus bundles to the canonical S40 registry."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.factory import create_corpus_runtime_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.models import (
    CorpusFilter,
    CorpusIndexSnapshot,
    CorpusOperationQualificationPanel,
    CorpusRetrievalPolicy,
    CorpusToolCallContext,
    HandlerBundleManifest,
)

from .canonical_support import adapt_result, canonical_context, operation
from .models import QualificationStatus
from .registry import ExecutableOperation


def _status_by_operation(panel: CorpusOperationQualificationPanel | None) -> Mapping[str, QualificationStatus]:
    if panel is None:
        return {}
    grouped: dict[str, list[str]] = {}
    for record in panel.records:
        grouped.setdefault(record.operation_id, []).append(str(record.status.value))
    result: dict[str, QualificationStatus] = {}
    for operation_id, statuses in grouped.items():
        if "FAILED" in statuses:
            result[operation_id] = QualificationStatus.FAILED
        elif set(statuses) == {"BLOCKED_UPSTREAM"}:
            result[operation_id] = QualificationStatus.BLOCKED_UPSTREAM
        elif "DEGRADED" in statuses or "BLOCKED_UPSTREAM" in statuses:
            result[operation_id] = QualificationStatus.DEGRADED
        else:
            result[operation_id] = QualificationStatus.QUALIFIED_LOCAL
    return result


def _arguments(request: BaseModel, operation_id: str) -> dict[str, Any]:
    data = request.model_dump(mode="python")
    mode = data["research_mode"]
    if operation_id == "search":
        return {
            "query": data["query"],
            "filters": CorpusFilter(
                entity_ids=tuple(data["entity_ids"]),
                document_types=tuple(data["document_types"]),
                source_ids=tuple(data["source_ids"]),
                available_from=data["start_time"],
                available_to=data["end_time"],
            ).model_dump(mode="json"),
            "research_mode": mode,
            "max_results": data["max_results"],
        }
    if operation_id == "get_document":
        return {"document_id": data["document_id"], "include_content": data["include_full_text"], "research_mode": mode}
    if operation_id == "compare_versions":
        return {"left_document_id": data["document_ids"][0], "right_document_id": data["document_ids"][1], "research_mode": mode}
    if operation_id == "find_counterevidence":
        return {
            "proposition": data["proposition"],
            # The public contract carries the proposition, while the family
            # handler requires at least one bounded search query. Keep the
            # projection deterministic and derived from the agent input.
            "counter_queries": (data["proposition"],),
            "filters": CorpusFilter(entity_ids=tuple(data["entity_ids"]), document_types=tuple(data["document_types"])).model_dump(mode="json"),
            "research_mode": mode,
            "max_results": data["max_results"],
        }
    if operation_id == "build_timeline":
        return {
            "filters": CorpusFilter(
                entity_ids=tuple(data["subject_ids"]),
                available_from=data["start_time"],
                available_to=data["end_time"],
            ).model_dump(mode="json"),
            "query": " ".join(data["event_types"]) or "timeline",
            "research_mode": mode,
            "max_events": data["max_events"],
        }
    if operation_id == "inspect_provenance":
        return {"document_id": data["evidence_ids"][0], "chunk_id": None, "research_mode": mode}
    raise KeyError(operation_id)


def build_corpus_operations(
    *,
    inputs: Mapping[str, Any],
    services: Mapping[str, Any],
) -> tuple[ExecutableOperation, ...]:
    if "corpus_tool_handler_bundle" not in inputs:
        return ()
    repository = services.get("corpus_repository")
    if repository is None:
        return ()
    manifest = HandlerBundleManifest.model_validate(inputs["corpus_tool_handler_bundle"], strict=False)
    snapshot = CorpusIndexSnapshot.model_validate(inputs["corpus_index_snapshot"], strict=False)
    policy = CorpusRetrievalPolicy.model_validate(inputs["corpus_retrieval_policy"], strict=False)
    qualification = None
    if inputs.get("corpus_operation_mode_qualification") is not None:
        qualification = CorpusOperationQualificationPanel.model_validate(inputs["corpus_operation_mode_qualification"], strict=False)
    runtime_bundle = create_corpus_runtime_bundle(
        repository=repository,
        snapshot=snapshot,
        policy=policy,
        dense_retriever=services.get("corpus_dense_retriever"),
        reranker=services.get("corpus_reranker"),
        raw_resolver=services.get("raw_evidence_resolver"),
        provenance_port=services.get("provenance_query_port"),
    )
    statuses = _status_by_operation(qualification)
    operations: list[ExecutableOperation] = []
    for binding in manifest.handlers:
        operation_id = binding.operation_id

        async def handler(request: BaseModel, context: CorpusToolCallContext, *, _operation_id: str = operation_id) -> BaseModel:
            envelope = await runtime_bundle.execute(_operation_id, _arguments(request, _operation_id), context)
            return adapt_result(tool_id="research.corpus.v1", operation_id=_operation_id, request=request, envelopes=(envelope,))

        operations.append(
            operation(
                inputs=inputs,
                tool_id="research.corpus.v1",
                operation_id=operation_id,
                bundle_id=manifest.content_hash,
                qualification_status=statuses.get(operation_id, QualificationStatus.DEGRADED),
                handler=handler,
                context_factory=lambda invocation: canonical_context(invocation, CorpusToolCallContext),
                fallback_binding=binding,
            )
        )
    return tuple(operations)
