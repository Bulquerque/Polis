from __future__ import annotations
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
ID = '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$'
SHA = '^[0-9a-f]{64}$'

def utc(v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError('datetime must be timezone-aware')
    return v.astimezone(UTC)

class C(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, validate_default=True)

class Status(StrEnum):
    READY = 'READY'
    READY_EMPTY = 'READY_EMPTY'
    DEGRADED = 'DEGRADED'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'

class TriggerType(StrEnum):
    STIMULUS = 'STIMULUS'
    HEARTBEAT = 'HEARTBEAT'

class SourceType(StrEnum):
    MEMORY = 'MEMORY'
    DOCUMENT = 'DOCUMENT'
    GRAPH = 'GRAPH'
    EXPERIENCE = 'EXPERIENCE'

class RetrievalStatus(StrEnum):
    READY = 'READY'
    READY_EMPTY = 'READY_EMPTY'
    DEGRADED = 'DEGRADED'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'

class ExperienceStatus(StrEnum):
    SUCCESSFUL = 'SUCCESSFUL'
    FAILED = 'FAILED'
    MATURED_NEUTRAL = 'MATURED_NEUTRAL'
    IMMATURE = 'IMMATURE'
    UNRESOLVED = 'UNRESOLVED'

class CutoffRisk(StrEnum):
    PASS = 'PASS'
    WARN = 'WARN'
    BLOCK = 'BLOCK'

class RunSnapshot(C):
    schema_version: Literal['phase3_run_snapshot.s20.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    snapshot_id: StrictStr = Field(pattern=ID)
    as_of: datetime
    execution_mode: StrictStr
    model_id: StrictStr
    model_context_window: StrictInt = Field(gt=0)
    content_hash: StrictStr = Field(pattern=SHA)
    _a = field_validator('as_of')(utc)

class ScheduleStep(C):
    schedule_step_id: StrictStr = Field(pattern=ID)
    person_id: StrictStr = Field(pattern=ID)
    trigger_type: TriggerType
    activation_id: StrictStr | None = None
    stimulus_id: StrictStr | None = None
    heartbeat_period: StrictStr | None = None
    priority: StrictInt
    activation_score: StrictFloat | None = None
    scheduled_at: datetime
    seed: StrictInt
    source_lineage_ids: tuple[StrictStr, ...]
    _s = field_validator('scheduled_at')(utc)

class CognitiveSchedule(C):
    schema_version: Literal['cognitive_cycle_schedule.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    as_of: datetime
    records: tuple[ScheduleStep, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: Status
    _a = field_validator('as_of')(utc)

class Stimulus(C):
    stimulus_id: StrictStr = Field(pattern=ID)
    subject: StrictStr
    available_at: datetime
    event_time: datetime
    selected_underlying_id: StrictStr | None = None
    proposition_id: StrictStr | None = None
    horizon: StrictStr | None = None
    evidence_refs: tuple[StrictStr, ...]
    lineage_ids: tuple[StrictStr, ...]
    salience: StrictFloat = Field(ge=0, le=1)
    priority: StrictInt
    _aa = field_validator('available_at', 'event_time')(utc)

class StimulusPanel(C):
    schema_version: Literal['stimulus_panel.v2']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    as_of: datetime
    records: tuple[Stimulus, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: Status
    _a = field_validator('as_of')(utc)

class Activation(C):
    activation_id: StrictStr = Field(pattern=ID)
    person_id: StrictStr = Field(pattern=ID)
    stimulus_id: StrictStr | None = None
    trigger_type: TriggerType
    activation_score: StrictFloat | None = None
    seed: StrictInt
    source_lineage_ids: tuple[StrictStr, ...]

class ActivationPanel(C):
    schema_version: Literal['activation_panel.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    records: tuple[Activation, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: Status

class PersonState(C):
    person_id: StrictStr = Field(pattern=ID)
    role: StrictStr
    objective: StrictStr
    current_attention: StrictFloat = Field(ge=0, le=1)
    enabled: StrictBool = True
    available_at: datetime
    lineage_id: StrictStr = Field(pattern=ID)
    _a = field_validator('available_at')(utc)

class PersonStatePanel(C):
    schema_version: Literal['current_person_state_panel.s20.v1']
    records: tuple[PersonState, ...]
    content_hash: StrictStr = Field(pattern=SHA)

class Belief(C):
    person_id: StrictStr = Field(pattern=ID)
    proposition_id: StrictStr = Field(pattern=ID)
    horizon: StrictStr = Field(pattern=ID)
    value: StrictFloat = Field(ge=0, le=1)
    confidence: StrictFloat = Field(ge=0, le=1)
    available_at: datetime
    evidence_refs: tuple[StrictStr, ...] = ()
    _a = field_validator('available_at')(utc)

class BeliefPanel(C):
    schema_version: Literal['current_belief_state_panel.s20.v1']
    records: tuple[Belief, ...]
    content_hash: StrictStr = Field(pattern=SHA)

class RetrievalQuery(C):
    query_id: StrictStr = Field(pattern=ID)
    schedule_step_id: StrictStr = Field(pattern=ID)
    person_id: StrictStr = Field(pattern=ID)
    trigger_type: TriggerType
    activation_id: StrictStr | None = None
    stimulus_id: StrictStr | None = None
    query_text: StrictStr = Field(min_length=1, max_length=12000)
    underlying_id: StrictStr | None = None
    proposition_id: StrictStr | None = None
    horizon: StrictStr | None = None
    as_of: datetime
    memory_scope: Literal['PERSON_ONLY']
    knowledge_scope: Literal['PIT_AUTHORIZED']
    source_lineage_ids: tuple[StrictStr, ...]
    _a = field_validator('as_of')(utc)

class QueryPanel(C):
    schema_version: Literal['person_retrieval_query_panel.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    as_of: datetime
    records: tuple[RetrievalQuery, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: Status
    _a = field_validator('as_of')(utc)

class IndexedItem(C):
    item_id: StrictStr = Field(pattern=ID)
    source_id: StrictStr = Field(pattern=ID)
    person_id: StrictStr | None = None
    title: StrictStr = ''
    text: StrictStr = Field(min_length=1)
    available_at: datetime
    event_time: datetime | None = None
    source_quality: StrictFloat = Field(ge=0, le=1)
    importance: StrictFloat = Field(ge=0, le=1)
    semantic_score: StrictFloat = Field(default=0, ge=0, le=1)
    keyword_score: StrictFloat = Field(default=0, ge=0, le=1)
    content_hash: StrictStr = Field(pattern=SHA)
    evidence_refs: tuple[StrictStr, ...]
    lineage_id: StrictStr = Field(pattern=ID)
    experience_status: ExperienceStatus | None = None
    commitment_id: StrictStr | None = None
    _a = field_validator('available_at')(utc)

    @field_validator('event_time')
    @classmethod
    def e(cls, v):
        return utc(v) if v else None

class IndexManifest(C):
    schema_version: StrictStr
    index_id: StrictStr = Field(pattern=ID)
    records: tuple[IndexedItem, ...]
    content_hash: StrictStr = Field(pattern=SHA)

class MemoryPolicy(C):
    schema_version: Literal['memory_access_policy.s20.v1']
    person_isolation_required: Literal[True]
    retro_memory_forbidden: Literal[True]
    max_items_per_query: StrictInt = Field(gt=0, le=100)

class HybridWeights(C):
    semantic: StrictFloat = Field(ge=0, le=1)
    keyword: StrictFloat = Field(ge=0, le=1)
    recency: StrictFloat = Field(ge=0, le=1)
    importance: StrictFloat = Field(ge=0, le=1)
    source_quality: StrictFloat = Field(ge=0, le=1)

class RetrievalConfig(C):
    schema_version: Literal['retrieval_config.s20.v1'] = 'retrieval_config.s20.v1'
    hybrid_weights: HybridWeights
    top_k_raw: StrictInt = Field(gt=0, le=500)
    top_k_final: StrictInt = Field(gt=0, le=200)
    memory_top_k: StrictInt = Field(default=10, gt=0, le=100)
    document_top_k: StrictInt = Field(default=20, gt=0, le=100)
    graph_top_k: StrictInt = Field(default=10, gt=0, le=100)
    experience_top_k: StrictInt = Field(default=5, gt=0, le=100)
    minimum_evidence_items: StrictInt = Field(default=2, ge=0)
    max_items_per_source: StrictInt = Field(default=6, gt=0)
    reranker_required_when_connected: StrictBool = True
    provider_unavailable_policy: StrictStr = 'material_failure_or_declared_deterministic_fallback'
    person_memory_partition_required: Literal[True] = True

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, v):
        if isinstance(v, dict) and 'hybrid_weights' not in v:
            keys = (
                'semantic_weight',
                'keyword_weight',
                'recency_weight',
                'importance_weight',
                'source_quality_weight',
            )
            if all((k in v for k in keys)):
                v = dict(v)
                v['hybrid_weights'] = {
                    'semantic': v.pop('semantic_weight'),
                    'keyword': v.pop('keyword_weight'),
                    'recency': v.pop('recency_weight'),
                    'importance': v.pop('importance_weight'),
                    'source_quality': v.pop('source_quality_weight'),
                }
                v['top_k_raw'] = max(
                    v.get('memory_top_k', 5)
                    + v.get('document_top_k', 8),
                    v.get('final_top_k', 10),
                )
                v['top_k_final'] = v.pop('final_top_k', 10)
                v.pop('external_reranker_enabled', None)
        return v

    @model_validator(mode='after')
    def weights(self):
        total = sum(
            (
                self.hybrid_weights.semantic,
                self.hybrid_weights.keyword,
                self.hybrid_weights.recency,
                self.hybrid_weights.importance,
                self.hybrid_weights.source_quality,
            )
        )
        if abs(total - 1) > 1e-09:
            raise ValueError('retrieval weights must sum to 1')
        return self

    @property
    def final_top_k(self):
        return self.top_k_final

    @property
    def semantic_weight(self):
        return self.hybrid_weights.semantic

    @property
    def keyword_weight(self):
        return self.hybrid_weights.keyword

    @property
    def recency_weight(self):
        return self.hybrid_weights.recency

    @property
    def importance_weight(self):
        return self.hybrid_weights.importance

    @property
    def source_quality_weight(self):
        return self.hybrid_weights.source_quality

class GraphConfig(C):
    schema_version: Literal['graph_config.s20.v1'] = 'graph_config.s20.v1'
    max_query_hops: StrictInt = Field(ge=0, le=5)
    edge_requires_evidence: Literal[True]
    temporal_edges_required: Literal[True] = True
    orphan_edge_policy: Literal['FAIL', 'fail']
    entity_resolution_version: StrictStr = 'v1'

class GraphEdge(C):
    edge_id: StrictStr = Field(pattern=ID)
    source_node_id: StrictStr = Field(pattern=ID)
    target_node_id: StrictStr = Field(pattern=ID)
    available_at: datetime
    evidence_refs: tuple[StrictStr, ...]
    text: StrictStr
    weight: StrictFloat = Field(ge=0, le=1)
    lineage_id: StrictStr = Field(pattern=ID)
    _a = field_validator('available_at')(utc)

class GraphArtifact(C):
    schema_version: Literal['graph_rag_artifact.s20.v1']
    graph_id: StrictStr = Field(pattern=ID)
    edges: tuple[GraphEdge, ...]
    content_hash: StrictStr = Field(pattern=SHA)

class RetrievedEvidence(C):
    query_text: StrictStr = Field(min_length=1, max_length=12000)
    evidence_id: StrictStr = Field(pattern=ID)
    query_id: StrictStr = Field(pattern=ID)
    person_id: StrictStr = Field(pattern=ID)
    source_type: SourceType
    source_id: StrictStr = Field(pattern=ID)
    text: StrictStr
    available_at: datetime
    event_time: datetime | None = None
    content_hash: StrictStr = Field(pattern=SHA)
    semantic_score: StrictFloat | None = Field(default=None, ge=0, le=1)
    keyword_score: StrictFloat | None = Field(default=None, ge=0, le=1)
    recency_score: StrictFloat | None = Field(default=None, ge=0, le=1)
    importance_score: StrictFloat | None = Field(default=None, ge=0, le=1)
    source_quality_score: StrictFloat | None = Field(default=None, ge=0, le=1)
    reranker_score: StrictFloat | None = Field(default=None, ge=0, le=1)
    rank_before: StrictInt = Field(ge=1)
    rank_after: StrictInt | None = Field(default=None, ge=1)
    evidence_refs: tuple[StrictStr, ...]
    lineage_ids: tuple[StrictStr, ...]
    experience_status: ExperienceStatus | None = None
    commitment_id: StrictStr | None = None
    _a = field_validator('available_at')(utc)

    @field_validator('event_time')
    @classmethod
    def e(cls, v):
        return utc(v) if v else None

class RetrievalBundle(C):
    schema_version: StrictStr
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    as_of: datetime
    records: tuple[RetrievedEvidence, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: RetrievalStatus
    warnings: tuple[StrictStr, ...] = ()
    ranking_policy_id: StrictStr | None = None
    ranking_provider_ref: StrictStr | None = None
    score_semantics: StrictStr | None = None
    _a = field_validator('as_of')(utc)

class EvidenceMapEntry(C):
    evidence_id: StrictStr = Field(pattern=ID)
    query_id: StrictStr = Field(pattern=ID)
    source_type: SourceType
    source_id: StrictStr = Field(pattern=ID)
    content_hash: StrictStr = Field(pattern=SHA)
    available_at: datetime
    evidence_refs: tuple[StrictStr, ...]
    lineage_ids: tuple[StrictStr, ...]
    _a = field_validator('available_at')(utc)

class EvidenceMap(C):
    schema_version: Literal['retrieval_evidence_map.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    records: tuple[EvidenceMapEntry, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: RetrievalStatus

class SocialEdge(C):
    edge_id: StrictStr = Field(pattern=ID)
    source_person_id: StrictStr = Field(pattern=ID)
    target_person_id: StrictStr = Field(pattern=ID)
    trust: StrictFloat = Field(ge=0, le=1)
    available_at: datetime
    _a = field_validator('available_at')(utc)

class SocialGraph(C):
    schema_version: Literal['current_social_graph.s20.v1']
    records: tuple[SocialEdge, ...]
    content_hash: StrictStr = Field(pattern=SHA)

class Entitlement(C):
    person_id: StrictStr = Field(pattern=ID)
    tool_ids: tuple[StrictStr, ...]

class EntitlementPanel(C):
    schema_version: Literal['person_tool_entitlement_panel.s20.v1']
    records: tuple[Entitlement, ...]
    content_hash: StrictStr = Field(pattern=SHA)

class RetroPatch(C):
    schema_version: Literal['active_retro_policy_patch.s20.v1']
    status: Literal['NO_PATCH', 'ACTIVE']
    patch_id: StrictStr | None = None
    allowed_context_notes: tuple[StrictStr, ...] = ()

class ContextSection(C):
    section_id: StrictStr = Field(pattern=ID)
    section_type: StrictStr
    priority: StrictInt
    mandatory: StrictBool
    text: StrictStr
    item_ids: tuple[StrictStr, ...]
    source_refs: tuple[StrictStr, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    estimated_tokens: StrictInt = Field(ge=0)

class PersonContext(C):
    context_id: StrictStr = Field(pattern=ID)
    schedule_step_id: StrictStr = Field(pattern=ID)
    person_id: StrictStr = Field(pattern=ID)
    trigger_type: TriggerType
    activation_id: StrictStr | None = None
    stimulus_id: StrictStr | None = None
    as_of: datetime
    sections: tuple[ContextSection, ...]
    entitled_tool_ids: tuple[StrictStr, ...]
    source_lineage_ids: tuple[StrictStr, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    _a = field_validator('as_of')(utc)

class ContextBundle(C):
    schema_version: Literal['person_context_bundle.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    records: tuple[PersonContext, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: Status

class BudgetConfig(C):
    schema_version: Literal['context_budget_config.s20.v1'] = 'context_budget_config.s20.v1'
    max_input_tokens: StrictInt = Field(gt=0)
    reserved_output_tokens: StrictInt = Field(default=4000, ge=0)
    safety_margin_tokens: StrictInt = Field(default=1000, ge=0)
    minimum_evidence_items: StrictInt = Field(default=2, ge=0)
    tokenizer_mode: Literal['DETERMINISTIC_REGEX', 'NVIDIA_NIM'] = 'DETERMINISTIC_REGEX'
    removable_section_order: tuple[StrictStr, ...]

    @model_validator(mode='before')
    @classmethod
    def normalize(cls, v):
        if isinstance(v, dict) and 'max_tokens_per_person_cycle' in v:
            v = dict(v)
            v['max_input_tokens'] = v.pop('max_tokens_per_person_cycle')
            v['minimum_evidence_items'] = v.pop('min_evidence_items', 2)
            order = v.pop('priority_order', [])
            v.pop('truncation', None)
            v['removable_section_order'] = (
                (
                    'ACTIVE_POLICY_PATCH',
                    'SOCIAL_CONTEXT',
                    'RETRIEVED_EVIDENCE',
                    'PRIOR_BELIEFS',
                )
                if order
                else (
                    'ACTIVE_POLICY_PATCH',
                    'SOCIAL_CONTEXT',
                    'RETRIEVED_EVIDENCE',
                )
            )
        return v

class CutoffReport(C):
    schema_version: Literal['model_knowledge_cutoff_report.s20.v1']
    risk: CutoffRisk
    model_id: StrictStr
    model_context_window: StrictInt = Field(default=32768, gt=0)
    report_id: StrictStr = Field(pattern=ID)
    reasons: tuple[StrictStr, ...] = ()

class BudgetReport(C):
    context_id: StrictStr = Field(pattern=ID)
    model_id: StrictStr
    tokenizer_ref: StrictStr
    original_tokens: StrictInt = Field(ge=0)
    effective_budget: StrictInt = Field(ge=0)
    final_tokens: StrictInt = Field(ge=0)
    removed_section_ids: tuple[StrictStr, ...]
    removed_item_ids: tuple[StrictStr, ...]
    removed_section_reasons: dict[StrictStr, StrictStr] = Field(default_factory=dict)
    minimum_evidence_status: StrictStr
    cutoff_risk: CutoffRisk

class ValidatedContext(C):
    context: PersonContext
    budget_report: BudgetReport

class ValidatedContextBundle(C):
    schema_version: Literal['validated_person_context_bundle.v1']
    run_id: StrictStr = Field(pattern=ID)
    cycle_id: StrictStr = Field(pattern=ID)
    records: tuple[ValidatedContext, ...]
    content_hash: StrictStr = Field(pattern=SHA)
    status: Status
    warnings: tuple[StrictStr, ...] = ()

class ProviderRegistry(C):
    schema_version: Literal['provider_adapter_registry.s20.v1']
    qualified_provider_ids: tuple[StrictStr, ...] = ()

class ContextLearningConfig(C):
    schema_version: Literal['context_learning_config.s20.v1'] = 'context_learning_config.s20.v1'
    person_experience_only: Literal[True] = True
    retro_experiment_memory_forbidden_for_people: Literal[True] = True
    top_k_person_trajectories: StrictInt = Field(default=5, gt=0)
    include_promoted_and_failed_person_experiences: StrictBool = True
    holdout_excluded: Literal[True] = True
    include_matured_success: StrictBool = True
    include_matured_failure: StrictBool = True
    include_immature: StrictBool = False

class S20Result(C):
    person_retrieval_query_panel: QueryPanel
    raw_retrieved_knowledge_bundle: RetrievalBundle
    graph_retrieval_bundle: RetrievalBundle
    person_learning_trajectory_bundle: RetrievalBundle
    retrieved_knowledge_bundle: RetrievalBundle
    retrieval_evidence_map: EvidenceMap
    person_context_bundle: ContextBundle
    validated_person_context_bundle: ValidatedContextBundle
