from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from .handler_support import (
    build_envelope,
    evidence_from_items,
    retrieval_outcome,
    simple_coverage,
    validate_request,
)
from .models import (
    CompareVersionsRequest,
    CorpusFilter,
    CorpusMode,
    CorpusToolCallContext,
    CorpusToolResultEnvelope,
    GetDocumentRequest,
    InspectProvenanceRequest,
    OutcomeStatus,
    SearchCorpusRequest,
)
from .ports import CorpusRepositoryPort
from .provenance import DocumentAssembler, ProvenanceAssembler, VersionComparator
from .retrieval import HybridCorpusRetriever


class DocumentCorpusHandlers:
    def __init__(
        self,
        *,
        repository: CorpusRepositoryPort,
        retriever: HybridCorpusRetriever,
        documents: DocumentAssembler,
        versions: VersionComparator,
        provenance: ProvenanceAssembler,
    ) -> None:
        self._repository = repository
        self._retriever = retriever
        self._documents = documents
        self._versions = versions
        self._provenance = provenance

    async def search(
        self,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        request = validate_request(SearchCorpusRequest, arguments)
        result = self._retriever.search(
            query=request.query,
            decision_time=context.decision_time,
            filters=request.filters,
            requested_mode=request.research_mode,
            max_results=request.max_results,
        )
        return build_envelope(
            operation_id="search",
            context=context,
            requested_mode=request.research_mode,
            executed_mode=result.executed_mode,
            downgrade_reason=result.downgrade_reason,
            outcome_status=retrieval_outcome(result),
            records=tuple(item.model_dump(mode="json") for item in result.hits),
            evidence_refs=evidence_from_items(result.hits),
            coverage=result.coverage,
            pit_proof=result.pit_proof,
            internal_subqueries=1,
            internal_work_units=1 + len(result.hits),
            warnings=result.warnings,
        )

    async def get_document(
        self,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        request = validate_request(GetDocumentRequest, arguments)
        selection = self._retriever.select_visible(
            decision_time=context.decision_time,
            filters=CorpusFilter(document_ids=(request.document_id,)),
        )
        assembly = self._documents.assemble(
            document_id=request.document_id,
            decision_time=context.decision_time,
            include_content=request.include_content,
        )
        document = assembly.document
        proof = self._retriever.pit_proof(
            decision_time=context.decision_time,
            selection=selection,
        )
        records = () if document is None else (document.model_dump(mode="json"),)
        evidence = () if document is None else evidence_from_items(selection.chunks)
        return build_envelope(
            operation_id="get_document",
            context=context,
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            downgrade_reason=None,
            outcome_status=(
                OutcomeStatus.EMPTY_VALID
                if document is None
                else OutcomeStatus.DEGRADED if assembly.warnings
                else OutcomeStatus.PASS
            ),
            records=records,
            evidence_refs=evidence,
            coverage=simple_coverage(selection, returned=len(records)),
            pit_proof=proof,
            internal_subqueries=1,
            internal_work_units=max(1, len(selection.chunks)),
            warnings=assembly.warnings,
        )

    async def compare_versions(
        self,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        request = validate_request(CompareVersionsRequest, arguments)
        selection = self._retriever.select_visible(
            decision_time=context.decision_time,
            filters=CorpusFilter(
                document_ids=(request.left_document_id, request.right_document_id)
            ),
        )
        proof = self._retriever.pit_proof(
            decision_time=context.decision_time,
            selection=selection,
        )
        left_assembly = self._documents.assemble(
            document_id=request.left_document_id,
            decision_time=context.decision_time,
            include_content=True,
        )
        right_assembly = self._documents.assemble(
            document_id=request.right_document_id,
            decision_time=context.decision_time,
            include_content=True,
        )
        left = left_assembly.document
        right = right_assembly.document
        assembly_warnings = tuple(
            sorted({*left_assembly.warnings, *right_assembly.warnings})
        )
        if left is None or right is None:
            return build_envelope(
                operation_id="compare_versions",
                context=context,
                requested_mode=request.research_mode,
                executed_mode=request.research_mode,
                downgrade_reason=None,
                outcome_status=OutcomeStatus.EMPTY_VALID,
                records=(),
                evidence_refs=(),
                coverage=simple_coverage(selection, returned=0),
                pit_proof=proof,
                internal_subqueries=2,
                internal_work_units=max(2, len(selection.chunks)),
                warnings=assembly_warnings,
            )
        comparison = self._versions.compare(
            left=left,
            right=right,
            left_metadata=self._repository.document_metadata(left.document_id),
            right_metadata=self._repository.document_metadata(right.document_id),
        )
        forensic_blocked = (
            request.research_mode is CorpusMode.FORENSIC
            and not comparison.version_graph_confirmed
        )
        return build_envelope(
            operation_id="compare_versions",
            context=context,
            requested_mode=request.research_mode,
            executed_mode=(CorpusMode.STANDARD if forensic_blocked else request.research_mode),
            downgrade_reason=("VERSION_GRAPH_UNAVAILABLE" if forensic_blocked else None),
            outcome_status=(
                OutcomeStatus.BLOCKED_UPSTREAM
                if forensic_blocked
                else OutcomeStatus.DEGRADED if assembly_warnings
                else OutcomeStatus.PASS
            ),
            records=(comparison.model_dump(mode="json"),),
            evidence_refs=evidence_from_items(selection.chunks),
            coverage=simple_coverage(selection, returned=1),
            pit_proof=proof,
            internal_subqueries=2,
            internal_work_units=max(2, len(selection.chunks)),
            warnings=tuple(
                sorted(
                    {
                        *assembly_warnings,
                        *(
                            ("P3_RT_QUAL_OPERATION_BLOCKED_UPSTREAM",)
                            if forensic_blocked
                            else ()
                        ),
                    }
                )
            ),
        )

    async def inspect_provenance(
        self,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        request = validate_request(InspectProvenanceRequest, arguments)
        document_id = request.document_id
        if request.chunk_id:
            chunk = self._repository.chunk(request.chunk_id)
            document_id = chunk.document_id if chunk else None
        selection = self._retriever.select_visible(
            decision_time=context.decision_time,
            filters=CorpusFilter(document_ids=(document_id,)) if document_id else CorpusFilter(),
        )
        result = self._provenance.build(
            document_id=request.document_id,
            chunk_id=request.chunk_id,
            decision_time=context.decision_time,
        )
        proof = self._retriever.pit_proof(
            decision_time=context.decision_time,
            selection=selection,
        )
        complete = bool(result and result.complete_to_p1)
        return build_envelope(
            operation_id="inspect_provenance",
            context=context,
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            downgrade_reason=None,
            outcome_status=(
                OutcomeStatus.EMPTY_VALID
                if result is None
                else OutcomeStatus.PASS if complete else OutcomeStatus.DEGRADED
            ),
            records=() if result is None else (result.model_dump(mode="json"),),
            evidence_refs=() if result is None else evidence_from_items(selection.chunks),
            coverage=simple_coverage(selection, returned=0 if result is None else 1),
            provenance=result,
            pit_proof=proof,
            internal_subqueries=1,
            internal_work_units=max(1, len(selection.chunks)),
            warnings=() if result is None or complete else ("P3_RT_DATA_PROVENANCE_PARTIAL",),
        )
