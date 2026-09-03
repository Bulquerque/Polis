from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import datetime

from .canonical import content_hash, normalize_name, tokenize
from .models import (
    Chunk,
    ConflictStatus,
    EvidenceOrigin,
    EvidenceRole,
    ExtractionMethod,
    GraphEdge,
    GraphElementType,
    GraphEvidenceAssertion,
    GraphNode,
    GraphProposalBatch,
    NodeType,
    ProposedEdge,
    ProposedNode,
    RelationType,
)


def stable_node_id(node_type: NodeType, resolution_key: str) -> str:
    return f"node_{content_hash({'type': node_type.value, 'key': resolution_key})[:24]}"


def stable_edge_id(source: str, target: str, relation: RelationType, valid_from: datetime | None) -> str:
    return f"edge_{content_hash({'source': source, 'target': target, 'relation': relation.value, 'valid_from': valid_from})[:24]}"


def resolution_key(node_type: NodeType, name: str) -> str:
    return f"{node_type.value}:{normalize_name(name)}"


def assertion_id(element_id: str, chunk_id: str, role: EvidenceRole, origin: EvidenceOrigin) -> str:
    return f"assert_{content_hash({'element': element_id, 'chunk': chunk_id, 'role': role.value, 'origin': origin.value})[:24]}"


def find_span(content: str, phrase: str) -> tuple[int, int] | None:
    content_tokens = tokenize(content)
    phrase_tokens = tokenize(phrase)
    if not phrase_tokens:
        return None
    width = len(phrase_tokens)
    for index in range(0, len(content_tokens) - width + 1):
        if content_tokens[index : index + width] == phrase_tokens:
            return index, index + width
    return None


class GraphAccumulator:
    def __init__(self, *, ontology_version: str) -> None:
        self.ontology_version = ontology_version
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.assertions: dict[str, GraphEvidenceAssertion] = {}

    def add_node(
        self,
        *,
        node_type: NodeType,
        name: str,
        chunk: Chunk,
        role: EvidenceRole,
        origin: EvidenceOrigin,
        confidence: float,
        aliases: tuple[str, ...] = (),
        attributes: dict[str, str | int | float | bool | None] | None = None,
    ) -> str:
        key = resolution_key(node_type, name)
        node_id = stable_node_id(node_type, key)
        assertion = self._make_assertion(
            element_id=node_id,
            element_type=GraphElementType.NODE,
            chunk=chunk,
            role=role,
            origin=origin,
            confidence=confidence,
            phrase=name,
        )
        current = self.nodes.get(node_id)
        evidence = tuple(sorted(set((current.evidence_refs if current else ()) + (assertion.assertion_id,))))
        provenance = tuple(sorted(set((current.provenance if current else ()) + chunk.lineage_refs)))
        node = GraphNode(
            node_id=node_id,
            node_type=node_type,
            canonical_name=current.canonical_name if current else name.strip(),
            aliases=tuple(sorted(set((current.aliases if current else ()) + aliases))),
            valid_from=min(filter(None, [current.valid_from if current else None, chunk.event_time or chunk.effective_time or chunk.available_at])),
            valid_to=current.valid_to if current else None,
            available_at=min(current.available_at, chunk.available_at) if current else chunk.available_at,
            attributes={**(current.attributes if current else {}), **(attributes or {})},
            evidence_refs=evidence,
            ontology_version=self.ontology_version,
            resolution_key=key,
            provenance=provenance,
        )
        self.nodes[node_id] = node
        self.assertions[assertion.assertion_id] = assertion
        return node_id

    def add_edge(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        relation_type: RelationType,
        chunk: Chunk,
        role: EvidenceRole,
        origin: EvidenceOrigin,
        method: ExtractionMethod,
        confidence: float,
    ) -> str:
        valid_from = chunk.event_time or chunk.effective_time or chunk.available_at
        edge_id = stable_edge_id(source_node_id, target_node_id, relation_type, valid_from)
        assertion = self._make_assertion(
            element_id=edge_id,
            element_type=GraphElementType.EDGE,
            chunk=chunk,
            role=role,
            origin=origin,
            confidence=confidence,
            phrase=None,
        )
        current = self.edges.get(edge_id)
        evidence = tuple(sorted(set((current.evidence_refs if current else ()) + (assertion.assertion_id,))))
        provenance = tuple(sorted(set((current.provenance if current else ()) + chunk.lineage_refs)))
        edge = GraphEdge(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type=relation_type,
            valid_from=valid_from,
            valid_to=None,
            available_at=min(current.available_at, chunk.available_at) if current else chunk.available_at,
            confidence=max(current.confidence if current else 0.0, confidence),
            evidence_refs=evidence,
            extraction_method=current.extraction_method if current else method,
            ontology_version=self.ontology_version,
            conflict_group_id=current.conflict_group_id if current else None,
            conflict_status=current.conflict_status if current else ConflictStatus.NONE,
            provenance=provenance,
        )
        self.edges[edge_id] = edge
        self.assertions[assertion.assertion_id] = assertion
        return edge_id

    def _make_assertion(
        self,
        *,
        element_id: str,
        element_type: GraphElementType,
        chunk: Chunk,
        role: EvidenceRole,
        origin: EvidenceOrigin,
        confidence: float,
        phrase: str | None,
    ) -> GraphEvidenceAssertion:
        span = find_span(chunk.content, phrase) if phrase else None
        return GraphEvidenceAssertion(
            assertion_id=assertion_id(element_id, chunk.chunk_id, role, origin),
            graph_element_id=element_id,
            graph_element_type=element_type,
            evidence_role=role,
            evidence_origin=origin,
            chunk_id=chunk.chunk_id,
            confidence=confidence,
            span_start_word=span[0] if span else None,
            span_end_word=span[1] if span else None,
            quote_hash=chunk.content_hash if span else None,
            provenance=chunk.lineage_refs,
        )

    def mark_conflicts(self) -> None:
        opposites = {RelationType.SUPPORTS: RelationType.OPPOSES, RelationType.OPPOSES: RelationType.SUPPORTS}
        index: dict[tuple[str, str, RelationType], GraphEdge] = {
            (edge.source_node_id, edge.target_node_id, edge.relation_type): edge for edge in self.edges.values()
        }
        for edge in list(self.edges.values()):
            opposite = opposites.get(edge.relation_type)
            if opposite is None:
                continue
            other = index.get((edge.source_node_id, edge.target_node_id, opposite))
            if other is None:
                continue
            group = f"conflict_{content_hash({'source': edge.source_node_id, 'target': edge.target_node_id})[:20]}"
            self.edges[edge.edge_id] = edge.model_copy(update={"conflict_group_id": group, "conflict_status": ConflictStatus.DISPUTED})
            self.edges[other.edge_id] = other.model_copy(update={"conflict_group_id": group, "conflict_status": ConflictStatus.DISPUTED})


