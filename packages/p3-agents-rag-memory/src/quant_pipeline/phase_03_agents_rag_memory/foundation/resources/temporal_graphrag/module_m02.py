from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel

from ....shared.artifact_hashing import compute_artifact_hash as _compute_artifact_hash
from .canonical import content_hash, sha256_bytes
from .errors import (
    ContractError,
    ErrorCategory,
    InvariantViolationError,
    TemporalViolationError,
    error,
)
from .graph_codec import decode_records, encode_records
from .models import (
    ArtifactStatus,
    CapabilityStatus,
    Chunk,
    EvidenceCoverage,
    EvidenceRecord,
    GraphComponent,
    GraphConfig,
    GraphEdge,
    GraphElementType,
    GraphEvidenceAssertion,
    GraphEvidenceMap,
    GraphNode,
    GraphRagArtifact,
    RagIndexArtifact,
    RelationType,
)
from .ports import ArtifactStorePort, EventSinkPort

T = TypeVar("T", bound=BaseModel)



def compute_artifact_hash(value: object) -> str:
    """Hash an artifact using this capability's canonical JSON policy."""
    return _compute_artifact_hash(value, hasher=content_hash)



@dataclass(frozen=True, slots=True)
class _LinkingOutcome:
    records: tuple[EvidenceRecord, ...]
    low_quality_count: int

