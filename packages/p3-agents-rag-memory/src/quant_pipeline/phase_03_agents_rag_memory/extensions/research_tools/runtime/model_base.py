"""Core registry and runtime-binding contracts for P3.S40."""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import (
    ContractModel,
    NonEmptyStr,
    Sha256,
)

SCHEMA_VERSION = "p3.s40.v1"
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]


class TransportKind(StrEnum):
    LOCAL_FUNCTION = "LOCAL_FUNCTION"
    ARTIFACT_QUERY = "ARTIFACT_QUERY"
    COMPOSITE_INTERNAL = "COMPOSITE_INTERNAL"
    MCP_OPTIONAL = "MCP_OPTIONAL"
    HTTP_OPTIONAL = "HTTP_OPTIONAL"


class RegistryStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class QualificationStatus(StrEnum):
    QUALIFIED_LOCAL = "QUALIFIED_LOCAL"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
    FAILED = "FAILED"


class OutcomeStatus(StrEnum):
    PASS = "PASS"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class ConsumerCompatibilityStatus(StrEnum):
    PRODUCER_READY_CONSUMER_NOT_YET_WIRED = "PRODUCER_READY_CONSUMER_NOT_YET_WIRED"
    DEFERRED_BY_GOVERNANCE = "DEFERRED_BY_GOVERNANCE"
    CONSUMER_COMPATIBLE = "CONSUMER_COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"


class ReleaseGateStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
    FAIL = "FAIL"


class S40Lineage(ContractModel):
    lineage_id: NonEmptyStr
    producer_module_id: Annotated[str, Field(pattern=r"^P3\.S40\.M\d{2}$")]
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_hashes: dict[NonEmptyStr, Sha256] = Field(default_factory=dict)
    transformation_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def hashes_reference_declared_sources(self) -> "S40Lineage":
        undeclared = set(self.source_hashes) - set(self.source_artifact_ids)
        if undeclared:
            raise ValueError(f"source hashes reference undeclared artifacts: {sorted(undeclared)}")
        return self


class AliasBinding(ContractModel):
    alias_tool_id: NonEmptyStr
    alias_operation_id: NonEmptyStr
    target_tool_id: NonEmptyStr
    target_operation_id: NonEmptyStr
    fixed_arguments: dict[str, JsonValue] = Field(default_factory=dict)
    argument_renames: dict[str, NonEmptyStr] = Field(default_factory=dict)
    deprecated: bool = True
    second_handler_forbidden: bool = True


class OperationDescriptor(ContractModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    handler_id: NonEmptyStr
    handler_version: NonEmptyStr
    provider_id: NonEmptyStr = "internal_research"
    transport: TransportKind
    request_schema_ref: NonEmptyStr
    result_schema_ref: NonEmptyStr
    supported_modes: tuple[NonEmptyStr, ...]
    required_view_ids: tuple[NonEmptyStr, ...] = ()
    qualification_status: QualificationStatus
    read_only: Literal[True] = True
    point_in_time_safe: Literal[True] = True
    deterministic_or_seeded: bool = True
    source_bundle_id: NonEmptyStr

    @model_validator(mode="after")
    def modes_unique(self) -> "OperationDescriptor":
        if not self.supported_modes or len(set(self.supported_modes)) != len(self.supported_modes):
            raise ValueError("supported_modes must be non-empty and unique")
        return self


class HandlerRegistryManifest(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    registry_id: NonEmptyStr
    registry_version: NonEmptyStr
    operations: tuple[OperationDescriptor, ...]
    aliases: tuple[AliasBinding, ...] = ()
    lineage: S40Lineage
    registry_hash: Sha256


class HandlerRegistryCompletenessReport(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: RegistryStatus
    expected_operations: NonNegativeInt
    registered_operations: NonNegativeInt
    executable_operations: NonNegativeInt
    blocked_operations: tuple[NonEmptyStr, ...] = ()
    missing_operations: tuple[NonEmptyStr, ...] = ()
    duplicate_operations: tuple[NonEmptyStr, ...] = ()
    alias_errors: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()
    lineage: S40Lineage
    report_hash: Sha256


class GatewayBindingManifest(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    provider_id: NonEmptyStr
    binding_version: NonEmptyStr
    enabled_transports: tuple[TransportKind, ...]
    operation_keys: tuple[NonEmptyStr, ...]
    timeout_seconds: PositiveFloat
    network_disabled_in_backtest: Literal[True] = True
    extension_snapshot_hash: Sha256
    registry_hash: Sha256
    runtime_object_key: NonEmptyStr
    snapshot_id: NonEmptyStr
    lineage: S40Lineage
    binding_hash: Sha256


class GatewayRuntimeReadinessReport(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: RegistryStatus
    execution_profile: NonEmptyStr
    operations_ready: NonNegativeInt
    operations_blocked: NonNegativeInt
    network_transports_enabled: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()
    lineage: S40Lineage
    report_hash: Sha256


class S21RuntimeBindingManifest(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    binding_id: NonEmptyStr
    provider_id: NonEmptyStr
    tool_gateway_port: Literal["ToolGatewayPort"] = "ToolGatewayPort"
    operation_keys: tuple[NonEmptyStr, ...]
    entitlement_versions: tuple[NonEmptyStr, ...] = ()
    context_bundle_hash: Sha256 | None = None
    extension_snapshot_hash: Sha256
    registry_hash: Sha256
    gateway_binding_hash: Sha256
    runtime_object_key: NonEmptyStr
    lineage: S40Lineage
    binding_hash: Sha256


class S21RuntimePreflightReport(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: RegistryStatus
    operation_count: NonNegativeInt
    entitlement_operation_count: NonNegativeInt
    unknown_entitlement_operations: tuple[NonEmptyStr, ...] = ()
    missing_provider_ids: tuple[NonEmptyStr, ...] = ()
    context_tool_mismatches: tuple[NonEmptyStr, ...] = ()
    network_policy_violations: tuple[NonEmptyStr, ...] = ()
    registry_gateway_mismatches: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()
    lineage: S40Lineage
    report_hash: Sha256