def build_structured_graph(chunks: Sequence[Chunk], ontology_version: str) -> GraphAccumulator:
    graph = GraphAccumulator(ontology_version=ontology_version)
    for chunk in sorted(chunks, key=lambda item: item.chunk_id):
        source = graph.add_node(
            node_type=NodeType.SOURCE,
            name=chunk.source_id,
            chunk=chunk,
            role=EvidenceRole.PROVENANCE,
            origin=EvidenceOrigin.STRUCTURED_METADATA,
            confidence=1.0,
            attributes={"source_id": chunk.source_id},
        )
        document = graph.add_node(
            node_type=NodeType.DOCUMENT,
            name=chunk.document_id,
            chunk=chunk,
            role=EvidenceRole.PROVENANCE,
            origin=EvidenceOrigin.STRUCTURED_METADATA,
            confidence=1.0,
            attributes={"document_id": chunk.document_id},
        )
        chunk_node = graph.add_node(
            node_type=NodeType.CHUNK,
            name=chunk.chunk_id,
            chunk=chunk,
            role=EvidenceRole.PROVENANCE,
            origin=EvidenceOrigin.STRUCTURED_METADATA,
            confidence=1.0,
            attributes={"chunk_id": chunk.chunk_id, "content_hash": chunk.content_hash},
        )
        graph.add_edge(
            source_node_id=document,
            target_node_id=source,
            relation_type=RelationType.PUBLISHED_BY,
            chunk=chunk,
            role=EvidenceRole.PROVENANCE,
            origin=EvidenceOrigin.STRUCTURED_METADATA,
            method=ExtractionMethod.STRUCTURED_RULE,
            confidence=1.0,
        )
        graph.add_edge(
            source_node_id=document,
            target_node_id=chunk_node,
            relation_type=RelationType.CONTAINS,
            chunk=chunk,
            role=EvidenceRole.PROVENANCE,
            origin=EvidenceOrigin.STRUCTURED_METADATA,
            method=ExtractionMethod.STRUCTURED_RULE,
            confidence=1.0,
        )
        entity_nodes: list[str] = []
        for entity in sorted(set(chunk.entities)):
            node = graph.add_node(
                node_type=NodeType.ENTITY,
                name=entity,
                chunk=chunk,
                role=EvidenceRole.MENTION,
                origin=EvidenceOrigin.TEXT_SPAN if find_span(chunk.content, entity) else EvidenceOrigin.STRUCTURED_METADATA,
                confidence=chunk.source_quality,
            )
            entity_nodes.append(node)
            graph.add_edge(
                source_node_id=chunk_node,
                target_node_id=node,
                relation_type=RelationType.MENTIONS,
                chunk=chunk,
                role=EvidenceRole.MENTION,
                origin=EvidenceOrigin.STRUCTURED_METADATA,
                method=ExtractionMethod.STRUCTURED_RULE,
                confidence=chunk.source_quality,
            )
        underlying_nodes: list[str] = []
        for underlying in sorted(set(chunk.underlyings)):
            node = graph.add_node(
                node_type=NodeType.UNDERLYING,
                name=underlying,
                chunk=chunk,
                role=EvidenceRole.MENTION,
                origin=EvidenceOrigin.TEXT_SPAN if find_span(chunk.content, underlying) else EvidenceOrigin.STRUCTURED_METADATA,
                confidence=chunk.source_quality,
            )
            underlying_nodes.append(node)
            graph.add_edge(
                source_node_id=chunk_node,
                target_node_id=node,
                relation_type=RelationType.REFERS_TO,
                chunk=chunk,
                role=EvidenceRole.MENTION,
                origin=EvidenceOrigin.STRUCTURED_METADATA,
                method=ExtractionMethod.STRUCTURED_RULE,
                confidence=chunk.source_quality,
            )
        if chunk.event_time is not None:
            event_name = f"{chunk.document_id}@{chunk.event_time.isoformat()}"
            event = graph.add_node(
                node_type=NodeType.EVENT,
                name=event_name,
                chunk=chunk,
                role=EvidenceRole.TEMPORAL_CONTEXT,
                origin=EvidenceOrigin.STRUCTURED_METADATA,
                confidence=chunk.source_quality,
                attributes={"event_time": chunk.event_time.isoformat()},
            )
            graph.add_edge(
                source_node_id=document,
                target_node_id=event,
                relation_type=RelationType.DESCRIBES,
                chunk=chunk,
                role=EvidenceRole.TEMPORAL_CONTEXT,
                origin=EvidenceOrigin.STRUCTURED_METADATA,
                method=ExtractionMethod.STRUCTURED_RULE,
                confidence=chunk.source_quality,
            )
            for node in entity_nodes + underlying_nodes:
                graph.add_edge(
                    source_node_id=event,
                    target_node_id=node,
                    relation_type=RelationType.INVOLVES,
                    chunk=chunk,
                    role=EvidenceRole.MENTION,
                    origin=EvidenceOrigin.STRUCTURED_METADATA,
                    method=ExtractionMethod.STRUCTURED_RULE,
                    confidence=chunk.source_quality,
                )
        for entity in entity_nodes:
            for underlying in underlying_nodes:
                graph.add_edge(
                    source_node_id=entity,
                    target_node_id=underlying,
                    relation_type=RelationType.CO_OCCURS_WITH,
                    chunk=chunk,
                    role=EvidenceRole.MENTION,
                    origin=EvidenceOrigin.STRUCTURED_METADATA,
                    method=ExtractionMethod.CO_OCCURRENCE_RULE,
                    confidence=min(chunk.source_quality, 0.75),
                )
    return graph