class GraphEvidenceLinker:
    """Resolve every graph element to an immutable S12 evidence chain."""

    MODULE_ID = "P3.S13.M02"

    def __init__(
        self,
        *,
        artifact_store: ArtifactStorePort,
        event_sink: EventSinkPort,
    ) -> None:
        self._store = artifact_store
        self._events = event_sink

    def run(
        self,
        *,
        graph: GraphRagArtifact,
        rag_index: RagIndexArtifact,
        graph_config: GraphConfig,
    ) -> GraphEvidenceMap:
        started = perf_counter()
        dimensions = self._dimensions(graph)
        self._events.emit("module_started", dimensions)
        try:
            self._validate_envelopes(graph, rag_index, graph_config)
            nodes = self._load_component(graph.nodes, GraphNode)
            edges = self._load_component(graph.edges, GraphEdge)
            assertions = self._load_component(
                graph.evidence_assertions,
                GraphEvidenceAssertion,
            )
            chunks = self._load_chunks(rag_index)
            outcome = self._link_evidence(
                graph=graph,
                graph_config=graph_config,
                nodes=nodes,
                edges=edges,
                assertions=assertions,
                chunks=chunks,
            )
            result = self._build_map(
                graph=graph,
                rag_index=rag_index,
                graph_config=graph_config,
                outcome=outcome,
                graph_element_count=len(nodes) + len(edges),
            )
            self._emit_success(
                dimensions=dimensions,
                started=started,
                result=result,
                low_quality_count=outcome.low_quality_count,
            )
            return result
        except Exception as exc:
            self._events.emit(
                "module_failed",
                {
                    **dimensions,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def _dimensions(self, graph: GraphRagArtifact) -> dict[str, str]:
        return {
            "run_id": graph.run_id,
            "snapshot_id": graph.snapshot_id,
            "module_id": self.MODULE_ID,
            "as_of_time": graph.as_of_time.isoformat(),
        }

    def _link_evidence(
        self,
        *,
        graph: GraphRagArtifact,
        graph_config: GraphConfig,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
        assertions: tuple[GraphEvidenceAssertion, ...],
        chunks: tuple[Chunk, ...],
    ) -> _LinkingOutcome:
        elements = self._index_elements(nodes, edges)
        assertions_by_id = {item.assertion_id: item for item in assertions}
        chunks_by_id = {item.chunk_id: item for item in chunks}
        records: list[EvidenceRecord] = []
        orphan_elements: set[str] = set()
        used_assertions: set[str] = set()
        future_count = 0
        low_quality_count = 0

        for element_id, (element_type, relation_type, assertion_refs) in sorted(
            elements.items()
        ):
            if not assertion_refs:
                orphan_elements.add(element_id)
                continue
            for assertion_ref in assertion_refs:
                assertion = assertions_by_id.get(assertion_ref)
                if not self._assertion_matches_element(
                    assertion,
                    element_id=element_id,
                    element_type=element_type,
                ):
                    orphan_elements.add(element_id)
                    continue
                assert assertion is not None
                used_assertions.add(assertion.assertion_id)
                chunk = chunks_by_id.get(assertion.chunk_id)
                if chunk is None:
                    orphan_elements.add(element_id)
                    continue
                if chunk.available_at > graph.as_of_time:
                    future_count += 1
                    continue
                self._validate_span(assertion, chunk)
                if chunk.source_quality < graph_config.low_quality_threshold:
                    low_quality_count += 1
                records.append(
                    self._build_record(
                        assertion=assertion,
                        chunk=chunk,
                        relation_type=relation_type,
                    )
                )

        self._validate_linking_outcome(
            assertions_by_id=assertions_by_id,
            used_assertions=used_assertions,
            orphan_elements=orphan_elements,
            future_count=future_count,
        )
        return _LinkingOutcome(
            records=tuple(
                sorted(records, key=lambda item: item.evidence_record_id)
            ),
            low_quality_count=low_quality_count,
        )

    @staticmethod
    def _validate_linking_outcome(
        *,
        assertions_by_id: dict[str, GraphEvidenceAssertion],
        used_assertions: set[str],
        orphan_elements: set[str],
        future_count: int,
    ) -> None:
        unused_assertions = set(assertions_by_id) - used_assertions
        if unused_assertions:
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_UNREFERENCED_ASSERTION",
                    ErrorCategory.INVARIANT,
                    "evidence assertion is not referenced by any graph element",
                    context={"assertion_ids": sorted(unused_assertions)[:20]},
                )
            )
        if orphan_elements:
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_ORPHAN_GRAPH_ELEMENT",
                    ErrorCategory.INVARIANT,
                    "graph element lacks a complete evidence chain",
                    context={"element_ids": sorted(orphan_elements)[:20]},
                )
            )
        if future_count:
            raise TemporalViolationError(
                error(
                    "P3_S13_M02_TEMPORAL_VIOLATION",
                    ErrorCategory.TEMPORAL,
                    "future evidence detected",
                    context={"count": future_count},
                )
            )

    def _build_map(
        self,
        *,
        graph: GraphRagArtifact,
        rag_index: RagIndexArtifact,
        graph_config: GraphConfig,
        outcome: _LinkingOutcome,
        graph_element_count: int,
    ) -> GraphEvidenceMap:
        linked_elements = {
            record.graph_element_id for record in outcome.records
        }
        fully_linked = len(linked_elements)
        coverage_ratio = (
            1.0
            if graph_element_count == 0
            else fully_linked / graph_element_count
        )
        component = self._persist_records(outcome.records, graph_config)
        base = {
            "artifact_name": "graph_evidence_map",
            "schema_id": "graph_evidence_map.v2",
            "schema_version": "2.0.0",
            "run_id": graph.run_id,
            "snapshot_id": graph.snapshot_id,
            "as_of_time": graph.as_of_time,
            "lineage_id": graph.lineage_id,
            "status": (
                ArtifactStatus.EMPTY
                if graph_element_count == 0
                else ArtifactStatus.READY
            ),
            "graph_rag_artifact_hash": graph.content_hash,
            "rag_index_artifact_hash": rag_index.content_hash,
            "configuration_hash": content_hash(graph_config),
            "records": component,
            "coverage": EvidenceCoverage(
                graph_element_count=graph_element_count,
                fully_linked_count=fully_linked,
                partially_linked_count=0,
                orphan_count=0,
                future_evidence_count=0,
                low_quality_evidence_count=outcome.low_quality_count,
                evidence_record_count=len(outcome.records),
                coverage_ratio=coverage_ratio,
            ),
            "issues": (),
        }
        digest = compute_artifact_hash(base)
        return GraphEvidenceMap(
            artifact_id=f"graph_evidence_{digest[:24]}",
            content_hash=digest,
            **base,
        )

    def _emit_success(
        self,
        *,
        dimensions: dict[str, str],
        started: float,
        result: GraphEvidenceMap,
        low_quality_count: int,
    ) -> None:
        self._events.emit(
            "module_succeeded",
            {
                **dimensions,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "output_record_count": result.coverage.evidence_record_count,
                "warning_count": low_quality_count,
                "error_count": 0,
            },
        )

    def _validate_envelopes(
        self,
        graph: GraphRagArtifact,
        rag_index: RagIndexArtifact,
        config: GraphConfig,
    ) -> None:
        if compute_artifact_hash(graph) != graph.content_hash:
            raise ContractError(
                error(
                    "P3_S13_M02_GRAPH_HASH_INVALID",
                    ErrorCategory.CONTRACT,
                    "graph artifact envelope hash is invalid",
                )
            )
        if compute_artifact_hash(rag_index) != rag_index.content_hash:
            raise ContractError(
                error(
                    "P3_S13_M02_RAG_HASH_INVALID",
                    ErrorCategory.CONTRACT,
                    "RAG artifact envelope hash is invalid",
                )
            )
        if graph.rag_index_artifact_hash != rag_index.content_hash:
            raise ContractError(
                error(
                    "P3_S13_M02_RAG_LINEAGE_MISMATCH",
                    ErrorCategory.CONTRACT,
                    "graph was built from a different RAG artifact",
                )
            )
        if graph.configuration_hash != content_hash(config):
            raise ContractError(
                error(
                    "P3_S13_M02_CONFIG_HASH_MISMATCH",
                    ErrorCategory.CONTRACT,
                    "graph config differs from M01",
                )
            )

    def _load_component(
        self,
        component: GraphComponent,
        model: type[T],
    ) -> tuple[T, ...]:
        content = self._store.get_bytes(component.artifact_ref)
        if sha256_bytes(content) != component.artifact_ref.content_hash:
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_COMPONENT_HASH_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "graph component hash mismatch",
                    context={"component": component.name},
                )
            )
        records = decode_records(
            content,
            model,
            component.artifact_ref.media_type,
        )
        if len(records) != component.record_count:
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_COMPONENT_CARDINALITY_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "graph component cardinality mismatch",
                    context={"component": component.name},
                )
            )
        return records

    def _load_chunks(self, rag_index: RagIndexArtifact) -> tuple[Chunk, ...]:
        reference = rag_index.chunk_catalog.artifact_ref
        if reference is None:
            if rag_index.coverage.chunk_count == 0:
                return ()
            raise ContractError(
                error(
                    "P3_S13_M02_CHUNK_CATALOG_MISSING",
                    ErrorCategory.CONTRACT,
                    "RAG reports chunks without a chunk catalog",
                )
            )
        content = self._store.get_bytes(reference)
        if sha256_bytes(content) != reference.content_hash:
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_CHUNK_CATALOG_HASH_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "chunk catalog hash mismatch",
                )
            )
        chunks = decode_records(content, Chunk, reference.media_type)
        if len(chunks) != rag_index.coverage.chunk_count:
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_CHUNK_CARDINALITY_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "chunk catalog cardinality mismatch",
                )
            )
        return chunks

    @staticmethod
    def _index_elements(
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
    ) -> dict[str, tuple[GraphElementType, RelationType | None, tuple[str, ...]]]:
        elements: dict[
            str,
            tuple[GraphElementType, RelationType | None, tuple[str, ...]],
        ] = {}
        for node in nodes:
            elements[node.node_id] = (
                GraphElementType.NODE,
                None,
                node.evidence_refs,
            )
        for edge in edges:
            elements[edge.edge_id] = (
                GraphElementType.EDGE,
                edge.relation_type,
                edge.evidence_refs,
            )
        if len(elements) != len(nodes) + len(edges):
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_DUPLICATE_GRAPH_ELEMENT_ID",
                    ErrorCategory.INVARIANT,
                    "node and edge IDs must be globally unique",
                )
            )
        return elements

    @staticmethod
    def _assertion_matches_element(
        assertion: GraphEvidenceAssertion | None,
        *,
        element_id: str,
        element_type: GraphElementType,
    ) -> bool:
        return (
            assertion is not None
            and assertion.graph_element_id == element_id
            and assertion.graph_element_type == element_type
        )

    @staticmethod
    def _validate_span(
        assertion: GraphEvidenceAssertion,
        chunk: Chunk,
    ) -> None:
        word_count = len(chunk.content.split())
        if (
            assertion.span_end_word is not None
            and assertion.span_end_word > word_count
        ):
            raise InvariantViolationError(
                error(
                    "P3_S13_M02_SPAN_OUT_OF_RANGE",
                    ErrorCategory.INVARIANT,
                    "evidence span exceeds chunk length",
                    context={"assertion_id": assertion.assertion_id},
                )
            )

    @staticmethod
    def _build_record(
        *,
        assertion: GraphEvidenceAssertion,
        chunk: Chunk,
        relation_type: RelationType | None,
    ) -> EvidenceRecord:
        record_id = f"evidence_{content_hash({
            'assertion': assertion.assertion_id,
            'chunk': chunk.chunk_id,
        })[:24]}"
        return EvidenceRecord(
            evidence_record_id=record_id,
            assertion_id=assertion.assertion_id,
            graph_element_id=assertion.graph_element_id,
            graph_element_type=assertion.graph_element_type,
            relation_type=relation_type,
            evidence_role=assertion.evidence_role,
            evidence_origin=assertion.evidence_origin,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            source_id=chunk.source_id,
            event_time=chunk.event_time,
            available_at=chunk.available_at,
            source_quality=chunk.source_quality,
            chunk_content_hash=chunk.content_hash,
            span_start_word=assertion.span_start_word,
            span_end_word=assertion.span_end_word,
            confidence=assertion.confidence,
            lineage_refs=tuple(
                sorted(set(chunk.lineage_refs + assertion.provenance))
            ),
        )

    def _persist_records(
        self,
        records: tuple[EvidenceRecord, ...],
        graph_config: GraphConfig,
    ) -> GraphComponent:
        content, media_type, suffix, version = encode_records(
            records,
            graph_config.record_format,
        )
        reference = self._store.put_bytes(
            artifact_type="graph_evidence_records",
            content=content,
            media_type=media_type,
            suffix=suffix,
            record_count=len(records),
            format_version=version,
        )
        return GraphComponent(
            name="graph_evidence_records",
            status=(
                CapabilityStatus.READY
                if records
                else CapabilityStatus.NOT_APPLICABLE
            ),
            artifact_ref=reference,
            adapter_id=(
                f"portable_{graph_config.record_format.value.casefold()}"
            ),
            adapter_version="1.0.0",
            record_count=len(records),
            format_version=version,
            qualification_status="IMPLEMENTED_QUALIFIED_INTERNAL",
        )
