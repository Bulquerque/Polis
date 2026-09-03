from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from .handler_support import (
    build_envelope,
    combined_coverage,
    empty_proof,
    evidence_from_items,
    timeline_events,
    validate_request,
)
from .models import (
    BuildTimelineRequest,
    CorpusToolCallContext,
    CorpusToolResultEnvelope,
    CounterevidenceHit,
    CoverageReport,
    FindCounterevidenceRequest,
    OutcomeStatus,
)
from .ports import CorpusRepositoryPort
from .retrieval import HybridCorpusRetriever, RetrievalResult


class ReasoningCorpusHandlers:
    def __init__(
        self,
        *,
        repository: CorpusRepositoryPort,
        retriever: HybridCorpusRetriever,
        policy: object,
    ) -> None:
        self._repository = repository
        self._retriever = retriever
        self._policy = policy

    async def find_counterevidence(
        self,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        request = validate_request(FindCounterevidenceRequest, arguments)
        mode_policy = self._policy.mode(request.research_mode)
        queries = request.counter_queries[: mode_policy.max_internal_subqueries]
        warnings = ["P3_RT_BUDGET_INTERNAL_WORK_LIMIT"] if len(queries) < len(request.counter_queries) else []
        per_query = max(1, (request.max_results or mode_policy.max_results) // len(queries))
        results, counter_hits = self._run_counter_queries(
            request=request,
            context=context,
            queries=queries,
            per_query=per_query,
        )
        proof = results[0].pit_proof if results else empty_proof(context)
        coverage = combined_coverage(
            results,
            returned=len(counter_hits),
            subqueries=len(queries),
        )
        downgrade = next((item.downgrade_reason for item in results if item.downgrade_reason), None)
        for item in results:
            warnings.extend(item.warnings)
        return build_envelope(
            operation_id="find_counterevidence",
            context=context,
            requested_mode=request.research_mode,
            executed_mode=results[0].executed_mode if results else request.research_mode,
            downgrade_reason=downgrade,
            outcome_status=OutcomeStatus.PASS if counter_hits else OutcomeStatus.EMPTY_VALID,
            records=tuple(item.model_dump(mode="json") for item in counter_hits),
            evidence_refs=evidence_from_items(tuple(item.hit for item in counter_hits)),
            coverage=coverage,
            pit_proof=proof,
            internal_subqueries=len(queries),
            internal_work_units=len(queries) + len(counter_hits),
            warnings=tuple(sorted(set(warnings))),
        )

    def _run_counter_queries(
        self,
        *,
        request: FindCounterevidenceRequest,
        context: CorpusToolCallContext,
        queries: tuple[str, ...],
        per_query: int,
    ) -> tuple[list[RetrievalResult], list[CounterevidenceHit]]:
        results: list[RetrievalResult] = []
        counter_hits: list[CounterevidenceHit] = []
        seen: set[str] = set()
        for query in queries:
            result = self._retriever.search(
                query=query,
                decision_time=context.decision_time,
                filters=request.filters,
                requested_mode=request.research_mode,
                max_results=per_query,
            )
            results.append(result)
            for hit in result.hits:
                if hit.chunk_id in seen:
                    continue
                seen.add(hit.chunk_id)
                counter_hits.append(
                    CounterevidenceHit(
                        proposition=request.proposition,
                        counter_query=query,
                        hit=hit,
                    )
                )
        return results, counter_hits

    async def build_timeline(
        self,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        request = validate_request(BuildTimelineRequest, arguments)
        chunks, proof, executed_mode, downgrade, warnings = self._timeline_input(
            request=request,
            context=context,
        )
        limit = request.max_events or 100
        events = timeline_events(chunks, limit)
        coverage = CoverageReport(
            records_scanned=proof.records_scanned,
            records_visible=proof.records_visible,
            records_returned=len(events),
            unique_documents=len({event.document_id for event in events}),
            unique_sources=len({event.source_id for event in events}),
            source_families=len({event.source_id for event in events}),
            duplicate_records_removed=0,
            score=1.0 if events else 0.0,
            truncated=len(events) >= limit,
        )
        return build_envelope(
            operation_id="build_timeline",
            context=context,
            requested_mode=request.research_mode,
            executed_mode=executed_mode,
            downgrade_reason=downgrade,
            outcome_status=OutcomeStatus.PASS if events else OutcomeStatus.EMPTY_VALID,
            records=tuple(item.model_dump(mode="json") for item in events),
            evidence_refs=evidence_from_items(chunks),
            coverage=coverage,
            pit_proof=proof,
            internal_subqueries=1,
            internal_work_units=max(1, len(chunks)),
            warnings=warnings,
        )

    def _timeline_input(
        self,
        *,
        request: BuildTimelineRequest,
        context: CorpusToolCallContext,
    ) -> tuple[tuple[object, ...], object, object, str | None, tuple[str, ...]]:
        if request.query:
            retrieval = self._retriever.search(
                query=request.query,
                decision_time=context.decision_time,
                filters=request.filters,
                requested_mode=request.research_mode,
                max_results=request.max_events,
            )
            chunks = tuple(
                chunk
                for hit in retrieval.hits
                if (chunk := self._repository.chunk(hit.chunk_id)) is not None
            )
            return (
                chunks,
                retrieval.pit_proof,
                retrieval.executed_mode,
                retrieval.downgrade_reason,
                retrieval.warnings,
            )
        selection = self._retriever.select_visible(
            decision_time=context.decision_time,
            filters=request.filters,
        )
        return (
            selection.chunks,
            self._retriever.pit_proof(
                decision_time=context.decision_time,
                selection=selection,
            ),
            request.research_mode,
            None,
            (),
        )
