from __future__ import annotations

from datetime import date, datetime

from pydantic import field_validator

from ._compat import MacroToolModel
from .result_contracts import MacroSeriesDefinition
from .types import NonEmptyStr, Sha256, ViewReadinessStatus, aware_utc


class MacroSeriesReleaseCatalog(MacroToolModel):
    schema_id: str = "p3.s37.macro_series_release_catalog.v1"
    schema_version: str = "1.0.0"
    snapshot_id: NonEmptyStr
    records: tuple[MacroSeriesDefinition, ...]
    content_hash: Sha256


class AssetMacroContextDefinition(MacroToolModel):
    asset_id: NonEmptyStr
    factor_id: NonEmptyStr
    family: NonEmptyStr
    series_ids: tuple[NonEmptyStr, ...]
    relationship_type: NonEmptyStr
    rationale: NonEmptyStr
    region: str | None = None
    source_id: NonEmptyStr
    available_at: datetime
    valid_from: date | None = None
    valid_to: date | None = None
    lineage_id: NonEmptyStr

    _available = field_validator("available_at")(aware_utc)


class AssetMacroContextRegistrySnapshot(MacroToolModel):
    schema_id: str = "p3.s37.asset_macro_context_registry.v1"
    schema_version: str = "1.0.0"
    snapshot_id: NonEmptyStr
    records: tuple[AssetMacroContextDefinition, ...]
    content_hash: Sha256


class MacroViewReadinessReport(MacroToolModel):
    schema_id: str = "p3.s37.macro_view_readiness_report.v1"
    snapshot_id: NonEmptyStr
    status: ViewReadinessStatus
    available_operations: tuple[str, ...]
    blocked_operations: tuple[str, ...]
    available_fields: tuple[str, ...]
    series_count: int
    observation_count: int
    vintage_capable_series_count: int
    reason_codes: tuple[str, ...]
    content_hash: Sha256
