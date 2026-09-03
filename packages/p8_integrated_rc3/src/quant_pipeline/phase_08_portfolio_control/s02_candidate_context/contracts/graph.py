
"""Typed immutable structural exposure graph."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from quant_pipeline.phase_08_contracts.base import NonEmptyStr, SHA256Str, StrictModel

from .enums import ExposureNodeType, ExposureRelationType


class ExposureNode(StrictModel):
    node_id: NonEmptyStr
    node_type: ExposureNodeType
    label: NonEmptyStr


class ExposureEdge(StrictModel):
    edge_id: NonEmptyStr
    source_node_id: NonEmptyStr
    target_node_id: NonEmptyStr
    relation: ExposureRelationType
    instrument_id: NonEmptyStr | None = None
    signed_contract_quantity: Decimal | None = None
    expiration: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_relation_fields(self) -> Self:
        if self.relation is ExposureRelationType.CANDIDATE_HAS_LEG:
            if self.instrument_id is None or self.signed_contract_quantity is None:
                raise ValueError("candidate-leg edges require instrument and signed quantity")
        elif self.signed_contract_quantity is not None:
            raise ValueError("signed quantity is only valid for candidate-leg edges")
        return self


class GraphComponent(StrictModel):
    component_id: NonEmptyStr
    node_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)


class StructuralExposureGraph(StrictModel):
    contract_version: Literal["P8_STRUCTURAL_EXPOSURE_GRAPH_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    nodes: tuple[ExposureNode, ...]
    edges: tuple[ExposureEdge, ...]
    connected_components: tuple[GraphComponent, ...]
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        node_ids = tuple(node.node_id for node in self.nodes)
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("graph node IDs must be unique")
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("graph edge IDs must be unique")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source_node_id not in known or edge.target_node_id not in known:
                raise ValueError("graph edge references unknown node")
        flattened = [node_id for component in self.connected_components for node_id in component.node_ids]
        if sorted(flattened) != sorted(node_ids):
            raise ValueError("connected components must partition all graph nodes")
        return self
