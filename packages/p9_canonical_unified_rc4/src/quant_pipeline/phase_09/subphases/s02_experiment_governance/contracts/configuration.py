from __future__ import annotations

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.artifacts import ArtifactReference

from .base import (
    CatalogState,
    ConfigurationId,
    NonEmptyStr,
    ParameterId,
    ReasonCode,
    Sha256Hex,
    StrictModel,
)
from .budget import SearchBudgetPlan
from .parameters import HyperparameterSchemaSnapshot, ParameterScalar
from .search_space import CompiledSearchSpace


class SeedPolicyReference(StrictModel):
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    base_seed: int = Field(ge=0)
    derivation_algorithm: NonEmptyStr
    policy_sha256: Sha256Hex


class FoldPlanReference(StrictModel):
    request_id: NonEmptyStr
    request_sha256: Sha256Hex


class ConfigurationIdentityContext(StrictModel):
    code_artifact: ArtifactReference
    data_snapshot: ArtifactReference
    fold_plan: FoldPlanReference
    seed_policy: SeedPolicyReference
    policy_artifact_ids: tuple[NonEmptyStr, ...]
    policy_bundle_sha256: Sha256Hex


class ParameterAssignment(StrictModel):
    parameter_id: ParameterId
    value: ParameterScalar


class ConfigurationRecord(StrictModel):
    configuration_id: ConfigurationId
    experiment_id: NonEmptyStr
    assignments: tuple[ParameterAssignment, ...]
    active_parameter_ids: tuple[ParameterId, ...]
    source: NonEmptyStr
    source_index: int = Field(ge=0)
    boundary_parameter_ids: tuple[ParameterId, ...] = ()
    identity_preimage_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_assignments(self) -> "ConfigurationRecord":
        ids = [assignment.parameter_id for assignment in self.assignments]
        if ids != sorted(ids):
            raise ValueError("configuration assignments must be sorted by parameter ID")
        if len(ids) != len(set(ids)):
            raise ValueError("configuration assignments must be unique")
        if tuple(ids) != self.active_parameter_ids:
            raise ValueError("active_parameter_ids must exactly match assignment IDs")
        return self


class ConfigurationCatalog(StrictModel):
    catalog_id: NonEmptyStr
    experiment_id: NonEmptyStr
    state: CatalogState
    configurations: tuple[ConfigurationRecord, ...]
    catalog_sha256: Sha256Hex
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_catalog(self) -> "ConfigurationCatalog":
        ids = [configuration.configuration_id for configuration in self.configurations]
        if len(ids) != len(set(ids)):
            raise ValueError("configuration IDs must be unique")
        if self.state in {CatalogState.IDENTITY_COLLISION, CatalogState.LINEAGE_INVALID}:
            if not self.reason_codes:
                raise ValueError("blocking catalog state requires reason codes")
        return self


class ConfigurationLineageEdge(StrictModel):
    parent_configuration_id: ConfigurationId
    child_configuration_id: ConfigurationId
    relation: NonEmptyStr


class ConfigurationLineageGraph(StrictModel):
    configuration_ids: tuple[ConfigurationId, ...]
    edges: tuple[ConfigurationLineageEdge, ...] = ()

    @model_validator(mode="after")
    def validate_graph(self) -> "ConfigurationLineageGraph":
        nodes = set(self.configuration_ids)
        if len(nodes) != len(self.configuration_ids):
            raise ValueError("configuration lineage nodes must be unique")
        for edge in self.edges:
            if (
                edge.parent_configuration_id not in nodes
                or edge.child_configuration_id not in nodes
            ):
                raise ValueError("configuration lineage edge references unknown node")
            if edge.parent_configuration_id == edge.child_configuration_id:
                raise ValueError("configuration cannot be parent of itself")
        return self


class EconomicEquivalenceGroup(StrictModel):
    group_id: NonEmptyStr
    canonical_configuration_id: ConfigurationId
    member_configuration_ids: tuple[ConfigurationId, ...]
    equivalence_sha256: Sha256Hex


class EconomicEquivalenceGroups(StrictModel):
    groups: tuple[EconomicEquivalenceGroup, ...] = ()


class ConfigurationIdentityReceipt(StrictModel):
    catalog_id: NonEmptyStr
    generated_count: int = Field(ge=0)
    duplicate_proposals_discarded: int = Field(ge=0)
    boundary_configuration_count: int = Field(ge=0)
    receipt_sha256: Sha256Hex


class ConfigurationBuildInput(StrictModel):
    compiled_search_space: CompiledSearchSpace
    parameter_snapshot: HyperparameterSchemaSnapshot
    budget_plan: SearchBudgetPlan
    identity_context: ConfigurationIdentityContext


class ConfigurationBuildOutcome(StrictModel):
    catalog: ConfigurationCatalog | None
    lineage_graph: ConfigurationLineageGraph | None
    equivalence_groups: EconomicEquivalenceGroups | None
    identity_receipt: ConfigurationIdentityReceipt | None
