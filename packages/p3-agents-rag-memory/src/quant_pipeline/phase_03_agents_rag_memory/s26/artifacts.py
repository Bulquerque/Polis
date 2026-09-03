"""Typed artifacts for P3.S26."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BeforeValidator, Field, model_validator
from .types import *
from .types import _tuple

class MemoryItem(StrictModel):
    memory_id: NonEmptyStr; person_id: NonEmptyStr; memory_type: MemoryTypeValue; source_event_ids: StringTuple
    created_at: AwareDateTime; available_at: AwareDateTime; valid_from_cycle: NonNegativeInt
    importance: Probability; confidence: Probability; retrievability: Probability
    content_ref: NonEmptyStr; content_fingerprint: NonEmptyStr; evidence_refs: StringTuple
    status: MemoryStatusValue; supersedes_memory_id: NonEmptyStr|None=None; reinforcement_count: NonNegativeInt=1
    last_reinforced_at: AwareDateTime|None=None; protected_audit: bool=False; lineage_ids: StringTuple
    @model_validator(mode="after")
    def check(self)->"MemoryItem":
        if self.available_at<self.created_at: raise ValueError("available_at cannot precede created_at")
        if self.memory_type==MemoryType.AUDIT and not self.protected_audit: raise ValueError("AUDIT memory must be protected")
        return self
class CurrentMemoryState(ArtifactContext):
    memory_state_id: NonEmptyStr; items: Annotated[tuple[MemoryItem,...],BeforeValidator(_tuple)]; content_hash: NonEmptyStr|None=None
class NextMemoryState(ArtifactContext):
    schema_version: Literal["p3.s26.next_memory_state.v2"]; memory_state_id: NonEmptyStr; source_memory_state_id: NonEmptyStr
    items: Annotated[tuple[MemoryItem,...],BeforeValidator(_tuple)]; created_count: NonNegativeInt; reinforced_count: NonNegativeInt
    promoted_count: NonNegativeInt; expired_count: NonNegativeInt; content_hash: NonEmptyStr

class LearningExperience(StrictModel):
    experience_id: NonEmptyStr; person_id: NonEmptyStr; experience_type: ExperienceTypeValue
    event_time: AwareDateTime; available_at: AwareDateTime; content_ref: NonEmptyStr; content_fingerprint: NonEmptyStr
    source_event_ids: StringTuple; evidence_refs: StringTuple; importance: Probability; confidence: Probability
    matured: bool; commitment_id: NonEmptyStr|None=None; lineage_id: NonEmptyStr
class PersonLearningTrajectoryBundle(ArtifactContext): items: Annotated[tuple[LearningExperience,...],BeforeValidator(_tuple)]

class BeliefStateRecord(StrictModel):
    person_id: NonEmptyStr; underlying_id: NonEmptyStr; proposition_id: NonEmptyStr; horizon: NonEmptyStr
    prior_value: SignedBelief; new_value: SignedBelief; delta: BeliefDelta; confidence: Probability; uncertainty: Probability
    changed_at: AwareDateTime; commitment_id: NonEmptyStr; evidence_refs: StringTuple; lineage_id: NonEmptyStr
    @model_validator(mode="after")
    def check_delta(self)->"BeliefStateRecord":
        if abs((self.new_value-self.prior_value)-self.delta)>1e-9: raise ValueError("delta mismatch")
        return self
class NextBeliefStatePanel(ArtifactContext): records: Annotated[tuple[BeliefStateRecord,...],BeforeValidator(_tuple)]

class RelationshipObservation(StrictModel):
    observation_id: NonEmptyStr; observer_person_id: NonEmptyStr; counterparty_person_id: NonEmptyStr
    relationship_type: NonEmptyStr; domain: NonEmptyStr; signal: Annotated[float,Field(ge=-1,le=1)]; reliability: Probability
    experience_type: NonEmptyStr; source_message_id: NonEmptyStr|None=None; observed_at: AwareDateTime
    effective_cycle: NonNegativeInt; evidence_refs: StringTuple; lineage_id: NonEmptyStr
class StateChangeSummary(StrictModel):
    change_id: NonEmptyStr; content_ref: NonEmptyStr; change_magnitude: Probability; source_event_ids: StringTuple
    evidence_refs: StringTuple; changed_at: AwareDateTime; lineage_id: NonEmptyStr
class NextPersonStateRecord(StrictModel):
    person_id: NonEmptyStr; relationship_observations: Annotated[tuple[RelationshipObservation,...],BeforeValidator(_tuple)]=()
    state_change_summary: StateChangeSummary|None=None
class ValidatedNextPersonStatePanel(ArtifactContext): records: Annotated[tuple[NextPersonStateRecord,...],BeforeValidator(_tuple)]

class SocialDeliveryRecord(StrictModel):
    message_id: NonEmptyStr; sender_person_id: NonEmptyStr; receiver_person_id: NonEmptyStr; status: DeliveryStatusValue
    created_cycle: NonNegativeInt; effective_cycle: NonNegativeInt; created_at: AwareDateTime; status_at: AwareDateTime
    causal_parent_id: NonEmptyStr|None=None; evidence_refs: StringTuple=(); lineage_id: NonEmptyStr
class SocialDeliveryPanel(ArtifactContext): records: Annotated[tuple[SocialDeliveryRecord,...],BeforeValidator(_tuple)]

class BeliefFeedbackRecord(StrictModel):
    feedback_id: NonEmptyStr; commitment_id: NonEmptyStr; commit_hash: NonEmptyStr|None=None
    observer_person_id: NonEmptyStr; counterparty_person_id: NonEmptyStr; relationship_type: NonEmptyStr; domain: NonEmptyStr
    outcome_alignment: Annotated[float,Field(ge=-1,le=1)]; reliability: Probability; status: FeedbackStatusValue
    matured_at: AwareDateTime; effective_cycle: NonNegativeInt; evidence_refs: StringTuple; lineage_id: NonEmptyStr
class ActiveBeliefFeedbackBundle(ArtifactContext): items: Annotated[tuple[BeliefFeedbackRecord,...],BeforeValidator(_tuple)]
class ActiveRetroPolicyPatch(StrictModel):
    status: RetroPatchStatusValue; patch_id: NonEmptyStr; change_type: NonEmptyStr; change_target: NonEmptyStr
    promoted_at: AwareDateTime; effective_cycle_id: NonNegativeInt; lineage_id: NonEmptyStr
    parameters: dict[NonEmptyStr,bool|int|float|str]

class MemoryTriggerEvent(StrictModel):
    event_id: NonEmptyStr; person_id: NonEmptyStr; memory_id: NonEmptyStr; source_event_id: NonEmptyStr
    causal_parent_id: NonEmptyStr|None=None; subject: NonEmptyStr; underlying_id: NonEmptyStr|None=None
    proposition_id: NonEmptyStr|None=None; created_at: AwareDateTime; available_at: AwareDateTime
    created_cycle: NonNegativeInt; target_cycle: NonNegativeInt; trigger_score: Probability; reason: TriggerReasonValue
    evidence_refs: StringTuple; lineage_id: NonEmptyStr
class MemoryTriggerEventPanel(ArtifactContext):
    schema_version: Literal["p3.s26.memory_trigger_event_panel.v2"]; records: Annotated[tuple[MemoryTriggerEvent,...],BeforeValidator(_tuple)]

class ToolDiscoveryEvent(StrictModel):
    event_id: NonEmptyStr; person_id: NonEmptyStr; tool_id: NonEmptyStr; source_request_id: NonEmptyStr; subject: NonEmptyStr
    underlying_id: NonEmptyStr|None=None; proposition_id: NonEmptyStr|None=None; discovered_at: AwareDateTime
    available_at: AwareDateTime; source_priority: Probability; content_hash: NonEmptyStr; evidence_refs: StringTuple; lineage_id: NonEmptyStr
class ToolDiscoveryEventPanel(ArtifactContext): records: Annotated[tuple[ToolDiscoveryEvent,...],BeforeValidator(_tuple)]
class SocialDeliveryEvent(StrictModel):
    event_id: NonEmptyStr; message_id: NonEmptyStr; sender_person_id: NonEmptyStr; receiver_person_id: NonEmptyStr
    status: DeliveryStatusValue; subject: NonEmptyStr; underlying_id: NonEmptyStr|None=None; proposition_id: NonEmptyStr|None=None
    occurred_at: AwareDateTime; available_at: AwareDateTime; effective_cycle: NonNegativeInt; source_priority: Probability
    causal_parent_id: NonEmptyStr|None=None; evidence_refs: StringTuple; lineage_id: NonEmptyStr
class SocialDeliveryEventPanel(ArtifactContext): records: Annotated[tuple[SocialDeliveryEvent,...],BeforeValidator(_tuple)]
class AttentionFollowupIntent(StrictModel):
    intent_id: NonEmptyStr; person_id: NonEmptyStr; subject: NonEmptyStr; underlying_id: NonEmptyStr|None=None
    proposition_id: NonEmptyStr|None=None; created_at: AwareDateTime; available_at: AwareDateTime; priority: Probability
    causal_parent_id: NonEmptyStr|None=None; evidence_refs: StringTuple; lineage_id: NonEmptyStr
class FinalizedAttentionFollowupIntentPanel(ArtifactContext): records: Annotated[tuple[AttentionFollowupIntent,...],BeforeValidator(_tuple)]

class Phase3RunSnapshot(ArtifactContext):
    snapshot_id: NonEmptyStr; next_cycle_id: NonNegativeInt; execution_mode: ExecutionModeValue
    foundation_manifest_ref: NonEmptyStr; config_manifest_ref: NonEmptyStr; prompt_manifest_ref: NonEmptyStr
    model_registry_ref: NonEmptyStr; provider_fingerprint_ref: NonEmptyStr; tool_registry_ref: NonEmptyStr
    entitlement_ref: NonEmptyStr; rag_index_ref: NonEmptyStr; graph_index_ref: NonEmptyStr; memory_index_ref: NonEmptyStr
    replay_cache_ref: NonEmptyStr; prior_commitment_ids: StringTuple=()
    @model_validator(mode="after")
    def exact_next(self)->"Phase3RunSnapshot":
        if self.next_cycle_id!=self.cycle_id+1: raise ValueError("next_cycle_id must equal cycle_id + 1")
        return self

class EndogenousStimulus(StrictModel):
    stimulus_id: NonEmptyStr; origin_type: StimulusOriginValue; source_event_id: NonEmptyStr; causal_parent_id: NonEmptyStr|None=None
    target_person_id: NonEmptyStr; subject: NonEmptyStr; underlying_id: NonEmptyStr|None=None; proposition_id: NonEmptyStr|None=None
    created_cycle: NonNegativeInt; target_cycle: NonNegativeInt; created_at: AwareDateTime; available_at: AwareDateTime
    expires_after_cycle: NonNegativeInt; priority: Probability; evidence_refs: StringTuple; source_lineage_ids: StringTuple; content_hash: NonEmptyStr
class NextCycleEndogenousStimulusQueue(ArtifactContext):
    schema_version: Literal["p3.s26.next_cycle_endogenous_stimulus_queue.v2"]; queue_id: NonEmptyStr
    source_cycle_id: NonNegativeInt; target_cycle_id: NonNegativeInt
    stimuli: Annotated[tuple[EndogenousStimulus,...],BeforeValidator(_tuple)]; content_hash: NonEmptyStr

class BeliefCommitment(StrictModel):
    commitment_id: NonEmptyStr; person_id: NonEmptyStr; underlying_id: NonEmptyStr; proposition_id: NonEmptyStr; horizon: NonEmptyStr
    belief_value: SignedBelief; confidence: Probability; uncertainty: Probability; committed_at: AwareDateTime; matures_at: AwareDateTime
    commit_hash: NonEmptyStr; evidence_refs: StringTuple; lineage_id: NonEmptyStr; status: CommitmentStatusValue
    @model_validator(mode="after")
    def valid_time(self)->"BeliefCommitment":
        if self.matures_at<=self.committed_at: raise ValueError("matures_at must follow committed_at")
        return self
class BeliefOutcomeCommitmentLog(ArtifactContext):
    commitments: Annotated[tuple[BeliefCommitment,...],BeforeValidator(_tuple)]; prior_commitment_ids: StringTuple=()
    append_only: Literal[True]; content_hash: NonEmptyStr

class GraphNode(StrictModel): person_id: NonEmptyStr; role_family: NonEmptyStr; active: bool=True
class RelationshipEdge(StrictModel):
    edge_id: NonEmptyStr; source_person_id: NonEmptyStr; target_person_id: NonEmptyStr; relationship_type: NonEmptyStr
    trust_by_domain: dict[NonEmptyStr,Probability]; general_trust: Probability; interaction_count: NonNegativeInt=0
    last_observed_at: AwareDateTime|None=None; created_at: AwareDateTime; valid_from_cycle: NonNegativeInt; lineage_ids: StringTuple
class RelationshipDecisionRecord(StrictModel):
    relationship_change_id: NonEmptyStr; decision: Literal["APPLIED","REJECTED"]; reason_codes: StringTuple; edge_id: NonEmptyStr|None=None
class TopologyMetrics(StrictModel):
    node_count: NonNegativeInt; edge_count: NonNegativeInt; min_degree: NonNegativeInt; max_degree: NonNegativeInt
    connected_components: NonNegativeInt; bridge_edges_between_role_families: NonNegativeInt; max_hub_share: Probability
class NextSocialGraph(ArtifactContext):
    schema_version: Literal["p3.s25.next_social_graph.v2"]; directed: Literal[True]=True
    nodes: Annotated[tuple[GraphNode,...],BeforeValidator(_tuple)]; records: Annotated[tuple[RelationshipEdge,...],BeforeValidator(_tuple)]
    applied_changes: Annotated[tuple[RelationshipDecisionRecord,...],BeforeValidator(_tuple)]
    rejected_changes: Annotated[tuple[RelationshipDecisionRecord,...],BeforeValidator(_tuple)]
    topology_metrics: TopologyMetrics; content_hash: NonEmptyStr

class ArtifactManifestEntry(StrictModel):
    artifact_id: NonEmptyStr; artifact_name: NonEmptyStr; schema_id: NonEmptyStr; schema_version: NonEmptyStr
    content_hash: NonEmptyStr; row_count: NonNegativeInt; grain: NonEmptyStr; producer_module_id: NonEmptyStr
    lineage_id: NonEmptyStr; status: ArtifactStatusValue
class CycleStateSnapshotOut(StrictModel):
    schema_version: Literal["p3.s26.cycle_state_snapshot_out.v2"]; snapshot_id: NonEmptyStr; run_id: NonEmptyStr
    source_cycle_id: NonNegativeInt; target_cycle_id: NonNegativeInt; as_of_time: AwareDateTime; available_from_cycle: NonNegativeInt
    lineage_id: NonEmptyStr; person_state_ref: NonEmptyStr; belief_state_ref: NonEmptyStr; memory_state_ref: NonEmptyStr
    social_graph_ref: NonEmptyStr; endogenous_stimulus_queue_ref: NonEmptyStr; belief_commitment_log_ref: NonEmptyStr
    run_snapshot_ref: NonEmptyStr; foundation_manifest_ref: NonEmptyStr; config_manifest_ref: NonEmptyStr
    prompt_manifest_ref: NonEmptyStr; model_registry_ref: NonEmptyStr; provider_fingerprint_ref: NonEmptyStr
    tool_registry_ref: NonEmptyStr; entitlement_ref: NonEmptyStr; rag_index_ref: NonEmptyStr; graph_index_ref: NonEmptyStr
    memory_index_ref: NonEmptyStr; replay_cache_ref: NonEmptyStr
    artifact_manifest: Annotated[tuple[ArtifactManifestEntry,...],BeforeValidator(_tuple)]; content_hash: NonEmptyStr
