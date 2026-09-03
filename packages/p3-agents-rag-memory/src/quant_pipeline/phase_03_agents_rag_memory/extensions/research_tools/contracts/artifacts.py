"""Canonical serialized artifacts produced by P3.S32."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pathlib import PurePosixPath

from pydantic import Field, JsonValue, field_validator, model_validator

from ..core.identifiers import MODULE_ID_RE, require_match
from ..core.models import NonEmptyStr, ResearchToolModel, SemVer, Sha256


class ArtifactStatus(StrEnum):
    READY = "READY"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class TransportKind(StrEnum):
    LOCAL_FUNCTION = "LOCAL_FUNCTION"
    ARTIFACT_QUERY = "ARTIFACT_QUERY"
    COMPOSITE_INTERNAL = "COMPOSITE_INTERNAL"
    MCP_OPTIONAL = "MCP_OPTIONAL"
    HTTP_OPTIONAL = "HTTP_OPTIONAL"


class ProviderAvailability(StrEnum):
    QUALIFIED_LOCAL = "QUALIFIED_LOCAL"
    OPTIONAL_NOT_CONFIGURED = "OPTIONAL_NOT_CONFIGURED"
    DISABLED = "DISABLED"
    UNQUALIFIED = "UNQUALIFIED"


class CounterevidencePolicy(StrEnum):
    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class CompatibilitySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ResearchToolLineage(ResearchToolModel):
    producer_module_id: NonEmptyStr

    @field_validator("producer_module_id")
    @classmethod
    def extension_module_only(cls, value: str) -> str:
        return require_match(value, MODULE_ID_RE, "producer_module_id")

    input_artifact_ids: tuple[NonEmptyStr, ...] = ()
    input_hashes: tuple[Sha256, ...] = ()
    configuration_hashes: tuple[Sha256, ...] = ()
    code_version: SemVer


class ArtifactEnvelope(ResearchToolModel):
    artifact_name: NonEmptyStr
    schema_id: NonEmptyStr
    schema_version: SemVer
    artifact_id: NonEmptyStr
    status: ArtifactStatus
    content_hash: Sha256
    lineage: ResearchToolLineage
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ToolDefinition(ResearchToolModel):
    tool_id: NonEmptyStr
    tool_version: SemVer
    title: NonEmptyStr
    description: NonEmptyStr
    capability_family: NonEmptyStr
    default_provider_id: NonEmptyStr
    default_transport: TransportKind
    operation_ids: tuple[NonEmptyStr, ...]
    read_only: Literal[True] = True
    point_in_time_required: Literal[True] = True
    provider_independent: Literal[True] = True
    forbidden_authorities: tuple[NonEmptyStr, ...]


class ToolOperationSpec(ResearchToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    operation_version: SemVer
    description: NonEmptyStr
    request_schema_ref: NonEmptyStr
    request_schema_hash: Sha256
    result_schema_ref: NonEmptyStr
    result_schema_hash: Sha256
    supported_mode_ids: tuple[NonEmptyStr, ...]
    required_view_classes: tuple[NonEmptyStr, ...]
    handler_id: NonEmptyStr
    default_provider_id: NonEmptyStr
    default_transport: TransportKind
    read_only: Literal[True] = True
    point_in_time_safe: Literal[True] = True
    deterministic_or_seeded: bool
    max_result_records: Annotated[int, Field(ge=1, le=100_000)]
    forbidden_authorities: tuple[NonEmptyStr, ...]


class CanonicalResearchToolCatalog(ArtifactEnvelope):
    artifact_name: Literal["canonical_research_tool_catalog"] = "canonical_research_tool_catalog"
    schema_id: Literal["p3.research_tools.catalog.v1"] = "p3.research_tools.catalog.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_version: SemVer
    tools: tuple[ToolDefinition, ...]
    tool_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def count_matches(self) -> "CanonicalResearchToolCatalog":
        if self.tool_count != len(self.tools):
            raise ValueError("tool_count must match tools")
        return self


class CanonicalToolOperationRegistry(ArtifactEnvelope):
    artifact_name: Literal["canonical_tool_operation_registry"] = "canonical_tool_operation_registry"
    schema_id: Literal["p3.research_tools.operations.v1"] = "p3.research_tools.operations.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_version: SemVer
    operations: tuple[ToolOperationSpec, ...]
    operation_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def count_matches(self) -> "CanonicalToolOperationRegistry":
        if self.operation_count != len(self.operations):
            raise ValueError("operation_count must match operations")
        return self


class ResearchModeSpec(ResearchToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_id: NonEmptyStr
    band: Literal[1, 2, 3, 4]
    required_capabilities: tuple[NonEmptyStr, ...] = ()
    required_methods: tuple[NonEmptyStr, ...] = ()
    required_view_classes: tuple[NonEmptyStr, ...] = ()
    required_source_families: Annotated[int, Field(ge=0, le=32)] = 0
    counterevidence_policy: CounterevidencePolicy = CounterevidencePolicy.NONE
    max_records: Annotated[int, Field(ge=1, le=100_000)]
    internal_subquery_limit: Annotated[int, Field(ge=0, le=100)]
    internal_work_units: Annotated[int, Field(ge=1, le=10_000)]
    coverage_floor: Annotated[float, Field(ge=0.0, le=1.0)]
    downgrade_targets: tuple[NonEmptyStr, ...] = ()


class ResearchModeRegistry(ArtifactEnvelope):
    artifact_name: Literal["research_mode_registry"] = "research_mode_registry"
    schema_id: Literal["p3.research_tools.modes.v1"] = "p3.research_tools.modes.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    modes: tuple[ResearchModeSpec, ...]
    mode_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def count_matches(self) -> "ResearchModeRegistry":
        if self.mode_count != len(self.modes):
            raise ValueError("mode_count must match modes")
        return self


class OperationModeMatrixRecord(ResearchToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_ids: tuple[NonEmptyStr, ...]
    minimum_mode_id: NonEmptyStr
    maximum_band: Literal[1, 2, 3, 4]


class OperationModeMatrix(ArtifactEnvelope):
    artifact_name: Literal["operation_mode_matrix"] = "operation_mode_matrix"
    schema_id: Literal["p3.research_tools.operation_mode_matrix.v1"] = "p3.research_tools.operation_mode_matrix.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[OperationModeMatrixRecord, ...]


class ProviderTransportRecord(ResearchToolModel):
    provider_id: NonEmptyStr
    transport: TransportKind
    availability: ProviderAvailability
    protocol: NonEmptyStr
    protocol_version: NonEmptyStr
    fingerprint: Sha256
    configured: bool
    qualified: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ProviderTransportOverlay(ArtifactEnvelope):
    artifact_name: Literal["provider_transport_overlay"] = "provider_transport_overlay"
    schema_id: Literal["p3.research_tools.provider_overlay.v1"] = "p3.research_tools.provider_overlay.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    providers: tuple[ProviderTransportRecord, ...]
    global_visible_call_limit: Annotated[int, Field(ge=0, le=5)]
    credential_policy: Literal["HANDLE_ONLY"] = "HANDLE_ONLY"


class AliasRecord(ResearchToolModel):
    alias_tool_id: NonEmptyStr
    target_tool_id: NonEmptyStr
    target_operation_id: NonEmptyStr
    fixed_arguments: dict[str, JsonValue] = Field(default_factory=dict)
    argument_renames: dict[str, str] = Field(default_factory=dict)
    deprecated: Literal[True] = True
    second_handler_forbidden: Literal[True] = True


class CompatibilityAliasRegistry(ArtifactEnvelope):
    artifact_name: Literal["compatibility_alias_registry"] = "compatibility_alias_registry"
    schema_id: Literal["p3.research_tools.aliases.v1"] = "p3.research_tools.aliases.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    aliases: tuple[AliasRecord, ...]


class ExtendedToolRecord(ResearchToolModel):
    tool_id: NonEmptyStr
    canonical: bool
    source: Literal["EXTENSION", "LEGACY_ALIAS"]
    provider_id: NonEmptyStr
    transport: TransportKind
    availability: ProviderAvailability
    operation_ids: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ExtendedToolRegistryOverlay(ArtifactEnvelope):
    artifact_name: Literal["extended_tool_registry_overlay"] = "extended_tool_registry_overlay"
    schema_id: Literal["p3.research_tools.registry_overlay.v1"] = "p3.research_tools.registry_overlay.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    tools: tuple[ExtendedToolRecord, ...]


class CompatibilityIssue(ResearchToolModel):
    issue_id: NonEmptyStr
    severity: CompatibilitySeverity
    component: NonEmptyStr
    summary: NonEmptyStr
    reason_code: NonEmptyStr
    details: dict[str, JsonValue] = Field(default_factory=dict)


class LegacyContractProjectionReport(ArtifactEnvelope):
    artifact_name: Literal["legacy_contract_projection_report"] = "legacy_contract_projection_report"
    schema_id: Literal["p3.research_tools.legacy_projection_report.v1"] = "p3.research_tools.legacy_projection_report.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    issues: tuple[CompatibilityIssue, ...]
    legacy_tool_count: Annotated[int, Field(ge=0)]
    aliases_resolved: Annotated[int, Field(ge=0)]
    external_providers_downgraded: Annotated[int, Field(ge=0)]


class SnapshotComponent(ResearchToolModel):
    component_id: NonEmptyStr
    version: SemVer
    content_hash: Sha256
    kind: NonEmptyStr


class ResearchToolExtensionSnapshot(ArtifactEnvelope):
    artifact_name: Literal["research_tool_extension_snapshot"] = "research_tool_extension_snapshot"
    schema_id: Literal["p3.research_tools.extension_snapshot.v1"] = "p3.research_tools.extension_snapshot.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_version: SemVer
    snapshot_hash: Sha256
    components: tuple[SnapshotComponent, ...]
    expected_handler_ids: tuple[NonEmptyStr, ...]
    provider_fingerprints: tuple[Sha256, ...]


class ContractPackFile(ResearchToolModel):
    relative_path: NonEmptyStr

    @field_validator("relative_path")
    @classmethod
    def relative_only(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("relative_path must be a normalized relative POSIX path")
        if len(path.parts[0]) >= 2 and path.parts[0][1:2] == ":":
            raise ValueError("Windows absolute paths are forbidden")
        return path.as_posix()

    kind: NonEmptyStr
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]


class ResearchToolContractPackManifest(ArtifactEnvelope):
    artifact_name: Literal["research_tool_contract_pack_manifest"] = "research_tool_contract_pack_manifest"
    schema_id: Literal["p3.research_tools.contract_pack_manifest.v1"] = "p3.research_tools.contract_pack_manifest.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_version: SemVer
    files: tuple[ContractPackFile, ...]
    file_count: Annotated[int, Field(ge=0)]
    schema_count: Annotated[int, Field(ge=0)]
    expected_handler_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def counts_match(self) -> "ResearchToolContractPackManifest":
        if self.file_count != len(self.files):
            raise ValueError("file_count must match files")
        if self.schema_count > self.file_count:
            raise ValueError("schema_count cannot exceed file_count")
        return self

