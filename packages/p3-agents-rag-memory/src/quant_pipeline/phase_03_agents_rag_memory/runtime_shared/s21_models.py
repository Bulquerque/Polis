from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "p3.s21.v1"
FORBIDDEN_FIELDS = frozenset(
    {
        "future_return",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
        "api_key",
        "authorization",
        "access_token",
        "refresh_token",
        "password",
        "cookie",
    }
)


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
NonEmptyStr = Annotated[str, Field(min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        str_strip_whitespace=True,
    )


class ArtifactStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    EMPTY_VALID = "EMPTY_VALID"


class ExecutionMode(StrEnum):
    WARMUP_REPLAY = "WARMUP_REPLAY"
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    DRY_RUN = "DRY_RUN"


class CognitionStage(StrEnum):
    INITIAL = "INITIAL"
    CONTINUATION = "CONTINUATION"


class ToolPathStatus(StrEnum):
    NO_TOOL = "NO_TOOL"
    TOOL_REQUESTED = "TOOL_REQUESTED"
    TOOL_AUTHORIZED = "TOOL_AUTHORIZED"
    TOOL_REJECTED = "TOOL_REJECTED"
    TOOL_EXECUTING = "TOOL_EXECUTING"
    TOOL_SUCCEEDED = "TOOL_SUCCEEDED"
    TOOL_FAILED = "TOOL_FAILED"
    COGNITION_RESUMED = "COGNITION_RESUMED"
    COMPLETED = "COMPLETED"


class RequestValidationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED_SCHEMA = "REJECTED_SCHEMA"
    REJECTED_TOOL_UNKNOWN = "REJECTED_TOOL_UNKNOWN"
    REJECTED_OPERATION = "REJECTED_OPERATION"
    REJECTED_ENTITLEMENT = "REJECTED_ENTITLEMENT"
    REJECTED_BUDGET = "REJECTED_BUDGET"
    REJECTED_TEMPORAL = "REJECTED_TEMPORAL"
    REJECTED_CREDENTIAL = "REJECTED_CREDENTIAL"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"


class ToolExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    FAILED_RATE_LIMIT = "FAILED_RATE_LIMIT"
    FAILED_AUTHENTICATION = "FAILED_AUTHENTICATION"
    FAILED_PROVIDER = "FAILED_PROVIDER"
    FAILED_SCHEMA = "FAILED_SCHEMA"
    REJECTED_TEMPORAL = "REJECTED_TEMPORAL"
    REJECTED_AUTHORIZATION = "REJECTED_AUTHORIZATION"


class ToolResultValidationStatus(StrEnum):
    VALID = "VALID"
    FAILURE_PRESERVED = "FAILURE_PRESERVED"
    INVALID_LINKAGE = "INVALID_LINKAGE"
    INVALID_TEMPORAL = "INVALID_TEMPORAL"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


class IntentStatus(StrEnum):
    PRELIMINARY = "PRELIMINARY"
    FINALIZED = "FINALIZED"


class BeliefValueType(StrEnum):
    DIRECTIONAL_SCORE = "DIRECTIONAL_SCORE"
    VOLATILITY_LEVEL = "VOLATILITY_LEVEL"
    REGIME_PROBABILITIES = "REGIME_PROBABILITIES"


class LineageRecord(StrictModel):
    lineage_id: NonEmptyStr
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_hashes: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    producer_module_id: NonEmptyStr


RecordT = TypeVar("RecordT", bound=StrictModel)


class ArtifactPanel(StrictModel, Generic[RecordT]):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: ArtifactStatus = ArtifactStatus.READY
    records: tuple[RecordT, ...]
    lineage: LineageRecord
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_empty_status(self) -> "ArtifactPanel[RecordT]":
        if not self.records and self.status not in {
            ArtifactStatus.EMPTY_VALID,
            ArtifactStatus.DEGRADED,
            ArtifactStatus.FAILED,
        }:
            raise ValueError("empty panels must declare EMPTY_VALID, DEGRADED, or FAILED")
        return self


class EvidenceRef(StrictModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    available_at: UTCDateTime
    content_hash: NonEmptyStr
    source_quality: Probability = 1.0


class ClaimRecord(StrictModel):
    claim_id: NonEmptyStr
    summary: NonEmptyStr
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    tool_result_refs: tuple[NonEmptyStr, ...] = ()


class PersonContextRecord(StrictModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    activation_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: UTCDateTime
    seed: NonNegativeInt
    personality_summary: NonEmptyStr
    current_belief_summary: str = ""
    prompt_context: NonEmptyStr
    retrieved_evidence_refs: tuple[NonEmptyStr, ...] = ()
    allowed_tool_ids: tuple[NonEmptyStr, ...] = ()
    tool_budget: NonNegativeInt = 0
    context_token_count: NonNegativeInt
    context_token_limit: PositiveInt
    lineage: LineageRecord

    @model_validator(mode="after")
    def validate_budget(self) -> "PersonContextRecord":
        if self.context_token_count > self.context_token_limit:
            raise ValueError("context exceeds token budget")
        return self


class ValidatedPersonContextBundle(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: ArtifactStatus = ArtifactStatus.READY
    items: tuple[PersonContextRecord, ...]
    lineage: LineageRecord


class ProviderModelConfig(StrictModel):
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    enabled: bool = True
    supports_structured_output: bool
    supports_seed: bool = False
    max_context_tokens: PositiveInt
    max_output_tokens: PositiveInt
    knowledge_cutoff: UTCDateTime | None = None
    release_date: UTCDateTime | None = None
    priority: NonNegativeInt = 0


class ToolProviderConfig(StrictModel):
    provider_id: NonEmptyStr
    enabled: bool = True
    max_concurrency: PositiveInt = 4


class ProviderAdapterRegistryConfig(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    providers: tuple[ProviderModelConfig, ...]
    tool_providers: tuple[ToolProviderConfig, ...] = ()
    selected_provider_id: NonEmptyStr
    selected_model_id: NonEmptyStr

    def selected(self) -> ProviderModelConfig:
        for provider in self.providers:
            if (
                provider.provider_id == self.selected_provider_id
                and provider.model_id == self.selected_model_id
            ):
                if not provider.enabled:
                    raise ValueError("selected provider is disabled")
                return provider
        raise ValueError("selected provider/model is not registered")


class CognitionConfig(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    temperature: Annotated[float, Field(ge=0.0, le=0.3)] = 0.1
    structured_output: Literal[True] = True
    max_tool_calls_per_cycle: Annotated[int, Field(ge=0, le=5)] = 3
    max_repair_attempts: Annotated[int, Field(ge=0, le=1)] = 1
    no_trade_authority: Literal[True] = True
    initial_prompt_id: NonEmptyStr
    initial_prompt_version: NonEmptyStr
    continuation_prompt_id: NonEmptyStr
    continuation_prompt_version: NonEmptyStr


class ToolOperationEntitlement(StrictModel):
    operation_id: NonEmptyStr
    arguments_schema: dict[str, JsonValue]
    result_schema: dict[str, JsonValue]
    read_only: bool = True
    point_in_time_safe: bool = True


class PersonToolEntitlementRecord(StrictModel):
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    provider_id: NonEmptyStr
    credential_handle: NonEmptyStr | None = None
    budget_calls_per_cycle: NonNegativeInt
    operations: tuple[ToolOperationEntitlement, ...]
    entitlement_version: NonEmptyStr


class PersonToolEntitlementPanel(ArtifactPanel[PersonToolEntitlementRecord]):
    pass


class MCPGatewayPolicy(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    policy_version: NonEmptyStr
    pit_required: Literal[True] = True
    audit_required: Literal[True] = True
    cache_mode: Literal["frozen_in_backtest", "live", "replay_only"]
    cognition_default_calls_per_person_cycle: Annotated[int, Field(ge=0, le=5)] = 3
    hard_limit_calls_per_person_cycle: Annotated[int, Field(ge=0, le=5)] = 5
    credential_policy: Literal["handle_only"] = "handle_only"
    timeout_seconds: Annotated[float, Field(gt=0.0, le=120.0)] = 30.0
    max_retry_attempts: Annotated[int, Field(ge=0, le=3)] = 1
    retry_backoff_seconds: Annotated[float, Field(ge=0.0, le=10.0)] = 0.1
    provider_failure_policy: Literal["material_no_fake_success"] = (
        "material_no_fake_success"
    )


class ToolCallAuditContract(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    contract_version: NonEmptyStr
    required_fields: tuple[NonEmptyStr, ...]
    redact_fields: tuple[NonEmptyStr, ...]


class Phase3RunSnapshot(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: UTCDateTime
    execution_mode: ExecutionMode
    configuration_hash: NonEmptyStr


class RetrievalEvidenceMap(ArtifactPanel[EvidenceRef]):
    pass


class AgentReadingRecord(StrictModel):
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    stage: CognitionStage
    summary: NonEmptyStr
    claims: tuple[ClaimRecord, ...]
    confidence: Probability
    uncertainty: Probability
    as_of: UTCDateTime
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    prompt_id: NonEmptyStr
    prompt_version: NonEmptyStr
    response_hash: NonEmptyStr


class RawBeliefProposalRecord(StrictModel):
    belief_proposal_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    value_type: BeliefValueType
    value_payload: dict[str, JsonValue]
    strength: Probability
    confidence: Probability
    uncertainty: Probability
    supporting_evidence_refs: tuple[NonEmptyStr, ...] = ()
    opposing_evidence_refs: tuple[NonEmptyStr, ...] = ()
    generated_at: UTCDateTime
    as_of: UTCDateTime


class SocialIntentRecord(StrictModel):
    intent_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    recipient_person_id: NonEmptyStr | None = None
    message_type: NonEmptyStr
    summary: NonEmptyStr
    claim_refs: tuple[NonEmptyStr, ...] = ()
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    requested_action: str | None = None
    status: IntentStatus


class AttentionFollowupIntentRecord(StrictModel):
    intent_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    topic_id: NonEmptyStr
    priority: Probability
    reason: NonEmptyStr
    evidence_refs: tuple[NonEmptyStr, ...] = ()


class ToolCallRequestRecord(StrictModel):
    tool_call_request_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    arguments: dict[str, JsonValue]
    reason: NonEmptyStr
    expected_information_gain: Probability
    requested_at: UTCDateTime
    as_of: UTCDateTime
    credential_handle: NonEmptyStr | None = None
    idempotency_key: NonEmptyStr


class ValidatedToolCallRequestRecord(StrictModel):
    request: ToolCallRequestRecord
    validation_status: RequestValidationStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()
    provider_id: NonEmptyStr | None = None
    entitlement_version: NonEmptyStr | None = None
    arguments_schema: dict[str, JsonValue] | None = None
    result_schema: dict[str, JsonValue] | None = None
    read_only: bool | None = None
    point_in_time_safe: bool | None = None


class ToolErrorRecord(StrictModel):
    code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool = False


class RawToolResultRecord(StrictModel):
    tool_call_request_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    execution_id: NonEmptyStr
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    provider_id: NonEmptyStr
    status: ToolExecutionStatus
    started_at: UTCDateTime
    finished_at: UTCDateTime
    available_at: UTCDateTime | None = None
    latency_ms: NonNegativeFloat
    cost_units: NonNegativeFloat
    canonical_payload: dict[str, JsonValue] | None = None
    raw_payload_ref: str | None = None
    response_hash: str | None = None
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    error: ToolErrorRecord | None = None
    result_schema: dict[str, JsonValue] | None = None


class ToolCallAuditRecord(StrictModel):
    audit_id: NonEmptyStr
    tool_call_request_id: NonEmptyStr
    execution_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    provider_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    status: ToolExecutionStatus
    started_at: UTCDateTime
    finished_at: UTCDateTime
    latency_ms: NonNegativeFloat
    cost_units: NonNegativeFloat
    retry_count: NonNegativeInt
    request_hash: NonEmptyStr
    response_hash: str | None = None
    credential_handle_used: bool
    arguments_redacted: Literal[True] = True
    previous_audit_hash: str | None = None
    audit_hash: str | None = None


class ToolDiscoveryEventRecord(StrictModel):
    event_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    provider_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    discovered_at: UTCDateTime
    status: Literal["DISCOVERED", "UNCHANGED"]


class ValidatedToolResultRecord(StrictModel):
    raw_result: RawToolResultRecord
    validation_status: ToolResultValidationStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()
    validated_payload: dict[str, JsonValue] | None = None
    untrusted_content: bool = True


class InitialAgentReadingPanel(ArtifactPanel[AgentReadingRecord]):
    pass


class AgentReadingPanel(ArtifactPanel[AgentReadingRecord]):
    pass


class PreliminaryBeliefProposalPanel(ArtifactPanel[RawBeliefProposalRecord]):
    pass


class RawBeliefProposalPanel(ArtifactPanel[RawBeliefProposalRecord]):
    pass


class SocialIntentPanel(ArtifactPanel[SocialIntentRecord]):
    pass


class FinalizedSocialIntentPanel(ArtifactPanel[SocialIntentRecord]):
    pass


class ToolCallRequestPanel(ArtifactPanel[ToolCallRequestRecord]):
    pass


class AttentionFollowupIntentPanel(ArtifactPanel[AttentionFollowupIntentRecord]):
    pass


class FinalizedAttentionFollowupIntentPanel(
    ArtifactPanel[AttentionFollowupIntentRecord]
):
    pass


class ValidatedToolCallRequestPanel(ArtifactPanel[ValidatedToolCallRequestRecord]):
    pass


class RawToolResultPanel(ArtifactPanel[RawToolResultRecord]):
    pass


class ToolCallAuditPanel(ArtifactPanel[ToolCallAuditRecord]):
    pass


class ToolDiscoveryEventPanel(ArtifactPanel[ToolDiscoveryEventRecord]):
    pass


class ValidatedToolResultPanel(ArtifactPanel[ValidatedToolResultRecord]):
    pass


class DirectionalBeliefPayload(StrictModel):
    value_type: Literal[BeliefValueType.DIRECTIONAL_SCORE]
    direction: NonEmptyStr
    score: Annotated[float, Field(ge=-1.0, le=1.0)]


class VolatilityBeliefPayload(StrictModel):
    value_type: Literal[BeliefValueType.VOLATILITY_LEVEL]
    level: Probability


class RegimeBeliefPayload(StrictModel):
    value_type: Literal[BeliefValueType.REGIME_PROBABILITIES]
    probabilities: dict[NonEmptyStr, Probability]

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> "RegimeBeliefPayload":
        if abs(sum(self.probabilities.values()) - 1.0) > 1e-9:
            raise ValueError("regime probabilities must sum to 1")
        return self


BeliefPayload = Annotated[
    DirectionalBeliefPayload | VolatilityBeliefPayload | RegimeBeliefPayload,
    Field(discriminator="value_type"),
]


class StructuredBeliefProposalRecord(StrictModel):
    belief_proposal_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    payload: BeliefPayload
    strength: Probability
    confidence: Probability
    uncertainty: Probability
    supporting_evidence_refs: tuple[NonEmptyStr, ...] = ()
    opposing_evidence_refs: tuple[NonEmptyStr, ...] = ()
    generated_at: UTCDateTime
    as_of: UTCDateTime


class StructuredBeliefProposalPanel(ArtifactPanel[StructuredBeliefProposalRecord]):
    pass


class PropositionDefinition(StrictModel):
    proposition_id: NonEmptyStr
    value_type: BeliefValueType
    allowed_horizons: tuple[NonEmptyStr, ...]
    allow_unresolved_underlying: bool = False
    direction_mapping: dict[NonEmptyStr, Annotated[float, Field(ge=-1.0, le=1.0)]] = (
        Field(default_factory=dict)
    )
    regime_labels: tuple[NonEmptyStr, ...] = ()


class PropositionRegistryConfig(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    registry_version: NonEmptyStr
    propositions: tuple[PropositionDefinition, ...]

    def get(self, proposition_id: str) -> PropositionDefinition:
        for proposition in self.propositions:
            if proposition.proposition_id == proposition_id:
                return proposition
        raise ValueError(f"unknown proposition: {proposition_id}")


class InitialCognitionOutput(StrictModel):
    reading_summary: NonEmptyStr
    claims: tuple[ClaimRecord, ...]
    confidence: Probability
    uncertainty: Probability
    preliminary_belief: RawBeliefProposalRecord
    social_intents: tuple[SocialIntentRecord, ...] = ()
    tool_requests: tuple[ToolCallRequestRecord, ...] = ()
    attention_followups: tuple[AttentionFollowupIntentRecord, ...] = ()


class ContinuationCognitionOutput(StrictModel):
    reading_summary: NonEmptyStr
    claims: tuple[ClaimRecord, ...]
    confidence: Probability
    uncertainty: Probability
    final_belief: RawBeliefProposalRecord
    social_intents: tuple[SocialIntentRecord, ...] = ()
    attention_followups: tuple[AttentionFollowupIntentRecord, ...] = ()




class PromptTemplate(StrictModel):
    prompt_id: NonEmptyStr
    prompt_version: NonEmptyStr
    system_prompt: NonEmptyStr
    prompt_hash: NonEmptyStr

class LLMRequest(StrictModel):
    stage: CognitionStage
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    prompt_id: NonEmptyStr
    prompt_version: NonEmptyStr
    prompt_hash: NonEmptyStr
    system_prompt: NonEmptyStr
    user_prompt: NonEmptyStr
    temperature: Annotated[float, Field(ge=0.0, le=0.3)]
    max_output_tokens: PositiveInt
    seed: NonNegativeInt | None = None
    context: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]


class LLMResponse(StrictModel):
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    content: dict[str, JsonValue]
    response_hash: NonEmptyStr
    raw_response_ref: str | None = None


class ToolExecutionResponse(StrictModel):
    status: ToolExecutionStatus
    provider_id: NonEmptyStr
    canonical_payload: dict[str, JsonValue] | None = None
    raw_payload_ref: str | None = None
    available_at: UTCDateTime | None = None
    cost_units: NonNegativeFloat = 0.0
    response_hash: str | None = None
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    error: ToolErrorRecord | None = None


MODEL_ADAPTERS: dict[str, TypeAdapter[StrictModel]] = {
    "InitialCognitionOutput": TypeAdapter(InitialCognitionOutput),
    "ContinuationCognitionOutput": TypeAdapter(ContinuationCognitionOutput),
}
