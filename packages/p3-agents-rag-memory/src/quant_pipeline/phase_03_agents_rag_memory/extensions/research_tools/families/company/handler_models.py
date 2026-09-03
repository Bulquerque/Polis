"""Handler, readiness, and qualification contracts for P3.S38."""
from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr, Sha256

from .model_base import (
    CompanyMode, ExtensionLineage, QualificationStatus, ReadinessStatus, SCHEMA_VERSION, TOOL_ID,
)


class HandlerBindingSpec(ContractModel):
    tool_id: Literal[TOOL_ID] = TOOL_ID
    operation_id: NonEmptyStr
    handler_id: NonEmptyStr
    handler_version: NonEmptyStr
    request_schema_ref: NonEmptyStr
    result_schema_ref: NonEmptyStr
    supported_modes: tuple[CompanyMode, ...]
    required_view_ids: tuple[NonEmptyStr, ...] = ()
    deterministic_or_seeded: bool = True
    read_only: Literal[True] = True
    forbidden_authorities: tuple[NonEmptyStr, ...] = (
        "investment_recommendation", "signal_generation", "portfolio_optimization",
        "backtest", "feature_selection", "model_selection", "direct_p5_consumption",
    )

    @model_validator(mode="after")
    def modes_unique(self) -> "HandlerBindingSpec":
        if not self.supported_modes or len(set(self.supported_modes)) != len(self.supported_modes):
            raise ValueError("supported_modes must be non-empty and unique")
        return self


class HandlerBundleManifest(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    bundle_id: NonEmptyStr
    bundle_version: NonEmptyStr
    tool_id: Literal[TOOL_ID] = TOOL_ID
    handlers: tuple[HandlerBindingSpec, ...]
    lineage: ExtensionLineage
    bundle_hash: Sha256


class ReadinessRecord(ContractModel):
    operation_id: NonEmptyStr
    mode_id: CompanyMode
    status: ReadinessStatus
    required_view_ids: tuple[NonEmptyStr, ...] = ()
    available_view_ids: tuple[NonEmptyStr, ...] = ()
    missing_view_ids: tuple[NonEmptyStr, ...] = ()
    version_history_required: bool = False
    reason_codes: tuple[NonEmptyStr, ...] = ()


class CompanyOperationReadinessPanel(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[ReadinessRecord, ...]
    lineage: ExtensionLineage
    panel_hash: Sha256


class HandlerQualificationRecord(ContractModel):
    operation_id: NonEmptyStr
    mode_id: CompanyMode
    status: QualificationStatus
    handler_id: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()
    contract_tests_passed: int = 0
    leakage_tests_passed: int = 0


class CompanyOperationModeQualification(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[HandlerQualificationRecord, ...]
    lineage: ExtensionLineage
    matrix_hash: Sha256


class CompanyToolBundle(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    tool_id: Literal[TOOL_ID] = TOOL_ID
    bundle_version: NonEmptyStr
    handlers: tuple[HandlerBindingSpec, ...]
    lineage: ExtensionLineage
    bundle_hash: Sha256
