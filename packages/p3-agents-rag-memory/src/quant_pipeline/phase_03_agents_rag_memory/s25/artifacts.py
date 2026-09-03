"""Strong artifact contracts for P3.S25."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from .types import (
    ArtifactContext,
    AwareDateTime,
    ChangeDecision,
    ChangeDecisionValue,
    DeliveryStatus,
    DeliveryStatusValue,
    EligibilityStatus,
    EligibilityStatusValue,
    EntitlementStatus,
    EntitlementStatusValue,
    ExecutionStatus,
    ExecutionStatusValue,
    ExperienceType,
    ExperienceTypeValue,
    FeedbackStatus,
    FeedbackStatusValue,
    NonEmptyStr,
    NonNegativeInt,
    Probability,
    RetroPatchStatus,
    RetroPatchStatusValue,
    SignedSignal,
    StrictModel,
    StringTuple,
    ValidationStatus,
    ValidationStatusValue,
    _to_tuple,
)

ModelTuple = Annotated[tuple[Any, ...], BeforeValidator(_to_tuple)]


class GraphNode(StrictModel):
    person_id: NonEmptyStr
    role_family: NonEmptyStr
    active: bool = True


class RelationshipEdge(StrictModel):
    edge_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    trust_by_domain: dict[NonEmptyStr, Probability]
    general_trust: Probability
    interaction_count: NonNegativeInt = 0
    last_observed_at: AwareDateTime | None = None
    created_at: AwareDateTime
    valid_from_cycle: NonNegativeInt
    lineage_ids: StringTuple

    @model_validator(mode="after")
    def validate_edge(self) -> "RelationshipEdge":
        if self.source_person_id == self.target_person_id:
            raise ValueError("self-edge is forbidden")
        if not self.trust_by_domain:
            raise ValueError("trust_by_domain cannot be empty")
        return self


class SocialGraphBase(ArtifactContext):
    directed: Literal[True] = True
    nodes: Annotated[tuple[GraphNode, ...], BeforeValidator(_to_tuple)]
    records: Annotated[tuple[RelationshipEdge, ...], BeforeValidator(_to_tuple)]

    @model_validator(mode="after")
    def validate_graph_identity(self) -> "SocialGraphBase":
        people = [node.person_id for node in self.nodes]
        if len(people) != len(set(people)):
            raise ValueError("duplicate person_id in graph nodes")
        known = set(people)
        edge_ids: set[str] = set()
        edge_keys: set[tuple[str, str, str]] = set()
        for edge in self.records:
            if edge.source_person_id not in known or edge.target_person_id not in known:
                raise ValueError("edge references an unknown person")
            key = (edge.source_person_id, edge.target_person_id, edge.relationship_type)
            if edge.edge_id in edge_ids or key in edge_keys:
                raise ValueError("duplicate social edge")
            edge_ids.add(edge.edge_id)
            edge_keys.add(key)
        return self


class CurrentSocialGraph(SocialGraphBase):
    schema_version: Literal[
        "v14.1-rc4.1",
        "p3.s25.current_social_graph.v2",
    ]


class SocialDeliveryRecord(StrictModel):
    message_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    receiver_person_id: NonEmptyStr
    status: DeliveryStatusValue
    created_cycle: NonNegativeInt
    effective_cycle: NonNegativeInt
    created_at: AwareDateTime
    status_at: AwareDateTime
    causal_parent_id: NonEmptyStr | None = None
    evidence_refs: StringTuple = ()
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_message(self) -> "SocialDeliveryRecord":
        if self.sender_person_id == self.receiver_person_id:
            raise ValueError("self-message is forbidden")
        if self.effective_cycle < self.created_cycle:
            raise ValueError("effective_cycle cannot precede created_cycle")
        if self.status_at < self.created_at:
            raise ValueError("status_at cannot precede created_at")
        return self


class SocialDeliveryPanel(ArtifactContext):
    schema_version: Literal[
        "v14.1-rc4.1",
        "p3.s25.social_delivery_panel.v2",
    ]
    records: Annotated[tuple[SocialDeliveryRecord, ...], BeforeValidator(_to_tuple)]


class RelationshipObservation(StrictModel):
    observation_id: NonEmptyStr
    observer_person_id: NonEmptyStr
    counterparty_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    domain: NonEmptyStr
    signal: SignedSignal
    reliability: Probability
    experience_type: ExperienceTypeValue
    source_message_id: NonEmptyStr | None = None
    observed_at: AwareDateTime
    effective_cycle: NonNegativeInt
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_observation(self) -> "RelationshipObservation":
        if self.observer_person_id == self.counterparty_person_id:
            raise ValueError("self-observation is forbidden")
        return self


class NextPersonStateRecord(StrictModel):
    person_id: NonEmptyStr
    relationship_observations: Annotated[
        tuple[RelationshipObservation, ...], BeforeValidator(_to_tuple)
    ] = ()


class ValidatedNextPersonStatePanel(ArtifactContext):
    schema_version: Literal[
        "v14.1-rc4.1",
        "p3.s25.validated_next_person_state_panel.v2",
    ]
    records: Annotated[tuple[NextPersonStateRecord, ...], BeforeValidator(_to_tuple)]


class BeliefFeedbackRecord(StrictModel):
    feedback_id: NonEmptyStr
    commitment_id: NonEmptyStr
    observer_person_id: NonEmptyStr
    counterparty_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    domain: NonEmptyStr
    outcome_alignment: SignedSignal
    reliability: Probability
    status: FeedbackStatusValue
    matured_at: AwareDateTime
    effective_cycle: NonNegativeInt
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr


class ActiveBeliefFeedbackBundle(ArtifactContext):
    schema_version: Literal[
        "v14.1-rc4.1",
        "p3.s25.active_belief_feedback_bundle.v2",
    ]
    items: Annotated[tuple[BeliefFeedbackRecord, ...], BeforeValidator(_to_tuple)]


class TrustChange(StrictModel):
    change_id: NonEmptyStr
    edge_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    domain: NonEmptyStr
    old_value: Probability
    normalized_signal: SignedSignal
    raw_delta: Annotated[float, Field(ge=-1.0, le=1.0)]
    applied_delta: Annotated[float, Field(ge=-1.0, le=1.0)]
    new_value: Probability
    experience_ids: StringTuple
    formula_version: NonEmptyStr
    changed_at: AwareDateTime
    lineage_ids: StringTuple


class UpdatedSocialGraph(SocialGraphBase):
    schema_version: Literal["p3.s25.updated_social_graph.v2"]
    changes: Annotated[tuple[TrustChange, ...], BeforeValidator(_to_tuple)]


class SocialToolAuditRecord(StrictModel):
    audit_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    event_id: NonEmptyStr
    occurred_at: AwareDateTime
    effective_cycle: NonNegativeInt
    entitlement_status: EntitlementStatusValue
    execution_status: ExecutionStatusValue
    validation_status: ValidationStatusValue
    mutual_relevance: Probability
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_audit(self) -> "SocialToolAuditRecord":
        if self.source_person_id == self.target_person_id:
            raise ValueError("self-relationship audit is forbidden")
        return self


class SocialToolAuditPanel(ArtifactContext):
    schema_version: Literal[
        "v14.1-rc4.1",
        "p3.s25.social_tool_audit_panel.v2",
    ]
    records: Annotated[tuple[SocialToolAuditRecord, ...], BeforeValidator(_to_tuple)]


class ActiveRetroPolicyPatch(StrictModel):
    status: RetroPatchStatusValue
    patch_id: NonEmptyStr
    change_type: NonEmptyStr
    change_target: NonEmptyStr
    promoted_at: AwareDateTime
    effective_cycle_id: NonNegativeInt
    lineage_id: NonEmptyStr
    parameters: dict[NonEmptyStr, bool | int | float | str]


class RelationshipProposal(StrictModel):
    relationship_change_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    eligibility_status: EligibilityStatusValue
    criteria_passed: StringTuple
    criteria_failed: StringTuple
    supporting_event_ids: StringTuple
    interaction_count: NonNegativeInt
    mean_mutual_relevance: Probability
    initial_trust_by_domain: dict[NonEmptyStr, Probability]
    proposed_at: AwareDateTime
    effective_cycle: NonNegativeInt
    lineage_ids: StringTuple


class RelationshipCandidatePanel(ArtifactContext):
    schema_version: Literal["p3.s25.relationship_candidate_panel.v2"]
    records: Annotated[tuple[RelationshipProposal, ...], BeforeValidator(_to_tuple)]
    policy_version: NonEmptyStr
    policy_patch_id: NonEmptyStr


class RelationshipDecisionRecord(StrictModel):
    relationship_change_id: NonEmptyStr
    decision: ChangeDecisionValue
    reason_codes: StringTuple
    edge_id: NonEmptyStr | None = None


class TopologyMetrics(StrictModel):
    node_count: NonNegativeInt
    edge_count: NonNegativeInt
    min_degree: NonNegativeInt
    max_degree: NonNegativeInt
    connected_components: NonNegativeInt
    bridge_edges_between_role_families: NonNegativeInt
    max_hub_share: Probability


class NextSocialGraph(SocialGraphBase):
    schema_version: Literal["p3.s25.next_social_graph.v2"]
    applied_changes: Annotated[
        tuple[RelationshipDecisionRecord, ...], BeforeValidator(_to_tuple)
    ]
    rejected_changes: Annotated[
        tuple[RelationshipDecisionRecord, ...], BeforeValidator(_to_tuple)
    ]
    topology_metrics: TopologyMetrics
    content_hash: NonEmptyStr