def apply_provider_proposals(
    graph: GraphAccumulator,
    proposals: GraphProposalBatch,
    chunks_by_id: dict[str, Chunk],
    *,
    min_confidence: float,
) -> int:
    rejected = 0
    proposed_nodes: dict[tuple[NodeType, str], str] = {}
    for proposal in proposals.nodes:
        valid_chunks = [chunks_by_id[item] for item in proposal.chunk_ids if item in chunks_by_id]
        if proposal.confidence < min_confidence or not valid_chunks:
            rejected += 1
            continue
        for chunk in valid_chunks:
            node_id = graph.add_node(
                node_type=proposal.node_type,
                name=proposal.canonical_name,
                aliases=proposal.aliases,
                chunk=chunk,
                role=EvidenceRole.MENTION,
                origin=EvidenceOrigin.PROVIDER_PROPOSAL,
                confidence=proposal.confidence,
            )
            proposed_nodes[(proposal.node_type, normalize_name(proposal.canonical_name))] = node_id
    for proposal in proposals.edges:
        valid_chunks = [chunks_by_id[item] for item in proposal.chunk_ids if item in chunks_by_id]
        source = graph.nodes.get(stable_node_id(proposal.source_type, resolution_key(proposal.source_type, proposal.source_name)))
        target = graph.nodes.get(stable_node_id(proposal.target_type, resolution_key(proposal.target_type, proposal.target_name)))
        if proposal.confidence < min_confidence or not valid_chunks or source is None or target is None:
            rejected += 1
            continue
        role = {
            RelationType.OPPOSES: EvidenceRole.OPPOSITION,
            RelationType.SUPPORTS: EvidenceRole.SUPPORT,
            RelationType.AFFECTS: EvidenceRole.CAUSAL_CONTEXT,
        }.get(proposal.relation_type, EvidenceRole.MENTION)
        for chunk in valid_chunks:
            graph.add_edge(
                source_node_id=source.node_id,
                target_node_id=target.node_id,
                relation_type=proposal.relation_type,
                chunk=chunk,
                role=role,
                origin=EvidenceOrigin.PROVIDER_PROPOSAL,
                method=ExtractionMethod.PROVIDER_STRUCTURED_OUTPUT,
                confidence=proposal.confidence,
            )
    graph.mark_conflicts()
    return rejected
