from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import NonEmptyStr, QualificationStatus, Sha256, ViewReadinessStatus


class ViewRequirement(ContractModel):
    artifact_name: NonEmptyStr
    required_fields: tuple[NonEmptyStr, ...]
    optional_fields: tuple[NonEmptyStr, ...] = ()
    minimum_records: int = Field(default=0, ge=0)


class BoundView(ContractModel):
    artifact_name: NonEmptyStr
    artifact_id: NonEmptyStr
    schema_version: NonEmptyStr
    content_hash: Sha256
    record_count: int = Field(ge=0)
    available_fields: tuple[NonEmptyStr, ...]
    missing_required_fields: tuple[NonEmptyStr, ...] = ()
    status: ViewReadinessStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def fields_are_unique(self) -> "BoundView":
        for values in (self.available_fields, self.missing_required_fields, self.reason_codes):
            if len(values) != len(set(values)):
                raise ValueError("view collections must be unique")
        return self


class MarketViewBinding(ContractModel):
    schema_id: Literal["market_view_binding.s36.v1"] = "market_view_binding.s36.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    views: tuple[BoundView, ...]
    operation_view_map: dict[str, tuple[str, ...]]
    content_hash: Sha256


class OptionsViewBinding(ContractModel):
    schema_id: Literal["options_view_binding.s36.v1"] = "options_view_binding.s36.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    views: tuple[BoundView, ...]
    operation_view_map: dict[str, tuple[str, ...]]
    observed_iv_available: bool
    content_hash: Sha256


class ViewReadinessReport(ContractModel):
    schema_id: NonEmptyStr
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    status: QualificationStatus
    available_operations: tuple[NonEmptyStr, ...]
    blocked_operations: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def collections_are_unique(self) -> "ViewReadinessReport":
        for field_name in ("available_operations", "blocked_operations", "reason_codes"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self
