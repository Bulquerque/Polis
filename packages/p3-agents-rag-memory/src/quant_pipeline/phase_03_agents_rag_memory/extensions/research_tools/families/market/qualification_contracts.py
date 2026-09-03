from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import NonEmptyStr, QualificationStatus, Sha256


class HandlerSpec(ContractModel):
    tool_id: Literal["market.observation.v1", "options.observation.v1"]
    operation_id: NonEmptyStr
    handler_id: NonEmptyStr
    handler_version: Literal["1.0.0"] = "1.0.0"
    request_model: NonEmptyStr
    result_model: Literal["MarketDerivativesToolResultEnvelope"] = (
        "MarketDerivativesToolResultEnvelope"
    )
    supported_modes: tuple[NonEmptyStr, ...]
    read_only: Literal[True] = True
    point_in_time_safe: Literal[True] = True

    @model_validator(mode="after")
    def modes_are_unique(self) -> "HandlerSpec":
        if not self.supported_modes:
            raise ValueError("handler must support at least one mode")
        if len(self.supported_modes) != len(set(self.supported_modes)):
            raise ValueError("supported_modes must be unique")
        return self


class HandlerBundleManifest(ContractModel):
    schema_id: NonEmptyStr
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_id: NonEmptyStr
    tool_id: Literal["market.observation.v1", "options.observation.v1"]
    handlers: tuple[HandlerSpec, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def operations_are_unique(self) -> "HandlerBundleManifest":
        operations = [item.operation_id for item in self.handlers]
        if len(operations) != len(set(operations)):
            raise ValueError("handler operations must be unique")
        if any(item.tool_id != self.tool_id for item in self.handlers):
            raise ValueError("handler tool_id must match bundle tool_id")
        return self


class OperationModeQualification(ContractModel):
    tool_id: Literal["market.observation.v1", "options.observation.v1"]
    operation_id: NonEmptyStr
    mode_id: NonEmptyStr
    status: QualificationStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()
    required_views: tuple[NonEmptyStr, ...] = ()
    test_targets: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def collections_are_unique(self) -> "OperationModeQualification":
        for field_name in ("reason_codes", "required_views", "test_targets"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class OperationModeQualificationPanel(ContractModel):
    schema_id: Literal["market_derivatives_operation_mode_qualification.s36.v1"] = (
        "market_derivatives_operation_mode_qualification.s36.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    records: tuple[OperationModeQualification, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def pairs_are_unique(self) -> "OperationModeQualificationPanel":
        keys = [(item.tool_id, item.operation_id, item.mode_id) for item in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("tool/operation/mode records must be unique")
        return self


class MarketDerivativesToolReadinessReport(ContractModel):
    schema_id: Literal["market_derivatives_tool_readiness_report.s36.v1"] = (
        "market_derivatives_tool_readiness_report.s36.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    status: QualificationStatus
    available_tool_operations: tuple[NonEmptyStr, ...]
    blocked_tool_operation_modes: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def collections_are_unique(self) -> "MarketDerivativesToolReadinessReport":
        for field_name in (
            "available_tool_operations",
            "blocked_tool_operation_modes",
            "reason_codes",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self
