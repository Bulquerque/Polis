"""Configuration contracts consumed by P3.S32 builders."""

from __future__ import annotations

from typing import Annotated, Literal

from pathlib import PurePosixPath

from pydantic import Field, JsonValue, field_validator, model_validator

from ..core.models import NonEmptyStr, RelativePath, ResearchToolModel, SemVer, Sha256
from .artifacts import CounterevidencePolicy, ProviderAvailability, TransportKind


def _validate_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("relative_path must be a normalized relative POSIX path")
    if len(path.parts[0]) >= 2 and path.parts[0][1:2] == ":":
        raise ValueError("Windows absolute paths are forbidden")
    return path.as_posix()


class SchemaBundleEntry(ResearchToolModel):
    schema_id: NonEmptyStr
    schema_version: SemVer
    model_name: NonEmptyStr
    relative_path: RelativePath
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    kind: Literal["REQUEST", "RESULT", "ARTIFACT", "CONFIG"]

    @field_validator("relative_path")
    @classmethod
    def relative_only(cls, value: str) -> str:
        return _validate_relative_path(value)


class SchemaBundleManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.schema_bundle_manifest.v1"] = (
        "p3.research_tools.schema_bundle_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    entries: tuple[SchemaBundleEntry, ...]

    @model_validator(mode="after")
    def unique_ids_and_paths(self) -> "SchemaBundleManifest":
        ids = [item.schema_id for item in self.entries]
        paths = [item.relative_path for item in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("schema bundle contains duplicate schema_id")
        if len(paths) != len(set(paths)):
            raise ValueError("schema bundle contains duplicate relative_path")
        return self


class OperationConfig(ResearchToolModel):
    operation_id: NonEmptyStr
    operation_version: SemVer = "1.0.0"
    description: NonEmptyStr
    request_schema_ref: NonEmptyStr
    result_schema_ref: NonEmptyStr
    supported_mode_ids: tuple[NonEmptyStr, ...]
    required_view_classes: tuple[NonEmptyStr, ...]
    handler_id: NonEmptyStr
    default_transport: TransportKind
    deterministic_or_seeded: bool
    max_result_records: Annotated[int, Field(ge=1, le=100_000)] = 1_000
    forbidden_authorities: tuple[NonEmptyStr, ...] = ()


class ToolFamilyConfig(ResearchToolModel):
    tool_id: NonEmptyStr
    tool_version: SemVer = "1.0.0"
    title: NonEmptyStr
    description: NonEmptyStr
    capability_family: NonEmptyStr
    default_provider_id: NonEmptyStr
    default_transport: TransportKind
    forbidden_authorities: tuple[NonEmptyStr, ...]
    operations: tuple[OperationConfig, ...]


class ResearchToolCatalogConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.catalog_config.v1"] = "p3.research_tools.catalog_config.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_version: SemVer
    expected_tool_count: Annotated[int, Field(ge=1, le=128)] = 6
    expected_operation_count: Annotated[int, Field(ge=1, le=1024)] = 34
    tools: tuple[ToolFamilyConfig, ...]


class ProviderBindingConfig(ResearchToolModel):
    provider_id: NonEmptyStr
    transport: TransportKind
    availability: ProviderAvailability
    protocol: NonEmptyStr
    protocol_version: NonEmptyStr
    configured: bool
    qualified: bool
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProviderTransportBindingsConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.provider_bindings.v1"] = (
        "p3.research_tools.provider_bindings.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    providers: tuple[ProviderBindingConfig, ...]


class ModeTemplateConfig(ResearchToolModel):
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


class OperationModeAssignment(ResearchToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_ids: tuple[NonEmptyStr, ...]
    downgrade_targets: dict[str, tuple[NonEmptyStr, ...]] = Field(default_factory=dict)
    overrides: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)


class OperationModeRegistryConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.mode_config.v1"] = "p3.research_tools.mode_config.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    templates: tuple[ModeTemplateConfig, ...]
    assignments: tuple[OperationModeAssignment, ...]


class CapabilityDefinition(ResearchToolModel):
    capability_id: NonEmptyStr
    category: Literal["DOMAIN", "METHOD", "ACCESS", "RESOURCE"]
    description: NonEmptyStr


class ResearchCapabilityTaxonomyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.capability_taxonomy_config.v1"] = (
        "p3.research_tools.capability_taxonomy_config.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    capabilities: tuple[CapabilityDefinition, ...]


class AliasConfigRecord(ResearchToolModel):
    alias_tool_id: NonEmptyStr
    target_tool_id: NonEmptyStr
    target_operation_id: NonEmptyStr
    fixed_arguments: dict[str, JsonValue] = Field(default_factory=dict)
    argument_renames: dict[str, str] = Field(default_factory=dict)


class CompatibilityAliasConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.alias_config.v1"] = "p3.research_tools.alias_config.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    aliases: tuple[AliasConfigRecord, ...]


class ManifestFileRecord(ResearchToolModel):
    relative_path: RelativePath
    kind: NonEmptyStr

    @field_validator("relative_path")
    @classmethod
    def relative_only(cls, value: str) -> str:
        return _validate_relative_path(value)
    version: SemVer
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]


class PromptDescriptorTemplateManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.prompt_descriptor_manifest.v1"] = (
        "p3.research_tools.prompt_descriptor_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    files: tuple[ManifestFileRecord, ...]


class ExtensionConfigManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.extension_config_manifest.v1"] = (
        "p3.research_tools.extension_config_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    files: tuple[ManifestFileRecord, ...]
