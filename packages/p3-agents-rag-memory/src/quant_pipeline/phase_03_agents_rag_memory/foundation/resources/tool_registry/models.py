from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonObject = dict[str, Any]


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


class DiscoveryMode(StrEnum):
    STATIC_ONLY = "STATIC_ONLY"
    FROZEN_SNAPSHOT = "FROZEN_SNAPSHOT"
    LIVE_CONFIRM = "LIVE_CONFIRM"


class ConfigurationStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class ConnectivityStatus(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


class QualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AvailabilityStatus(StrEnum):
    AVAILABLE_QUALIFIED = "AVAILABLE_QUALIFIED"
    UNAVAILABLE_DISCONNECTED = "UNAVAILABLE_DISCONNECTED"
    UNAVAILABLE_UNQUALIFIED = "UNAVAILABLE_UNQUALIFIED"
    DISABLED = "DISABLED"
    FAILED_VALIDATION = "FAILED_VALIDATION"


class ExecutionMode(StrEnum):
    READ_ONLY = "READ_ONLY"
    STATE_CHANGING = "STATE_CHANGING"


class CredentialPolicy(StrEnum):
    NONE = "NONE"
    HANDLE_ONLY = "HANDLE_ONLY"


class EntitlementAction(StrEnum):
    DISCOVER = "DISCOVER"
    REQUEST = "REQUEST"
    EXECUTE = "EXECUTE"


class DecisionEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class EntitlementDecision(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"


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

    @model_validator(mode="after")
    def live_only_reason_consistency(self) -> "PitPolicy":
        if not self.backtest_allowed and not self.live_only_reason:
            raise ValueError("live_only_reason required when backtest_allowed is false")
        return self


class CostPolicy(StrictModel):
    cost_class: Literal["FREE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    estimated_cost_per_call: float | None = Field(default=None, ge=0.0)
    currency: str | None = None


class ToolConfig(StrictModel):
    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    title: str | None = None
    description: str = ""
    provider_id: str = Field(min_length=1)
    interface_id: str = "MCPGatewayAdapter"
    adapter_id: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    capability_family: str = Field(min_length=1)
    configuration_status: ConfigurationStatus = ConfigurationStatus.ENABLED
    execution_mode: ExecutionMode = ExecutionMode.READ_ONLY
    request_schema: JsonObject
    response_schema: JsonObject | None = None
    pit_policy: PitPolicy
    credential_policy: CredentialPolicy = CredentialPolicy.HANDLE_ONLY
    credential_handle_type: str | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_policy: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    rate_limit_policy: RateLimitPolicy = Field(default_factory=RateLimitPolicy)
    cost_policy: CostPolicy = Field(default_factory=CostPolicy)
    cacheable: bool = False
    deterministic_or_seeded: bool = False
    sensitivity_class: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"] = "PUBLIC"
    permitted_data_classes: tuple[str, ...] = ()
    max_calls_per_person_cycle: int = Field(default=3, ge=0, le=100)
    discovery_name: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("effective_from", "effective_to")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value

    @model_validator(mode="after")
    def validate_credentials_and_window(self) -> "ToolConfig":
        if self.credential_policy == CredentialPolicy.HANDLE_ONLY and not self.credential_handle_type:
            raise ValueError("credential_handle_type required for HANDLE_ONLY")
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("effective_from must not exceed effective_to")
        return self


class ToolRegistryConfig(StrictModel):
    schema_id: Literal["tool_registry_config.s15.v2"] = "tool_registry_config.s15.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    execution_context: ExecutionContext
    discovery_mode: DiscoveryMode = DiscoveryMode.STATIC_ONLY
    disconnected_tools_not_entitleable: Literal[True] = True
    unqualified_tools_not_entitleable: Literal[True] = True
    credential_policy: Literal["handle_only"] = "handle_only"
    tools: tuple[ToolConfig, ...] = ()

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value

    @model_validator(mode="after")
    def backtest_discovery_guard(self) -> "ToolRegistryConfig":
        if self.execution_context == ExecutionContext.BACKTEST and self.discovery_mode == DiscoveryMode.LIVE_CONFIRM:
            raise ValueError("LIVE_CONFIRM is forbidden in BACKTEST")
        return self


class DiscoveredTool(StrictModel):
    name: str
    title: str | None = None
    description: str = ""
    input_schema: JsonObject
    output_schema: JsonObject | None = None
    annotations: JsonObject = Field(default_factory=dict)


class DiscoverySnapshot(StrictModel):
    provider_id: str
    protocol: str
    protocol_version: str
    observed_at: datetime
    connectivity_status: ConnectivityStatus
    list_changed_supported: bool = False
    tools: tuple[DiscoveredTool, ...] = ()
    next_cursor_exhausted: bool = True
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    issues: tuple[str, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware observed_at required")
        return value


class ProviderAdapter(StrictModel):
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    protocol: Literal["MCP", "LOCAL", "HTTP", "FUNCTION"]
    protocol_version: str
    connectivity_status: ConnectivityStatus
    qualification_status: QualificationStatus
    capabilities: tuple[str, ...]
    list_changed_supported: bool = False
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    metadata: JsonObject = Field(default_factory=dict)


class ProviderAdapterRegistry(StrictModel):
    schema_id: Literal["provider_adapter_registry.s15.v2"] = "provider_adapter_registry.s15.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    registry_id: str
    adapters: tuple[ProviderAdapter, ...]

    def find(self, provider_id: str, interface_id: str) -> ProviderAdapter | None:
        return next(
            (item for item in self.adapters if item.provider_id == provider_id and item.interface_id == interface_id),
            None,
        )


class PatchChange(StrictModel):
    field: Literal[
        "configuration_status",
        "timeout_ms",
        "max_calls_per_person_cycle",
        "cacheable",
    ]
    value: str | int | bool


class ActiveRetroPolicyPatch(StrictModel):
    patch_id: str
    change_type: Literal["tool_update"]
    change_target: str
    promoted_at: datetime
    effective_cycle_id: str
    lineage_id: str
    changes: tuple[PatchChange, ...] = ()

    @field_validator("promoted_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware promoted_at required")
        return value


class EffectiveTool(StrictModel):
    tool_id: str
    tool_version: str
    name: str
    title: str | None
    description: str
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    capability_family: str
    configuration_status: ConfigurationStatus
    connectivity_status: ConnectivityStatus
    qualification_status: QualificationStatus
    availability_status: AvailabilityStatus
    execution_mode: ExecutionMode
    request_schema: JsonObject
    request_schema_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_schema: JsonObject | None
    response_schema_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    pit_policy: PitPolicy
    credential_policy: CredentialPolicy
    credential_handle_type: str | None
    retry_policy: RetryPolicy
    timeout_policy: TimeoutPolicy
    rate_limit_policy: RateLimitPolicy
    cost_policy: CostPolicy
    cacheable: bool
    deterministic_or_seeded: bool
    sensitivity_class: str
    permitted_data_classes: tuple[str, ...]
    max_calls_per_person_cycle: int
    protocol: str
    protocol_version: str
    provider_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    discovery_snapshot_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    discovery_observed_at: datetime | None = None
    discovery_confirmed: bool
    list_changed_supported: bool
    effective_from: datetime | None
    effective_to: datetime | None
    reason_codes: tuple[str, ...] = ()
    metadata: JsonObject = Field(default_factory=dict)


class RegistryCoverage(StrictModel):
    configured_tool_count: int = Field(ge=0)
    available_qualified_count: int = Field(ge=0)
    disconnected_count: int = Field(ge=0)
    unqualified_count: int = Field(ge=0)
    disabled_count: int = Field(ge=0)
    failed_validation_count: int = Field(ge=0)


class ToolRegistryArtifact(StrictModel):
    artifact_name: Literal["tool_registry"] = "tool_registry"
    schema_id: Literal["tool_registry.v2"] = "tool_registry.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ArtifactStatus
    grain: tuple[str, ...] = ("tool_id",)
    primary_key: tuple[str, ...] = ("tool_id",)
    configuration_hash: str
    provider_registry_hash: str
    applied_patch_id: str | None = None
    tools: tuple[EffectiveTool, ...]
    coverage: RegistryCoverage
    issues: tuple[str, ...] = ()


class PersonSeed(StrictModel):
    person_id: str
    economic_role: str
    institution: str | None = None
    resources: tuple[str, ...] = ()
    capabilities: dict[str, float] = Field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    allowed_data_classes: tuple[str, ...] = ()
    schema_version: str

    @field_validator("capabilities")
    @classmethod
    def capability_range(cls, value: dict[str, float]) -> dict[str, float]:
        if any(score < 0.0 or score > 1.0 for score in value.values()):
            raise ValueError("capability scores must be between 0 and 1")
        return value


class PersonSeedPanel(StrictModel):
    schema_id: Literal["person_seed_panel.s15.v2"] = "person_seed_panel.s15.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    records: tuple[PersonSeed, ...]
    lineage_id: str


class PersonSchemaPolicy(StrictModel):
    schema_id: Literal["person_schema_policy.s15.v2"] = "person_schema_policy.s15.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    allowed_roles: tuple[str, ...]
    allowed_resources: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    allowed_constraints: tuple[str, ...]
    forbidden_entitlement_attributes: tuple[str, ...] = (
        "performance",
        "future_return",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
    )


class SubjectMatch(StrictModel):
    roles: tuple[str, ...] = ()
    institutions: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    required_constraints: tuple[str, ...] = ()
    forbidden_constraints: tuple[str, ...] = ()
    minimum_capabilities: dict[str, float] = Field(default_factory=dict)


class ResourceMatch(StrictModel):
    tool_ids: tuple[str, ...] = ()
    capability_families: tuple[str, ...] = ()
    execution_modes: tuple[ExecutionMode, ...] = ()
    sensitivity_classes: tuple[str, ...] = ()
    required_data_classes: tuple[str, ...] = ()


class RuleBudget(StrictModel):
    max_calls_per_cycle: int | None = Field(default=None, ge=0, le=100)
    max_cost_per_cycle: float | None = Field(default=None, ge=0.0)
    max_latency_ms: int | None = Field(default=None, ge=1)


class EntitlementRule(StrictModel):
    rule_id: str
    effect: DecisionEffect
    priority: int = Field(default=0, ge=0, le=10_000)
    actions: tuple[EntitlementAction, ...]
    subject: SubjectMatch = Field(default_factory=SubjectMatch)
    resource: ResourceMatch = Field(default_factory=ResourceMatch)
    budget: RuleBudget = Field(default_factory=RuleBudget)
    reason_code: str


class ToolEntitlementConfig(StrictModel):
    schema_id: Literal["tool_entitlement_config.s15.v2"] = "tool_entitlement_config.s15.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    default_decision: Literal["DENY"] = "DENY"
    deny_overrides: Literal[True] = True
    role_and_resource_based: Literal[True] = True
    performance_based_entitlement_forbidden: Literal[True] = True
    default_budget_calls_per_cycle: int = Field(default=3, ge=0, le=100)
    maximum_entitlement_calls_per_cycle: int = Field(default=5, ge=0, le=100)
    default_max_cost_per_cycle: float | None = Field(default=None, ge=0.0)
    default_max_latency_ms: int | None = Field(default=None, ge=1)
    rules: tuple[EntitlementRule, ...] = ()

    @model_validator(mode="after")
    def budget_hierarchy(self) -> "ToolEntitlementConfig":
        if self.default_budget_calls_per_cycle > self.maximum_entitlement_calls_per_cycle:
            raise ValueError("default budget cannot exceed maximum entitlement budget")
        return self


class EntitlementBudget(StrictModel):
    max_calls_per_cycle: int = Field(ge=0)
    max_cost_per_cycle: float | None = Field(default=None, ge=0.0)
    max_latency_ms: int | None = Field(default=None, ge=1)


class EntitlementRecord(StrictModel):
    person_id: str
    tool_id: str
    decision: EntitlementDecision
    allowed_actions: tuple[EntitlementAction, ...]
    budget: EntitlementBudget
    allowed_operations: tuple[str, ...] = ()
    allowed_data_classes: tuple[str, ...] = ()
    matched_allow_rule_ids: tuple[str, ...] = ()
    matched_deny_rule_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...]
    policy_version: str


class EntitlementCoverage(StrictModel):
    person_count: int = Field(ge=0)
    tool_count: int = Field(ge=0)
    evaluated_pair_count: int = Field(ge=0)
    allowed_pair_count: int = Field(ge=0)
    denied_pair_count: int = Field(ge=0)
    unavailable_tool_pair_count: int = Field(ge=0)


class PersonToolEntitlementPanel(StrictModel):
    artifact_name: Literal["person_tool_entitlement_panel"] = "person_tool_entitlement_panel"
    schema_id: Literal["person_tool_entitlement_panel.v2"] = "person_tool_entitlement_panel.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    cycle_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ArtifactStatus
    grain: tuple[str, ...] = ("person_id", "tool_id")
    primary_key: tuple[str, ...] = ("person_id", "tool_id")
    tool_registry_hash: str
    person_seed_panel_hash: str
    person_schema_policy_hash: str
    entitlement_config_hash: str
    records: tuple[EntitlementRecord, ...]
    coverage: EntitlementCoverage
    issues: tuple[str, ...] = ()
