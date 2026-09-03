from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.models import Chunk

from .canonical import content_hash, min_max_normalize, reciprocal_rank_fusion, tokenize
from .errors import CorpusToolError, ErrorCategory, error
from .models import (
    CorpusFilter,
    CorpusIndexSnapshot,
    CorpusMode,
    CorpusRetrievalPolicy,
    ModePolicy,
    CoverageReport,
    PitQueryProof,
    SearchHit,
)
from .ports import CorpusRepositoryPort, DenseRetrievalPort, RerankerPort


@dataclass(frozen=True, slots=True)
class RetrievalDiagnostics:
    records_scanned: int
    records_visible: int
    records_rejected_future: int
    records_rejected_filter: int
    duplicate_records_removed: int
    missing_dimensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    hits: tuple[SearchHit, ...]
    coverage: CoverageReport
    pit_proof: PitQueryProof
    executed_mode: CorpusMode
    downgrade_reason: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VisibleSelection:
    chunks: tuple[Chunk, ...]
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True, slots=True)
class CandidateScores:
    ranked_chunks: tuple[Chunk, ...]
    lexical: dict[str, float]
    semantic: dict[str, float]
    fused: dict[str, float]
    rerank: dict[str, float]


class HybridCorpusRetriever:
    def __init__(
        self,
        *,
        repository: CorpusRepositoryPort,
        snapshot: CorpusIndexSnapshot,
        policy: CorpusRetrievalPolicy,
        dense_retriever: DenseRetrievalPort | None = None,
        reranker: RerankerPort | None = None,
    ) -> None:
        self._repository = repository
        self._snapshot = snapshot
        self._policy = policy
        self._dense = dense_retriever
        self._reranker = reranker

    def select_visible(
        self,
        *,
        decision_time: datetime,
        filters: CorpusFilter,
    ) -> VisibleSelection:
        self._validate_decision_time(decision_time)
        missing = self._missing_filter_dimensions(filters)
        if missing:
            raise CorpusToolError(
                error(
                    "P3_RT_MODE_PREREQUISITE_MISSING",
                    ErrorCategory.DATA,
                    "requested corpus filters are unavailable in the frozen index",
                    context={"missing_dimensions": missing},
                )
            )
        scanned = len(self._repository.chunks)
        future_rejected = 0
        filter_rejected = 0
        visible: list[Chunk] = []
        for chunk in self._repository.chunks:
            if chunk.available_at > decision_time:
                future_rejected += 1
                continue
            if not self._matches(chunk, filters):
                filter_rejected += 1
                continue
            visible.append(chunk)
        deduplicated, duplicates = self._deduplicate(visible)
        diagnostics = RetrievalDiagnostics(
            records_scanned=scanned,
            records_visible=len(deduplicated),
            records_rejected_future=future_rejected,
            records_rejected_filter=filter_rejected,
            duplicate_records_removed=duplicates,
            missing_dimensions=(),
        )
        return VisibleSelection(chunks=deduplicated, diagnostics=diagnostics)

    def pit_proof(
        self,
        *,
        decision_time: datetime,
        selection: VisibleSelection,
    ) -> PitQueryProof:
        return self._pit_proof(decision_time, selection)

    def search(
        self,
        *,
        query: str,
        decision_time: datetime,
        filters: CorpusFilter,
        requested_mode: CorpusMode,
        max_results: int | None,
    ) -> RetrievalResult:
        selection = self.select_visible(decision_time=decision_time, filters=filters)
        mode, downgrade, warnings = self._resolve_mode(requested_mode)
        mode_policy = self._policy.mode(mode)
        limit = min(max_results or mode_policy.max_results, mode_policy.max_results)
        scores = self._score_candidates(
            query=query,
            chunks=selection.chunks,
            mode_policy=mode_policy,
            limit=limit,
        )
        hits = self._build_hits(scores, limit=limit)
        return RetrievalResult(
            hits=hits,
            coverage=self._coverage(hits, selection.diagnostics, mode_policy, limit),
            pit_proof=self._pit_proof(decision_time, selection),
            executed_mode=mode,
            downgrade_reason=downgrade,
            warnings=warnings,
        )

    def _score_candidates(
        self,
        *,
        query: str,
        chunks: tuple[Chunk, ...],
        mode_policy: ModePolicy,
        limit: int,
    ) -> CandidateScores:
        lexical = self._bm25(query, chunks)
        semantic = self._semantic_scores(query, chunks, mode_policy, limit)
        rankings = [self._rank_ids(lexical)]
        if semantic:
            rankings.append(self._rank_ids(semantic))
        fused = reciprocal_rank_fusion(rankings, constant=self._policy.rrf_constant)
        ordered = self._ordered_candidates(chunks, fused, lexical, semantic)
        ranked, rerank = self._rerank_candidates(
            query=query,
            chunks=ordered,
            fused=fused,
            mode_policy=mode_policy,
            limit=limit,
        )
        return CandidateScores(
            ranked_chunks=ranked,
            lexical=lexical,
            semantic=semantic,
            fused=fused,
            rerank=rerank,
        )

    def _semantic_scores(
        self,
        query: str,
        chunks: tuple[Chunk, ...],
        mode_policy: ModePolicy,
        limit: int,
    ) -> dict[str, float]:
        if not mode_policy.allow_semantic or self._dense is None or not chunks:
            return {}
        scores = dict(
            self._dense.search(
                query,
                candidate_chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
                top_k=max(limit * 4, limit),
            )
        )
        self._validate_semantic_scores(scores, chunks)
        return scores

    def _rerank_candidates(
        self,
        *,
        query: str,
        chunks: tuple[Chunk, ...],
        fused: dict[str, float],
        mode_policy: ModePolicy,
        limit: int,
    ) -> tuple[tuple[Chunk, ...], dict[str, float]]:
        if not mode_policy.allow_reranker or self._reranker is None or not chunks:
            return chunks, {}
        candidates = chunks[: max(limit * 3, limit)]
        scores = self._reranker.rank(query, tuple(chunk.content for chunk in candidates))
        if len(scores) != len(candidates):
            raise CorpusToolError(
                error(
                    "P3_RT_PROVIDER_RERANKER_CARDINALITY_MISMATCH",
                    ErrorCategory.PROVIDER,
                    "reranker did not return one score per passage",
                )
            )
        rerank = {
            chunk.chunk_id: float(score)
            for chunk, score in zip(candidates, scores, strict=True)
        }
        ordered = tuple(
            sorted(
                chunks,
                key=lambda item: (
                    -rerank.get(item.chunk_id, float("-inf")),
                    -fused.get(item.chunk_id, 0.0),
                    item.chunk_id,
                ),
            )
        )
        return ordered, rerank

    @staticmethod
    def _build_hits(scores: CandidateScores, *, limit: int) -> tuple[SearchHit, ...]:
        lexical = min_max_normalize(scores.lexical)
        semantic = min_max_normalize(scores.semantic)
        fused = min_max_normalize(scores.fused)
        return tuple(
            SearchHit(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                source_id=chunk.source_id,
                sequence_number=chunk.sequence_number,
                content=chunk.content,
                content_hash=chunk.content_hash,
                available_at=chunk.available_at,
                event_time=chunk.event_time,
                effective_time=chunk.effective_time,
                source_quality=chunk.source_quality,
                entities=chunk.entities,
                underlyings=chunk.underlyings,
                lineage_refs=chunk.lineage_refs,
                lexical_score=lexical.get(chunk.chunk_id, 0.0),
                semantic_score=semantic.get(chunk.chunk_id) if chunk.chunk_id in scores.semantic else None,
                fused_score=fused.get(chunk.chunk_id, 0.0),
                rerank_score=scores.rerank.get(chunk.chunk_id),
                rank=rank,
            )
            for rank, chunk in enumerate(scores.ranked_chunks[:limit], start=1)
        )

    def _validate_decision_time(self, decision_time: datetime) -> None:
        if decision_time.tzinfo is None or decision_time.utcoffset() is None:
            raise CorpusToolError(
                error(
                    "P3_RT_CONTRACT_DECISION_TIME_INVALID",
                    ErrorCategory.CONTRACT,
                    "decision_time must be timezone-aware",
                )
            )
        if decision_time > self._snapshot.as_of_time:
            raise CorpusToolError(
                error(
                    "P3_RT_PIT_DECISION_AFTER_SNAPSHOT",
                    ErrorCategory.TEMPORAL,
                    "tool decision_time cannot be after the frozen corpus snapshot",
                    context={
                        "decision_time": decision_time.isoformat(),
                        "snapshot_as_of": self._snapshot.as_of_time.isoformat(),
                    },
                )
            )

    def _missing_filter_dimensions(self, filters: CorpusFilter) -> tuple[str, ...]:
        missing: list[str] = []
        if filters.document_types and not self._repository.supports_metadata_field("document_type"):
            missing.append("document_type")
        return tuple(missing)

    def _matches(self, chunk: Chunk, filters: CorpusFilter) -> bool:
        if filters.source_ids and chunk.source_id not in filters.source_ids:
            return False
        if filters.document_ids and chunk.document_id not in filters.document_ids:
            return False
        if filters.entity_ids and not set(filters.entity_ids).intersection(chunk.entities):
            return False
        if filters.underlying_ids and not set(filters.underlying_ids).intersection(chunk.underlyings):
            return False
        if filters.available_from and chunk.available_at < filters.available_from:
            return False
        if filters.available_to and chunk.available_at > filters.available_to:
            return False
        if filters.document_types:
            metadata = self._repository.document_metadata(chunk.document_id)
            if str(metadata.get("document_type", "")) not in filters.document_types:
                return False
        return True

    @staticmethod
    def _deduplicate(chunks: Iterable[Chunk]) -> tuple[tuple[Chunk, ...], int]:
        best: dict[str, Chunk] = {}
        duplicates = 0
        for chunk in sorted(
            chunks,
            key=lambda item: (-item.source_quality, item.document_id, item.chunk_id),
        ):
            if chunk.content_hash in best:
                duplicates += 1
                continue
            best[chunk.content_hash] = chunk
        return tuple(sorted(best.values(), key=lambda item: item.chunk_id)), duplicates

    def _resolve_mode(
        self,
        requested: CorpusMode,
    ) -> tuple[CorpusMode, str | None, tuple[str, ...]]:
        policy = self._policy.mode(requested)
        warnings: list[str] = []
        if policy.require_semantic and self._dense is None:
            for target in policy.downgrade_targets:
                candidate = self._policy.mode(target)
                if not candidate.require_semantic:
                    warnings.append("P3_RT_MODE_DOWNGRADED")
                    return target, "SEMANTIC_RETRIEVAL_UNAVAILABLE", tuple(warnings)
            raise CorpusToolError(
                error(
                    "P3_RT_MODE_PREREQUISITE_MISSING",
                    ErrorCategory.PROVIDER,
                    "requested mode requires semantic retrieval",
                )
            )
        if policy.allow_semantic and self._dense is None:
            warnings.append("P3_RT_PROVIDER_SEMANTIC_RETRIEVAL_UNAVAILABLE")
        if policy.allow_reranker and self._reranker is None:
            warnings.append("P3_RT_PROVIDER_RERANKER_UNAVAILABLE")
        return requested, None, tuple(warnings)

    def _bm25(self, query: str, chunks: tuple[Chunk, ...]) -> dict[str, float]:
        query_tokens = tokenize(query)
        if not query_tokens or not chunks:
            return {}
        tokenized = {chunk.chunk_id: tokenize(chunk.content) for chunk in chunks}
        lengths = {chunk_id: len(tokens) for chunk_id, tokens in tokenized.items()}
        average_length = sum(lengths.values()) / max(len(lengths), 1)
        document_frequency: Counter[str] = Counter()
        for tokens in tokenized.values():
            document_frequency.update(set(tokens))
        total = len(chunks)
        scores: dict[str, float] = {}
        for chunk in chunks:
            frequencies = Counter(tokenized[chunk.chunk_id])
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if frequency == 0:
                    continue
                df = document_frequency[token]
                idf = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
                denominator = frequency + self._policy.bm25_k1 * (
                    1.0
                    - self._policy.bm25_b
                    + self._policy.bm25_b * lengths[chunk.chunk_id] / max(average_length, 1.0)
                )
                score += idf * frequency * (self._policy.bm25_k1 + 1.0) / denominator
            if score > 0:
                scores[chunk.chunk_id] = score
        return scores

    @staticmethod
    def _rank_ids(scores: dict[str, float]) -> tuple[str, ...]:
        return tuple(sorted(scores, key=lambda item: (-scores[item], item)))

    @staticmethod
    def _validate_semantic_scores(scores: dict[str, float], chunks: tuple[Chunk, ...]) -> None:
        valid_ids = {chunk.chunk_id for chunk in chunks}
        unknown = sorted(set(scores) - valid_ids)
        if unknown:
            raise CorpusToolError(
                error(
                    "P3_RT_PROVIDER_SEMANTIC_RESULT_INVALID",
                    ErrorCategory.PROVIDER,
                    "semantic retriever returned unknown chunk IDs",
                    context={"unknown": unknown[:10]},
                )
            )
        if any(value < 0 or not math.isfinite(value) for value in scores.values()):
            raise CorpusToolError(
                error(
                    "P3_RT_PROVIDER_SEMANTIC_RESULT_INVALID",
                    ErrorCategory.PROVIDER,
                    "semantic retriever returned invalid scores",
                )
            )

    @staticmethod
    def _ordered_candidates(
        chunks: tuple[Chunk, ...],
        fused: dict[str, float],
        lexical: dict[str, float],
        semantic: dict[str, float],
    ) -> tuple[Chunk, ...]:
        candidate_ids = set(fused) | set(lexical) | set(semantic)
        return tuple(
            sorted(
                (chunk for chunk in chunks if chunk.chunk_id in candidate_ids),
                key=lambda item: (
                    -fused.get(item.chunk_id, 0.0),
                    -lexical.get(item.chunk_id, 0.0),
                    -semantic.get(item.chunk_id, 0.0),
                    item.chunk_id,
                ),
            )
        )

    def _coverage(
        self,
        hits: tuple[SearchHit, ...],
        diagnostics: RetrievalDiagnostics,
        mode_policy: object,
        requested_limit: int,
    ) -> CoverageReport:
        minimum_sources = int(getattr(mode_policy, "minimum_source_families"))
        source_ids = {hit.source_id for hit in hits}
        source_families = {
            str(self._repository.document_metadata(hit.document_id).get("source_family", hit.source_id))
            for hit in hits
        }
        result_factor = min(1.0, len(hits) / max(requested_limit, 1))
        source_factor = min(1.0, len(source_families) / max(minimum_sources, 1))
        score = max(0.0, min(1.0, 0.7 * result_factor + 0.3 * source_factor))
        missing: list[str] = []
        if len(source_families) < minimum_sources:
            missing.append("SOURCE_FAMILY_DIVERSITY")
        return CoverageReport(
            records_scanned=diagnostics.records_scanned,
            records_visible=diagnostics.records_visible,
            records_returned=len(hits),
            unique_documents=len({hit.document_id for hit in hits}),
            unique_sources=len(source_ids),
            source_families=len(source_families),
            duplicate_records_removed=diagnostics.duplicate_records_removed,
            score=score,
            missing_dimensions=tuple(missing),
            truncated=len(hits) >= requested_limit and diagnostics.records_visible > len(hits),
        )

    def _pit_proof(
        self,
        decision_time: datetime,
        selection: VisibleSelection,
    ) -> PitQueryProof:
        available = [chunk.available_at for chunk in selection.chunks]
        base = {
            "decision_time": decision_time,
            "records_scanned": selection.diagnostics.records_scanned,
            "records_visible": selection.diagnostics.records_visible,
            "records_rejected_future": selection.diagnostics.records_rejected_future,
            "records_rejected_filter": selection.diagnostics.records_rejected_filter,
            "earliest_available_at": min(available) if available else None,
            "latest_available_at": max(available) if available else None,
            "snapshot_id": self._snapshot.snapshot_id,
            "input_hashes": (
                self._snapshot.content_hash,
                self._snapshot.chunk_catalog.content_hash,
                self._snapshot.keyword_index.content_hash,
            ),
        }
        return PitQueryProof(proof_hash=content_hash(base), **base)
