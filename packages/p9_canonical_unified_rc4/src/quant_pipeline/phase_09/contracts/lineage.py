from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from .artifacts import ArtifactReference
from .base import (
    ArtifactId,
    CycleId,
    NonEmptyStr,
    PhaseId,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)
from .integrity import IntegrityEnvelope


class LineageRelation(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    USED = "USED"
    GENERATED_BY = "GENERATED_BY"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    SPECIALIZATION_OF = "SPECIALIZATION_OF"


class LineageNode(StrictModel):
    node_id: NonEmptyStr
    phase_id: PhaseId
    entity_type: NonEmptyStr
    artifact: ArtifactReference
    generated_at: UtcDateTime


class LineageEdge(StrictModel):
    edge_id: NonEmptyStr
    parent_node_id: NonEmptyStr
    child_node_id: NonEmptyStr
    relation: LineageRelation
    occurred_at: UtcDateTime
    activity_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def reject_self_edge(self) -> "LineageEdge":
        if self.parent_node_id == self.child_node_id:
            raise ValueError("lineage self-edge is not allowed")
        return self


class LineageManifestPayload(StrictModel):
    manifest_id: ArtifactId
    cycle_id: CycleId
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    root_node_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "LineageManifestPayload":
        node_ids = [node.node_id for node in self.nodes]
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("lineage node IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("lineage edge IDs must be unique")
        node_set = set(node_ids)
        if not set(self.root_node_ids).issubset(node_set):
            raise ValueError("root_node_ids must reference existing nodes")
        for edge in self.edges:
            if edge.parent_node_id not in node_set or edge.child_node_id not in node_set:
                raise ValueError("lineage edges must reference existing nodes")
        return self


class LineageManifest(StrictModel):
    payload: LineageManifestPayload
    integrity: IntegrityEnvelope


class LineageGap(StrictModel):
    gap_id: NonEmptyStr
    description: NonEmptyStr
    material: bool
    reason_code: ReasonCode
    affected_node_ids: tuple[NonEmptyStr, ...] = ()


class LineageResolutionStatus(StrEnum):
    RESOLVED_COMPLETE = "RESOLVED_COMPLETE"
    RESOLVED_WITH_NONMATERIAL_GAPS = "RESOLVED_WITH_NONMATERIAL_GAPS"
    INCOMPLETE_MATERIAL = "INCOMPLETE_MATERIAL"
    CORRUPT = "CORRUPT"
    UNAVAILABLE = "UNAVAILABLE"


class ResolvedLineageGraph(StrictModel):
    status: LineageResolutionStatus
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    topological_order: tuple[NonEmptyStr, ...]
    gaps: tuple[LineageGap, ...]
    graph_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_order(self) -> "ResolvedLineageGraph":
        node_ids = {node.node_id for node in self.nodes}
        if set(self.topological_order) != node_ids:
            raise ValueError("topological order must cover every node exactly once")
        positions = {node_id: index for index, node_id in enumerate(self.topological_order)}
        for edge in self.edges:
            if edge.relation is LineageRelation.DERIVED_FROM:
                if positions[edge.parent_node_id] >= positions[edge.child_node_id]:
                    raise ValueError("DERIVED_FROM edge violates topological order")
        return self


class LineageGapReport(StrictModel):
    status: LineageResolutionStatus
    gaps: tuple[LineageGap, ...]
    required_phase_ids: tuple[PhaseId, ...]
    observed_phase_ids: tuple[PhaseId, ...]


class LineageResolutionReceipt(StrictModel):
    manifest_artifact_id: ArtifactId
    graph_sha256: Sha256Hex
    verified_artifact_ids: tuple[ArtifactId, ...]
    unresolved_artifact_ids: tuple[ArtifactId, ...]
    reason_codes: tuple[ReasonCode, ...] = ()
