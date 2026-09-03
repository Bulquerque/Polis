from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter

from pydantic import BaseModel

from ....shared.artifact_hashing import compute_artifact_hash as _compute_artifact_hash
from .canonical import content_hash, sha256_bytes
from .errors import (
    ContractError,
    ErrorCategory,
    InvariantViolationError,
    ProviderFailureError,
    TemporalViolationError,
    error,
)
from .graph_building import apply_provider_proposals, build_structured_graph
from .graph_codec import decode_records, encode_records
from .models import (
    ArtifactStatus,
    CapabilityStatus,
    Chunk,
    GraphComponent,
    GraphConfig,
    GraphCoverage,
    GraphRagArtifact,
    PitValidatedContext,
    ProviderRegistry,
    ProviderStatus,
    PublicationResult,
    PublicationStatus,
    RagIndexArtifact,
    RunSnapshot,
)
from .ports import (
    ArtifactStorePort,
    EventSinkPort,
    GraphProposalProviderPort,
    GraphPublisherPort,
)



def compute_artifact_hash(value: object) -> str:
    """Hash an artifact using this capability's canonical JSON policy."""
    return _compute_artifact_hash(value, hasher=content_hash)

class TemporalGraphBuilder:
    """Build a portable, evidence-bound, point-in-time graph."""

    MODULE_ID = "P3.S13.M01"

    def __init__(
        self,
        *,
        artifact_store: ArtifactStorePort,
        proposal_provider: GraphProposalProviderPort,
        graph_publisher: GraphPublisherPort,
        event_sink: EventSinkPort,
    ) -> None:
        self._store = artifact_store
        self._proposal_provider = proposal_provider
        self._publisher = graph_publisher
        self._events = event_sink

    async def run(
        self,
        *,
        rag_index: RagIndexArtifact,
        context: PitValidatedContext,
        snapshot: RunSnapshot,
        graph_config: GraphConfig,
        provider_registry: ProviderRegistry,
    ) -> GraphRagArtifact:
        started = perf_counter()
        dimensions = {
            "run_id": snapshot.run_id,
            "snapshot_id": snapshot.snapshot_id,
            "module_id": self.MODULE_ID,
            "as_of_time": snapshot.as_of_time.isoformat(),
        }
        self._events.emit("module_started", dimensions)
        try:
            self._validate_inputs(rag_index, context, snapshot, graph_config)
            chunks = self._load_chunks(rag_index)
            self._validate_chunk_lineage(chunks, context, snapshot)

            graph = build_structured_graph(chunks, graph_config.ontology_version)
            issues: list[str] = []
            rejected = 0
            provider_fingerprints: dict[str, str] = {}

            if graph_config.provider_proposals.enabled:
                rejected += await self._apply_optional_proposals(
                    graph=graph,
                    chunks=chunks,
                    snapshot=snapshot,
                    graph_config=graph_config,
                    provider_registry=provider_registry,
                    provider_fingerprints=provider_fingerprints,
                    issues=issues,
                )

            nodes = tuple(sorted(graph.nodes.values(), key=lambda item: item.node_id))
            edges = tuple(sorted(graph.edges.values(), key=lambda item: item.edge_id))
            assertions = tuple(
                sorted(graph.assertions.values(), key=lambda item: item.assertion_id)
            )
            self._validate_graph_edges(edges, graph.nodes, snapshot)

            node_component = self._persist_component("graph_nodes", nodes, graph_config)
            edge_component = self._persist_component("graph_edges", edges, graph_config)
            assertion_component = self._persist_component(
                "graph_evidence_assertions",
                assertions,
                graph_config,
            )
            publication = await self._publish_if_requested(
                nodes=nodes,
                edges=edges,
                graph_config=graph_config,
                issues=issues,
            )

            status = ArtifactStatus.EMPTY if not nodes else (
                ArtifactStatus.DEGRADED if issues else ArtifactStatus.READY
            )
            base = {
                "artifact_name": "graph_rag_artifact",
                "schema_id": "graph_rag_artifact.v2",
                "schema_version": "2.0.0",
                "run_id": snapshot.run_id,
                "snapshot_id": snapshot.snapshot_id,
                "as_of_time": snapshot.as_of_time,
                "lineage_id": context.lineage_id,
                "status": status,
                "reason_code": "EMPTY_CORPUS" if not nodes else None,
                "grain": ("graph_element_id",),
                "ontology_version": graph_config.ontology_version,
                "entity_resolution_version": graph_config.entity_resolution_version,
                "relation_rules_version": graph_config.relation_rules_version,
                "rag_index_artifact_hash": rag_index.content_hash,
                "configuration_hash": content_hash(graph_config),
                "nodes": node_component,
                "edges": edge_component,
                "evidence_assertions": assertion_component,
                "coverage": self._coverage(
                    nodes,
                    edges,
                    assertions,
                    rejected_proposal_count=rejected,
                ),
                "publication": publication,
                "provider_fingerprints": provider_fingerprints,
                "issues": tuple(sorted(set(issues))),
            }
            digest = compute_artifact_hash(base)
            artifact = GraphRagArtifact(
                artifact_id=f"graph_{digest[:24]}",
                content_hash=digest,
                **base,
            )
            self._events.emit(
                "module_succeeded",
                {
                    **dimensions,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "output_record_count": len(nodes) + len(edges),
                    "warning_count": len(issues),
                    "error_count": 0,
                },
            )
            return artifact
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

    async def _apply_optional_proposals(
        self,
        *,
        graph: object,
        chunks: Sequence[Chunk],
        snapshot: RunSnapshot,
        graph_config: GraphConfig,
        provider_registry: ProviderRegistry,
        provider_fingerprints: dict[str, str],
        issues: list[str],
    ) -> int:
        descriptor = await self._proposal_provider.describe()
        provider_fingerprints[descriptor.provider_id] = descriptor.fingerprint
        provider_id = graph_config.provider_proposals.provider_id or ""
        declared = provider_registry.find(provider_id, "GraphProposalProvider")
        snapshot_fingerprint = snapshot.provider_fingerprints.get(provider_id)
        provider_usable = (
            declared is not None
            and declared.status
            in {
                ProviderStatus.CONNECTED_QUALIFIED,
                ProviderStatus.CONNECTED_UNQUALIFIED,
            }
            and descriptor.provider_id == declared.provider_id
            and descriptor.fingerprint == declared.fingerprint
            and snapshot_fingerprint == descriptor.fingerprint
            and descriptor.supports_json_schema
        )
        if not provider_usable:
            if graph_config.provider_proposals.required:
                raise ProviderFailureError(
                    error(
                        "P3_S13_M01_PROVIDER_UNAVAILABLE",
                        ErrorCategory.PROVIDER,
                        "required graph proposal provider is not usable or pinned",
                    )
                )
            issues.append("GRAPH_PROPOSAL_PROVIDER_UNAVAILABLE")
            return 0

        if declared.status == ProviderStatus.CONNECTED_UNQUALIFIED:
            issues.append("GRAPH_PROPOSAL_PROVIDER_UNQUALIFIED")

        chunks_by_id = {item.chunk_id: item for item in chunks}
        rejected = 0
        try:
            for batch in _batched(
                chunks,
                graph_config.provider_proposals.max_chunks_per_request,
            ):
                payload = tuple(
                    {
                        "chunk_id": item.chunk_id,
                        "content": item.content,
                        "entities": list(item.entities),
                        "underlyings": list(item.underlyings),
                        "available_at": item.available_at.isoformat(),
                    }
                    for item in batch
                )
                proposals = await self._proposal_provider.propose(payload)
                proposal_count = len(proposals.nodes) + len(proposals.edges)
                maximum = (
                    len(batch)
                    * graph_config.provider_proposals.max_proposals_per_chunk
                )
                if proposal_count > maximum:
                    raise ProviderFailureError(
                        error(
                            "P3_S13_M01_PROVIDER_PROPOSAL_LIMIT_EXCEEDED",
                            ErrorCategory.PROVIDER,
                            "provider returned more proposals than permitted",
                            context={"received": proposal_count, "maximum": maximum},
                        )
                    )
                rejected += apply_provider_proposals(
                    graph,  # type: ignore[arg-type]
                    proposals,
                    chunks_by_id,
                    min_confidence=graph_config.provider_proposals.min_confidence,
                )
        except ProviderFailureError:
            if graph_config.provider_proposals.required:
                raise
            issues.append("GRAPH_PROPOSAL_PROVIDER_FAILED")
        return rejected

    async def _publish_if_requested(
        self,
        *,
        nodes: Sequence[object],
        edges: Sequence[object],
        graph_config: GraphConfig,
        issues: list[str],
    ) -> PublicationResult:
        publication = PublicationResult(status=PublicationStatus.NOT_REQUESTED)
        if not graph_config.publication.enabled:
            return publication
        try:
            publication = await self._publisher.publish(
                nodes=nodes,  # type: ignore[arg-type]
                edges=edges,  # type: ignore[arg-type]
                database=graph_config.publication.database,
            )
            if publication.adapter_id != graph_config.publication.adapter_id:
                raise ProviderFailureError(
                    error(
                        "P3_S13_M01_PUBLICATION_ADAPTER_MISMATCH",
                        ErrorCategory.PROVIDER,
                        "graph publisher differs from the configured adapter",
                    )
                )
            return publication
        except Exception as exc:
            if graph_config.publication.required:
                raise ProviderFailureError(
                    error(
                        "P3_S13_M01_GRAPH_PUBLICATION_FAILED",
                        ErrorCategory.PROVIDER,
                        "required graph publication failed",
                    )
                ) from exc
            issues.append("OPTIONAL_GRAPH_PUBLICATION_FAILED")
            return PublicationResult(
                status=PublicationStatus.FAILED_OPTIONAL,
                adapter_id=graph_config.publication.adapter_id,
                database=graph_config.publication.database,
                reason_code="OPTIONAL_PUBLICATION_FAILED",
            )

    def _validate_inputs(
        self,
        rag_index: RagIndexArtifact,
        context: PitValidatedContext,
        snapshot: RunSnapshot,
        graph_config: GraphConfig,
    ) -> None:
        if compute_artifact_hash(rag_index) != rag_index.content_hash:
            raise ContractError(
                error(
                    "P3_S13_M01_RAG_HASH_INVALID",
                    ErrorCategory.CONTRACT,
                    "rag_index_artifact envelope hash is invalid",
                )
            )
        if (
            rag_index.run_id != snapshot.run_id
            or rag_index.snapshot_id != snapshot.snapshot_id
        ):
            raise ContractError(
                error(
                    "P3_S13_M01_SNAPSHOT_MISMATCH",
                    ErrorCategory.CONTRACT,
                    "RAG and run snapshot identities differ",
                )
            )
        if rag_index.as_of_time != snapshot.as_of_time:
            raise ContractError(
                error(
                    "P3_S13_M01_AS_OF_MISMATCH",
                    ErrorCategory.CONTRACT,
                    "RAG and run snapshot as_of differ",
                )
            )
        expected = snapshot.config_hashes.get("graph_config")
        resolved = content_hash(graph_config)
        if expected is None or expected != resolved:
            raise ContractError(
                error(
                    "P3_S13_M01_GRAPH_CONFIG_NOT_PINNED",
                    ErrorCategory.CONTRACT,
                    "graph_config hash is not pinned by the run snapshot",
                    context={"expected": expected, "actual": resolved},
                )
            )
        for record in context.records:
            if record.available_at > snapshot.as_of_time:
                raise TemporalViolationError(
                    error(
                        "P3_S13_M01_TEMPORAL_VIOLATION",
                        ErrorCategory.TEMPORAL,
                        "future context record cannot enter graph build",
                        context={"document_id": record.document_id},
                    )
                )

    def _validate_chunk_lineage(
        self,
        chunks: Sequence[Chunk],
        context: PitValidatedContext,
        snapshot: RunSnapshot,
    ) -> None:
        documents = {record.document_id: record for record in context.records}
        if len(documents) != len(context.records):
            raise ContractError(
                error(
                    "P3_S13_M01_DUPLICATE_CONTEXT_DOCUMENT_ID",
                    ErrorCategory.CONTRACT,
                    "PIT context contains duplicate document IDs",
                )
            )
        seen: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in seen:
                raise ContractError(
                    error(
                        "P3_S13_M01_DUPLICATE_CHUNK_ID",
                        ErrorCategory.CONTRACT,
                        "chunk catalog contains duplicate chunk IDs",
                        context={"chunk_id": chunk.chunk_id},
                    )
                )
            seen.add(chunk.chunk_id)
            record = documents.get(chunk.document_id)
            if record is None or record.source_id != chunk.source_id:
                raise ContractError(
                    error(
                        "P3_S13_M01_CHUNK_CONTEXT_LINEAGE_MISMATCH",
                        ErrorCategory.CONTRACT,
                        "chunk does not resolve to its PIT document and source",
                        context={"chunk_id": chunk.chunk_id},
                    )
                )
            if record.available_at != chunk.available_at:
                raise ContractError(
                    error(
                        "P3_S13_M01_CHUNK_AVAILABLE_AT_MISMATCH",
                        ErrorCategory.CONTRACT,
                        "chunk availability differs from its PIT document",
                        context={"chunk_id": chunk.chunk_id},
                    )
                )
            if chunk.available_at > snapshot.as_of_time:
                raise TemporalViolationError(
                    error(
                        "P3_S13_M01_TEMPORAL_VIOLATION",
                        ErrorCategory.TEMPORAL,
                        "future chunk cannot enter the temporal graph",
                        context={"chunk_id": chunk.chunk_id},
                    )
                )
            if content_hash({"content": chunk.content}) != chunk.content_hash:
                raise ContractError(
                    error(
                        "P3_S13_M01_CHUNK_CONTENT_HASH_MISMATCH",
                        ErrorCategory.CONTRACT,
                        "chunk content hash is not recomputable",
                        context={"chunk_id": chunk.chunk_id},
                    )
                )
            if not chunk.lineage_refs:
                raise ContractError(
                    error(
                        "P3_S13_M01_CHUNK_LINEAGE_MISSING",
                        ErrorCategory.CONTRACT,
                        "chunk must retain upstream lineage references",
                        context={"chunk_id": chunk.chunk_id},
                    )
                )

    def _validate_graph_edges(
        self,
        edges: Sequence[object],
        nodes: dict[str, object],
        snapshot: RunSnapshot,
    ) -> None:
        for edge in edges:
            source_node_id = edge.source_node_id  # type: ignore[attr-defined]
            target_node_id = edge.target_node_id  # type: ignore[attr-defined]
            if source_node_id not in nodes or target_node_id not in nodes:
                raise InvariantViolationError(
                    error(
                        "P3_S13_M01_ORPHAN_EDGE",
                        ErrorCategory.INVARIANT,
                        "edge references a missing node",
                        context={"edge_id": edge.edge_id},  # type: ignore[attr-defined]
                    )
                )
            if (
                edge.available_at > snapshot.as_of_time  # type: ignore[attr-defined]
                or not edge.evidence_refs  # type: ignore[attr-defined]
            ):
                raise InvariantViolationError(
                    error(
                        "P3_S13_M01_EDGE_INVALID",
                        ErrorCategory.INVARIANT,
                        "edge violates temporal or evidence invariant",
                        context={"edge_id": edge.edge_id},  # type: ignore[attr-defined]
                    )
                )

    def _load_chunks(self, rag_index: RagIndexArtifact) -> tuple[Chunk, ...]:
        reference = rag_index.chunk_catalog.artifact_ref
        if reference is None:
            if rag_index.coverage.chunk_count == 0:
                return ()
            raise ContractError(
                error(
                    "P3_S13_M01_CHUNK_CATALOG_MISSING",
                    ErrorCategory.CONTRACT,
                    "RAG reports chunks without a chunk catalog",
                )
            )
        content = self._store.get_bytes(reference)
        if sha256_bytes(content) != reference.content_hash:
            raise InvariantViolationError(
                error(
                    "P3_S13_M01_CHUNK_CATALOG_HASH_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "chunk catalog hash mismatch",
                )
            )
        chunks = decode_records(content, Chunk, reference.media_type)
        if len(chunks) != rag_index.coverage.chunk_count:
            raise InvariantViolationError(
                error(
                    "P3_S13_M01_CHUNK_CARDINALITY_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "chunk catalog cardinality differs from RAG coverage",
                )
            )
        return chunks

    def _persist_component(
        self,
        name: str,
        records: Sequence[BaseModel],
        config: GraphConfig,
    ) -> GraphComponent:
        content, media_type, suffix, version = encode_records(
            records,
            config.record_format,
        )
        reference = self._store.put_bytes(
            artifact_type=name,
            content=content,
            media_type=media_type,
            suffix=suffix,
            record_count=len(records),
            format_version=version,
        )
        return GraphComponent(
            name=name,
            status=(
                CapabilityStatus.READY
                if records
                else CapabilityStatus.NOT_APPLICABLE
            ),
            artifact_ref=reference,
            adapter_id=f"portable_{config.record_format.value.casefold()}",
            adapter_version="1.0.0",
            record_count=len(records),
            format_version=version,
            qualification_status="IMPLEMENTED_QUALIFIED_INTERNAL",
        )

    @staticmethod
    def _coverage(
        nodes: Sequence[object],
        edges: Sequence[object],
        assertions: Sequence[object],
        *,
        rejected_proposal_count: int,
    ) -> GraphCoverage:
        node_types = [node.node_type.value for node in nodes]  # type: ignore[attr-defined]
        return GraphCoverage(
            node_count=len(nodes),
            edge_count=len(edges),
            assertion_count=len(assertions),
            source_count=node_types.count("SOURCE"),
            document_count=node_types.count("DOCUMENT"),
            chunk_count=node_types.count("CHUNK"),
            entity_count=sum(
                value
                in {
                    "ENTITY",
                    "ORGANIZATION",
                    "PERSON",
                    "UNDERLYING",
                    "MACRO_INDICATOR",
                }
                for value in node_types
            ),
            event_count=node_types.count("EVENT"),
            claim_count=node_types.count("CLAIM"),
            rejected_proposal_count=rejected_proposal_count,
        )


def _batched(
    values: Sequence[Chunk],
    size: int,
) -> tuple[tuple[Chunk, ...], ...]:
    return tuple(
        tuple(values[index : index + size])
        for index in range(0, len(values), size)
    )
