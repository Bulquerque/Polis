"""Strict P3.S8 boundary models."""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .upstream_s7 import PersonSeedPanel, ValidatedPopulationManifest

UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Hash64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PersonId = Annotated[str, Field(pattern=r"^person_[0-9a-f]{24}$")]
PopulationId = Annotated[str, Field(pattern=r"^population_[0-9a-f]{24}$")]
GraphId = Annotated[str, Field(pattern=r"^graph_[0-9a-f]{24}$")]
EdgeId = Annotated[str, Field(pattern=r"^edge_[0-9a-f]{24}$")]
PairId = Annotated[str, Field(pattern=r"^pair_[0-9a-f]{24}$")]
LineageId = Annotated[str, Field(pattern=r"^lin_[0-9a-f]{24}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_json_arrays(cls, value: object) -> object:
        def convert(item: object) -> object:
            if isinstance(item, list):
                return tuple(convert(element) for element in item)
            if isinstance(item, dict):
                return {key: convert(element) for key, element in item.items()}
            return item
        return convert(value)


class GraphDirection(StrEnum):
    DIRECTED_RECIPROCAL_PAIRS = "DIRECTED_RECIPROCAL_PAIRS"


class EdgeOrigin(StrEnum):
    INTRA_FAMILY_BACKBONE = "INTRA_FAMILY_BACKBONE"
    CROSS_FAMILY_BRIDGE = "CROSS_FAMILY_BRIDGE"
    PROBABILISTIC = "PROBABILISTIC"
    MIN_DEGREE_REPAIR = "MIN_DEGREE_REPAIR"


class ValidationStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class IssueSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ProbabilityWeights(StrictModel):
    intercept: float
    same_institution: float
    role_similarity: float
    tag_cosine: float
    same_geography: float


class TrustDomainFormula(StrictModel):
    base: UnitFloat
    target_research: UnitFloat = 0.0
    target_quantitative: UnitFloat = 0.0
    target_verbal: UnitFloat = 0.0
    target_coding: UnitFloat = 0.0
    target_tool_use: UnitFloat = 0.0
    target_information_access: UnitFloat = 0.0
    pair_tag_cosine: UnitFloat = 0.0
    same_institution: UnitFloat = 0.0
    role_similarity: UnitFloat = 0.0

    @model_validator(mode="after")
    def bounded_coefficients(self) -> "TrustDomainFormula":
        if sum(self.model_dump().values()) > 2.0:
            raise ValueError("trust-domain coefficients exceed the safe normalization ceiling")
        return self


class SocialGraphConfig(StrictModel):
    config_id: Literal["P3_S8_SOCIAL_GRAPH_CONFIG_V2"]
    config_version: Literal["2.0.0"]
    architecture_revision: Literal["P3-FINAL"]
    graph_direction: Literal[GraphDirection.DIRECTED_RECIPROCAL_PAIRS]
    graph_seed_algorithm: Literal["sha256_uint63_v1"]
    pair_random_algorithm: Literal["sha256_pair_uniform_v1"]
    edge_id_algorithm: Literal["sha256_directed_edge_v1"]
    probability_formula_version: Literal["sigmoid_homophily_v2"]
    probability_weights: ProbabilityWeights
    minimum_neighbor_degree: PositiveInt
    maximum_neighbor_degree: PositiveInt
    maximum_connected_components: PositiveInt
    minimum_bridge_pairs_between_role_families: NonNegativeInt
    maximum_hub_share: UnitFloat
    relationship_types: tuple[str, ...] = Field(min_length=1)
    trust_domains: tuple[str, ...] = Field(min_length=1)
    trust_domain_formulas: dict[str, TrustDomainFormula]
    global_trust_floor: UnitFloat
    global_trust_ceiling: UnitFloat
    numeric_precision: Annotated[int, Field(ge=6, le=15)] = 12

    @model_validator(mode="after")
    def validate_config(self) -> "SocialGraphConfig":
        if self.minimum_neighbor_degree > self.maximum_neighbor_degree:
            raise ValueError("minimum degree cannot exceed maximum degree")
        if self.global_trust_floor >= self.global_trust_ceiling:
            raise ValueError("global trust floor must be below ceiling")
        if len(self.relationship_types) != len(set(self.relationship_types)):
            raise ValueError("relationship types must be unique")
        if len(self.trust_domains) != len(set(self.trust_domains)):
            raise ValueError("trust domains must be unique")
        if set(self.trust_domains) != set(self.trust_domain_formulas):
            raise ValueError("trust-domain formulas must exactly cover trust domains")
        return self


class TagValue(StrictModel):
    tag_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    effective_value: UnitFloat


class CapabilityVector(StrictModel):
    research: UnitFloat
    quantitative: UnitFloat
    verbal: UnitFloat
    coding: UnitFloat
    tool_use: UnitFloat


class ResourceVector(StrictModel):
    information_access: UnitFloat
    research_time: UnitFloat
    computational_access: UnitFloat


class SocialNode(StrictModel):
    person_id: PersonId
    candidate_id: str = Field(pattern=r"^cand_[0-9a-f]{24}$")
    representation_weight: UnitFloat
    person_seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    economic_role: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    role_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    institution_type: str | None
    geography: str = Field(min_length=1)
    tags: tuple[TagValue, ...] = Field(min_length=1)
    capabilities: CapabilityVector
    resources: ResourceVector
    profile_fingerprint: Hash64
    node_hash: Hash64
    lineage_id: LineageId

    @model_validator(mode="after")
    def unique_tags(self) -> "SocialNode":
        ids = [tag.tag_id for tag in self.tags]
        if len(ids) != len(set(ids)):
            raise ValueError("social-node tags must be unique")
        return self


class DomainTrust(StrictModel):
    domain_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: UnitFloat


class SocialEdge(StrictModel):
    edge_id: EdgeId
    reciprocal_pair_id: PairId
    source_person_id: PersonId
    target_person_id: PersonId
    relationship_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    origin: EdgeOrigin
    global_trust: UnitFloat
    domain_trust: tuple[DomainTrust, ...] = Field(min_length=1)
    influence: UnitFloat
    interaction_frequency: UnitFloat
    selection_probability: UnitFloat
    pair_uniform: UnitFloat
    edge_hash: Hash64
    lineage_id: LineageId

    @model_validator(mode="after")
    def edge_invariants(self) -> "SocialEdge":
        if self.source_person_id == self.target_person_id:
            raise ValueError("self loops are forbidden")
        domains = [item.domain_id for item in self.domain_trust]
        if len(domains) != len(set(domains)):
            raise ValueError("domain trust entries must be unique")
        return self


class GraphMetrics(StrictModel):
    node_count: PositiveInt
    directed_edge_count: NonNegativeInt
    reciprocal_pair_count: NonNegativeInt
    connected_component_count: PositiveInt
    isolated_node_count: NonNegativeInt
    cross_family_bridge_pair_count: NonNegativeInt
    minimum_neighbor_degree: NonNegativeInt
    maximum_neighbor_degree: NonNegativeInt
    mean_neighbor_degree: NonNegativeFloat
    maximum_hub_share: UnitFloat
    degree_by_person: dict[str, NonNegativeInt]
    relationship_pair_counts: dict[str, NonNegativeInt]
    role_family_pair_counts: dict[str, NonNegativeInt]


class InitialSocialGraph(StrictModel):
    schema_id: Literal["initial_social_graph.v2"] = "initial_social_graph.v2"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    creator_run_id: str
    population_id: PopulationId
    graph_id: GraphId
    graph_seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    graph_direction: GraphDirection
    nodes: tuple[SocialNode, ...] = Field(min_length=1)
    edges: tuple[SocialEdge, ...]
    metrics: GraphMetrics
    relationship_type_registry: tuple[str, ...]
    trust_domain_registry: tuple[str, ...]
    population_manifest_hash: Hash64
    validated_population_manifest_hash: Hash64
    person_seed_panel_hash: Hash64
    config_hash: Hash64
    graph_hash: Hash64
    lineage_id: LineageId

    @model_validator(mode="after")
    def unique_graph_records(self) -> "InitialSocialGraph":
        for values, label in [
            ([node.person_id for node in self.nodes], "node person_id"),
            ([edge.edge_id for edge in self.edges], "edge_id"),
        ]:
            if len(values) != len(set(values)):
                raise ValueError(f"graph requires unique {label}")
        return self


class ValidationIssue(StrictModel):
    issue_code: str = Field(pattern=r"^[A-Z0-9_]+$")
    severity: IssueSeverity
    message: str = Field(min_length=1)
    subject_ids: tuple[str, ...] = ()


class ValidationCheck(StrictModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    status: CheckStatus
    observed: str
    expected: str
    issue_codes: tuple[str, ...] = ()


class ValidatedInitialSocialGraph(StrictModel):
    schema_id: Literal["validated_initial_social_graph.v2"] = "validated_initial_social_graph.v2"
    schema_version: Literal["v14.1-rc4.1-p3r2"] = "v14.1-rc4.1-p3r2"
    validation_status: ValidationStatus
    initial_social_graph: InitialSocialGraph
    checks: tuple[ValidationCheck, ...]
    issues: tuple[ValidationIssue, ...]
    validated_graph_hash: Hash64
    lineage_id: LineageId
    production_promotion_allowed: Literal[False] = False

    @model_validator(mode="after")
    def status_matches_issues(self) -> "ValidatedInitialSocialGraph":
        has_error = any(issue.severity is IssueSeverity.ERROR for issue in self.issues)
        if has_error != (self.validation_status is ValidationStatus.BLOCKED):
            raise ValueError("validation status must match error issues")
        return self


class InitialSocialGraphBuildRequest(StrictModel):
    validated_population_manifest: ValidatedPopulationManifest
    person_seed_panel: PersonSeedPanel
    social_graph_config: SocialGraphConfig
    personality_tag_registry: tuple[str, ...] = Field(min_length=1)


class InitialSocialGraphBuildResult(StrictModel):
    initial_social_graph: InitialSocialGraph


class RelationshipPriorValidationRequest(StrictModel):
    initial_social_graph: InitialSocialGraph
    social_graph_config: SocialGraphConfig


class RelationshipPriorValidationResult(StrictModel):
    validated_initial_social_graph: ValidatedInitialSocialGraph
