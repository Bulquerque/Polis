"""Strict policy configuration contracts consumed by P3.S33."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..core.models import NonEmptyStr, RelativePath, ResearchToolModel, SemVer, Sha256
from .boundary_artifacts import MissingTimeAction, VintagePolicyName


class PitDataViewPolicyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.pit_data_view_policy.v1"] = (
        "p3.research_tools.pit_data_view_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    availability_field: Literal["available_at"] = "available_at"
    observational_missing_time_action: MissingTimeAction
    temporal_reference_missing_time_action: MissingTimeAction
    atemporal_allowlist: tuple[NonEmptyStr, ...]
    default_vintage_policy: VintagePolicyName
    forbidden_backtest_vintage_policies: tuple[NonEmptyStr, ...]
    reject_network_backtest: Literal[True] = True
    require_request_as_of_equals_decision_time: Literal[True] = True


class CalendarTimezonePolicyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.calendar_timezone_policy.v1"] = (
        "p3.research_tools.calendar_timezone_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    canonical_timezone: NonEmptyStr
    naive_datetime_action: Literal["REJECT"] = "REJECT"
    date_only_timezone: NonEmptyStr
    normalize_to_utc: Literal[True] = True


class VintagePolicyConfigRecord(ResearchToolModel):
    policy_name: VintagePolicyName
    description: NonEmptyStr
    allowed_execution_modes: tuple[NonEmptyStr, ...]
    selection_rule: NonEmptyStr


class VintagePolicyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.vintage_policy_config.v1"] = (
        "p3.research_tools.vintage_policy_config.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    policies: tuple[VintagePolicyConfigRecord, ...]

    @model_validator(mode="after")
    def unique_names(self) -> "VintagePolicyConfig":
        names = [item.policy_name for item in self.policies]
        if len(names) != len(set(names)):
            raise ValueError("vintage policy names must be unique")
        return self


class EntityMapRecordConfig(ResearchToolModel):
    entity_id: NonEmptyStr
    instrument_id: NonEmptyStr | None = None
    instrument_type: NonEmptyStr
    venue: NonEmptyStr | None = None
    ticker: NonEmptyStr | None = None
    aliases: tuple[NonEmptyStr, ...] = ()
    identifiers: dict[str, NonEmptyStr] = Field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    underlying_instrument_id: NonEmptyStr | None = None


class EntityUnderlyingMapConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.entity_underlying_map.v1"] = (
        "p3.research_tools.entity_underlying_map.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    fuzzy_matching_enabled: bool = False
    minimum_probabilistic_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.95
    identifier_namespaces: tuple[NonEmptyStr, ...]
    records: tuple[EntityMapRecordConfig, ...] = ()


class BoundaryManifestEntry(ResearchToolModel):
    schema_id: NonEmptyStr
    schema_version: SemVer
    model_name: NonEmptyStr
    relative_path: RelativePath
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    kind: Literal["ARTIFACT", "CONFIG", "CONTRACT"]


class BoundarySchemaBundleManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.s33_schema_bundle_manifest.v1"] = (
        "p3.research_tools.s33_schema_bundle_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    entries: tuple[BoundaryManifestEntry, ...]

    @model_validator(mode="after")
    def unique_entries(self) -> "BoundarySchemaBundleManifest":
        ids = [item.schema_id for item in self.entries]
        paths = [item.relative_path for item in self.entries]
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
            raise ValueError("boundary schema manifest entries must be unique")
        return self


class BoundaryConfigFile(ResearchToolModel):
    relative_path: RelativePath
    kind: NonEmptyStr
    version: SemVer
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]


class BoundaryConfigManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.s33_config_manifest.v1"] = (
        "p3.research_tools.s33_config_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    files: tuple[BoundaryConfigFile, ...]
