from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonObject = dict[str, Any]
HEX64 = r"^[a-f0-9]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True)


class ArtifactStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    EMPTY = "EMPTY"
    BLOCKED = "BLOCKED"


class ExecutionContext(StrEnum):
    BACKTEST = "BACKTEST"
    LIVE = "LIVE"
    TEST = "TEST"


class ExecutionMode(StrEnum):
    READ_ONLY = "READ_ONLY"
    STATE_CHANGING = "STATE_CHANGING"


class AvailabilityStatus(StrEnum):
    AVAILABLE_QUALIFIED = "AVAILABLE_QUALIFIED"
    UNAVAILABLE_DISCONNECTED = "UNAVAILABLE_DISCONNECTED"
    UNAVAILABLE_UNQUALIFIED = "UNAVAILABLE_UNQUALIFIED"
    DISABLED = "DISABLED"
    FAILED_VALIDATION = "FAILED_VALIDATION"


class EntitlementDecision(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"


class CredentialPolicy(StrEnum):
    NONE = "NONE"
    HANDLE_ONLY = "HANDLE_ONLY"


class CacheMode(StrEnum):
    FROZEN_IN_BACKTEST = "FROZEN_IN_BACKTEST"
    READ_THROUGH_LIVE = "READ_THROUGH_LIVE"
    DISABLED = "DISABLED"


class ApprovalPolicy(StrEnum):
    AUTO_READ_ONLY = "AUTO_READ_ONLY"
    HUMAN_REQUIRED_STATE_CHANGING = "HUMAN_REQUIRED_STATE_CHANGING"
    STATE_CHANGING_FORBIDDEN = "STATE_CHANGING_FORBIDDEN"


class BackoffPolicy(StrEnum):
    NONE = "NONE"
    EXPONENTIAL_FULL_JITTER = "EXPONENTIAL_FULL_JITTER"


class GatewayDecision(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    BLOCKED = "BLOCKED"


class AuditEventType(StrEnum):
    EXECUTION_STARTED = "EXECUTION_STARTED"
    ATTEMPT_STARTED = "ATTEMPT_STARTED"
    CACHE_HIT = "CACHE_HIT"
    ATTEMPT_FAILED = "ATTEMPT_FAILED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_TIMED_OUT = "EXECUTION_TIMED_OUT"
    EXECUTION_CANCELLED = "EXECUTION_CANCELLED"
    RESULT_REJECTED = "RESULT_REJECTED"


class CacheStatus(StrEnum):
    NOT_CHECKED = "NOT_CHECKED"
    MISS = "MISS"
    HIT = "HIT"
    WRITE = "WRITE"
    BYPASSED = "BYPASSED"


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=1, ge=1, le=10)
    retryable_failure_codes: tuple[str, ...] = ()
    backoff_policy: Literal["NONE", "EXPONENTIAL_JITTER"] = "NONE"


class TimeoutPolicy(StrictModel):
    timeout_ms: int = Field(default=30_000, ge=1, le=600_000)


class RateLimitPolicy(StrictModel):
    max_calls_per_minute: int | None = Field(default=None, ge=1)


class PitPolicy(StrictModel):
    backtest_allowed: bool
    live_allowed: bool = True
    requires_available_at: bool = True
    live_only_reason: str | None = None


class CostPolicy(StrictModel):
    cost_class: str = "UNKNOWN"
    estimated_cost_per_call: float | None = Field(default=None, ge=0.0)
    currency: str | None = None


class EffectiveTool(StrictModel):
    tool_id: str
    tool_version: str
    name: str
    title: str | None = None
    description: str = ""
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    capability_family: str
    configuration_status: str
    connectivity_status: str
    qualification_status: str
    availability_status: AvailabilityStatus
    execution_mode: ExecutionMode
    request_schema: JsonObject
    request_schema_hash: str = Field(pattern=HEX64)
    response_schema: JsonObject | None = None
    response_schema_hash: str | None = Field(default=None, pattern=HEX64)
    pit_policy: PitPolicy
    credential_policy: CredentialPolicy
    credential_handle_type: str | None = None
    retry_policy: RetryPolicy
    timeout_policy: TimeoutPolicy
    rate_limit_policy: RateLimitPolicy
    cost_policy: CostPolicy
    cacheable: bool
    deterministic_or_seeded: bool
    sensitivity_class: str
    permitted_data_classes: tuple[str, ...] = ()
    max_calls_per_person_cycle: int = Field(ge=0, le=100)
    protocol: str
    protocol_version: str
    provider_fingerprint: str = Field(pattern=HEX64)
    discovery_snapshot_fingerprint: str | None = Field(default=None, pattern=HEX64)
    discovery_observed_at: datetime | None = None
    discovery_confirmed: bool = False
    list_changed_supported: bool = False
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    reason_codes: tuple[str, ...] = ()
    metadata: JsonObject = Field(default_factory=dict)


class ToolRegistryArtifact(StrictModel):
    artifact_name: Literal["tool_registry"]
    schema_id: Literal["tool_registry.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=HEX64)
    status: ArtifactStatus
    grain: tuple[str, ...]
    primary_key: tuple[str, ...]
    configuration_hash: str = Field(pattern=HEX64)
    provider_registry_hash: str = Field(pattern=HEX64)
    applied_patch_id: str | None = None
    tools: tuple[EffectiveTool, ...]
    coverage: JsonObject
    issues: tuple[str, ...] = ()


class EntitlementBudget(StrictModel):
    max_calls_per_cycle: int = Field(ge=0)
    max_cost_per_cycle: float | None = Field(default=None, ge=0.0)
    max_latency_ms: int | None = Field(default=None, ge=1)


class EntitlementRecord(StrictModel):
    person_id: str
    tool_id: str
    decision: EntitlementDecision
    allowed_actions: tuple[str, ...]
    budget: EntitlementBudget
    allowed_operations: tuple[str, ...] = ()
    allowed_data_classes: tuple[str, ...] = ()
    matched_allow_rule_ids: tuple[str, ...] = ()
    matched_deny_rule_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...]
    policy_version: str


class PersonToolEntitlementPanel(StrictModel):
    artifact_name: Literal["person_tool_entitlement_panel"]
    schema_id: Literal["person_tool_entitlement_panel.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=HEX64)
    status: ArtifactStatus
    grain: tuple[str, ...]
    primary_key: tuple[str, ...]
    tool_registry_hash: str = Field(pattern=HEX64)
    person_seed_panel_hash: str = Field(pattern=HEX64)
    person_schema_policy_hash: str = Field(pattern=HEX64)
    entitlement_config_hash: str = Field(pattern=HEX64)
    records: tuple[EntitlementRecord, ...]
    coverage: JsonObject
    issues: tuple[str, ...] = ()


class ProviderAdapter(StrictModel):
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    protocol: str
    protocol_version: str
    connectivity_status: str
    qualification_status: str
    capabilities: tuple[str, ...]
    list_changed_supported: bool = False
    fingerprint: str = Field(pattern=HEX64)
    metadata: JsonObject = Field(default_factory=dict)


class ProviderAdapterRegistry(StrictModel):
    schema_id: str
    schema_version: str
    registry_id: str
    adapters: tuple[ProviderAdapter, ...]

    def find(self, provider_id: str, interface_id: str) -> ProviderAdapter | None:
        return next((x for x in self.adapters if x.provider_id == provider_id and x.interface_id == interface_id), None)


class RetryControlConfig(StrictModel):
    max_attempts_per_call: int = Field(default=2, ge=1, le=5)
    backoff_policy: BackoffPolicy = BackoffPolicy.EXPONENTIAL_FULL_JITTER
    base_delay_ms: int = Field(default=250, ge=1, le=60_000)
    max_delay_ms: int = Field(default=5_000, ge=1, le=120_000)
    retry_budget_per_run: int = Field(default=100, ge=0, le=100_000)
    respect_retry_after: Literal[True] = True

    @model_validator(mode="after")
    def delays_valid(self) -> "RetryControlConfig":
        if self.base_delay_ms > self.max_delay_ms:
            raise ValueError("base_delay_ms must not exceed max_delay_ms")
        return self


class CacheControlConfig(StrictModel):
    mode: CacheMode = CacheMode.FROZEN_IN_BACKTEST
    require_cache_hit_in_backtest: bool = True
    cache_key_version: str = "2.0.0"
    include_provider_fingerprint: Literal[True] = True
    include_request_schema_hash: Literal[True] = True


class SecurityControlConfig(StrictModel):
    credential_policy: Literal["HANDLE_ONLY"] = "HANDLE_ONLY"
    secret_material_forbidden: Literal[True] = True
    tool_annotations_untrusted: Literal[True] = True
    tool_result_untrusted: Literal[True] = True
    preserve_meta_for_host_only: Literal[True] = True
    expose_meta_to_model: Literal[False] = False
    require_output_schema_validation_when_declared: Literal[True] = True
    reject_unknown_output_fields: bool = True
    state_changing_policy: ApprovalPolicy = ApprovalPolicy.STATE_CHANGING_FORBIDDEN
    forbidden_argument_fields: tuple[str, ...] = (
        "future_return", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "buy_sell_signal",
        "api_key", "access_token", "refresh_token", "password", "secret", "authorization",
    )


class ToolGatewayConfig(StrictModel):
    schema_id: Literal["tool_gateway_config.s16.v2"] = "tool_gateway_config.s16.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    execution_context: ExecutionContext
    pit_required: Literal[True] = True
    audit_required: Literal[True] = True
    provider_failure_policy: Literal["MATERIAL_NO_FAKE_SUCCESS"] = "MATERIAL_NO_FAKE_SUCCESS"
    max_calls_per_person_cycle: int = Field(default=5, ge=0, le=100)
    max_total_calls_per_run: int = Field(default=5_000, ge=0)
    max_total_cost_per_run: float | None = Field(default=None, ge=0.0)
    max_concurrency_per_provider: int = Field(default=4, ge=1, le=100)
    hard_timeout_ms: int = Field(default=60_000, ge=1, le=600_000)
    approval_policy: ApprovalPolicy = ApprovalPolicy.STATE_CHANGING_FORBIDDEN
    retry: RetryControlConfig = Field(default_factory=RetryControlConfig)
    cache: CacheControlConfig = Field(default_factory=CacheControlConfig)
    security: SecurityControlConfig = Field(default_factory=SecurityControlConfig)
    accepted_protocol_versions: tuple[str, ...] = ("2025-11-25", "local-v1")
    experimental_task_support: Literal[False] = False

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value

    @model_validator(mode="after")
    def consistency(self) -> "ToolGatewayConfig":
        if self.security.state_changing_policy != self.approval_policy:
            raise ValueError("approval policies must match")
        if self.execution_context == ExecutionContext.BACKTEST and self.cache.mode != CacheMode.FROZEN_IN_BACKTEST:
            raise ValueError("BACKTEST requires FROZEN_IN_BACKTEST cache mode")
        return self


class EffectiveRetryPolicy(StrictModel):
    max_attempts: int = Field(ge=1, le=5)
    retryable_failure_codes: tuple[str, ...]
    backoff_policy: BackoffPolicy
    base_delay_ms: int
    max_delay_ms: int
    automatic_retry_allowed: bool
    idempotency_key_required: bool


class EffectiveCachePolicy(StrictModel):
    mode: CacheMode
    cacheable: bool
    require_hit: bool
    cache_key_version: str


class EffectiveCredentialPolicy(StrictModel):
    policy: CredentialPolicy
    handle_type: str | None = None
    materialization_location: Literal["ADAPTER_ONLY"] = "ADAPTER_ONLY"


class GatewayToolControl(StrictModel):
    person_id: str
    tool_id: str
    gateway_decision: GatewayDecision
    reason_codes: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    allowed_data_classes: tuple[str, ...]
    execution_mode: ExecutionMode
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    protocol: str
    protocol_version: str
    provider_fingerprint: str = Field(pattern=HEX64)
    request_schema: JsonObject
    request_schema_hash: str = Field(pattern=HEX64)
    response_schema: JsonObject | None = None
    response_schema_hash: str | None = Field(default=None, pattern=HEX64)
    pit_policy: PitPolicy
    credential_policy: EffectiveCredentialPolicy
    timeout_ms: int = Field(ge=1)
    max_calls_per_cycle: int = Field(ge=0)
    max_cost_per_cycle: float | None = Field(default=None, ge=0.0)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    retry_policy: EffectiveRetryPolicy
    cache_policy: EffectiveCachePolicy
    approval_required: bool
    result_content_untrusted: Literal[True] = True
    preserve_meta_for_host_only: Literal[True] = True


class GatewayCoverage(StrictModel):
    evaluated_pair_count: int = Field(ge=0)
    allowed_pair_count: int = Field(ge=0)
    denied_pair_count: int = Field(ge=0)
    blocked_pair_count: int = Field(ge=0)
    state_changing_pair_count: int = Field(ge=0)
    cache_required_pair_count: int = Field(ge=0)


class MCPGatewayPolicy(StrictModel):
    artifact_name: Literal["mcp_gateway_policy"] = "mcp_gateway_policy"
    schema_id: Literal["mcp_gateway_policy.v2"] = "mcp_gateway_policy.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=HEX64)
    status: ArtifactStatus
    grain: tuple[str, ...] = ("person_id", "tool_id")
    primary_key: tuple[str, ...] = ("person_id", "tool_id")
    tool_registry_hash: str = Field(pattern=HEX64)
    entitlement_panel_hash: str = Field(pattern=HEX64)
    gateway_config_hash: str = Field(pattern=HEX64)
    provider_registry_hash: str = Field(pattern=HEX64)
    policy_version: Literal["2.0.0"] = "2.0.0"
    controls: tuple[GatewayToolControl, ...]
    coverage: GatewayCoverage
    global_controls: JsonObject
    issues: tuple[str, ...] = ()


class CredentialHandleRef(StrictModel):
    handle: str = Field(min_length=1, max_length=512)
    handle_type: str = Field(min_length=1, max_length=128)

    @field_validator("handle")
    @classmethod
    def no_secret_patterns(cls, value: str) -> str:
        lowered = value.lower()
        if any(token in lowered for token in ("bearer ", "sk-", "api_key=", "password=", "secret=")):
            raise ValueError("credential handle appears to contain secret material")
        return value


class GatewayBudgetState(StrictModel):
    person_tool_calls_used: int = Field(default=0, ge=0)
    total_calls_used: int = Field(default=0, ge=0)
    person_tool_cost_used: float = Field(default=0.0, ge=0.0)
    total_cost_used: float = Field(default=0.0, ge=0.0)


class ToolCallRequestEnvelope(StrictModel):
    schema_id: Literal["tool_call_request_envelope.s16.v2"] = "tool_call_request_envelope.s16.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    tool_call_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    person_id: str
    tool_id: str
    as_of_time: datetime
    arguments: JsonObject
    credential_handle: CredentialHandleRef | None = None
    idempotency_key: str | None = None
    cache_key: str | None = None
    estimated_cost: float | None = Field(default=None, ge=0.0)
    approval_ref: str | None = None
    budget_state: GatewayBudgetState = Field(default_factory=GatewayBudgetState)

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value


class GatewayExecutionDecision(StrictModel):
    schema_id: Literal["gateway_execution_decision.s16.v2"] = "gateway_execution_decision.s16.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    tool_call_id: str
    decision: GatewayDecision
    reason_codes: tuple[str, ...]
    control_hash: str = Field(pattern=HEX64)
    request_hash: str = Field(pattern=HEX64)
    effective_timeout_ms: int | None = None
    effective_max_attempts: int | None = None
    cache_required: bool = False
    credential_resolution_required: bool = False


class AuditFieldRule(StrictModel):
    field_name: str
    required_for_events: tuple[AuditEventType, ...]
    sensitive: bool = False
    hash_only: bool = False


class AuditTransition(StrictModel):
    from_event: AuditEventType
    to_events: tuple[AuditEventType, ...]


class ToolCallAuditContract(StrictModel):
    artifact_name: Literal["tool_call_audit_contract"] = "tool_call_audit_contract"
    schema_id: Literal["tool_call_audit_contract.v2"] = "tool_call_audit_contract.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=HEX64)
    status: ArtifactStatus
    gateway_policy_hash: str = Field(pattern=HEX64)
    contract_version: Literal["2.0.0"] = "2.0.0"
    allowed_event_types: tuple[AuditEventType, ...]
    terminal_event_types: tuple[AuditEventType, ...]
    transitions: tuple[AuditTransition, ...]
    field_rules: tuple[AuditFieldRule, ...]
    redaction_rules: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    fake_success_forbidden: Literal[True] = True
    pre_execution_rejection_belongs_to_request_validation_panel: Literal[True] = True
    result_contract: JsonObject
    observability_mapping: JsonObject
    issues: tuple[str, ...] = ()


class CostRecord(StrictModel):
    amount: float = Field(ge=0.0)
    currency: str = Field(min_length=3, max_length=8)


class ToolCallAuditEvent(StrictModel):
    schema_id: Literal["tool_call_audit_event.s16.v2"] = "tool_call_audit_event.s16.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    event_type: AuditEventType
    sequence_number: int = Field(ge=0)
    tool_call_id: str
    attempt_id: str | None = None
    run_id: str
    cycle_id: str
    snapshot_id: str
    person_id: str
    tool_id: str
    provider_id: str
    timestamp: datetime
    request_hash: str = Field(pattern=HEX64)
    argument_schema_hash: str = Field(pattern=HEX64)
    authorization_policy_hash: str = Field(pattern=HEX64)
    idempotency_key_hash: str | None = Field(default=None, pattern=HEX64)
    cache_status: CacheStatus = CacheStatus.NOT_CHECKED
    latency_ms: float | None = Field(default=None, ge=0.0)
    retry_count: int | None = Field(default=None, ge=0)
    cost: CostRecord | None = None
    result_hash: str | None = Field(default=None, pattern=HEX64)
    structured_content_hash: str | None = Field(default=None, pattern=HEX64)
    result_available_at: datetime | None = None
    source_available_at: datetime | None = None
    response_schema_validated: bool | None = None
    is_error: bool | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    retryable: bool | None = None
    redacted_fields: tuple[str, ...] = ()
    secret_material_detected: bool = False
    provider_request_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None

    @field_validator("timestamp", "result_available_at", "source_available_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value


class NormalizedToolResult(StrictModel):
    content: tuple[JsonObject, ...]
    structured_content: JsonObject | None = None
    is_error: bool = False
    host_meta: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(pattern=HEX64)
    structured_content_hash: str | None = Field(default=None, pattern=HEX64)
    untrusted_content: Literal[True] = True
