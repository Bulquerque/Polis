from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import CorpusMode, NonEmptyStr, QualificationStatus, Sha256


class HandlerSpec(ContractModel):
    tool_id: Literal["research.corpus.v1"] = "research.corpus.v1"
    operation_id: NonEmptyStr
    handler_id: NonEmptyStr
    handler_version: Literal["1.0.0"] = "1.0.0"
    request_model: NonEmptyStr
    result_model: Literal["CorpusToolResultEnvelope"] = "CorpusToolResultEnvelope"
    supported_modes: tuple[CorpusMode, ...]
    read_only: Literal[True] = True
    point_in_time_safe: Literal[True] = True

    @model_validator(mode="after")
    def modes_are_nonempty_and_unique(self) -> "HandlerSpec":
        if not self.supported_modes:
            raise ValueError("handler must support at least one mode")
        if len(self.supported_modes) != len(set(self.supported_modes)):
            raise ValueError("supported_modes must be unique")
        return self


class HandlerBundleManifest(ContractModel):
    schema_id: Literal["corpus_handler_bundle.s35.v1"] = "corpus_handler_bundle.s35.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_id: NonEmptyStr
    tool_id: Literal["research.corpus.v1"] = "research.corpus.v1"
    handlers: tuple[HandlerSpec, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def operations_are_unique(self) -> "HandlerBundleManifest":
        operations = [item.operation_id for item in self.handlers]
        if len(operations) != len(set(operations)):
            raise ValueError("handler bundle contains duplicate operations")
        return self


class OperationModeQualification(ContractModel):
    operation_id: NonEmptyStr
    mode_id: CorpusMode
    status: QualificationStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()
    required_capabilities: tuple[NonEmptyStr, ...] = ()
    test_targets: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def lists_are_unique(self) -> "OperationModeQualification":
        for field_name in ("reason_codes", "required_capabilities", "test_targets"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class CorpusOperationQualificationPanel(ContractModel):
    schema_id: Literal["corpus_operation_mode_qualification.s35.v1"] = (
        "corpus_operation_mode_qualification.s35.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    records: tuple[OperationModeQualification, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def operation_mode_pairs_are_unique(self) -> "CorpusOperationQualificationPanel":
        pairs = [(item.operation_id, item.mode_id) for item in self.records]
        if len(pairs) != len(set(pairs)):
            raise ValueError("operation/mode qualification pairs must be unique")
        return self


class CorpusToolReadinessReport(ContractModel):
    schema_id: Literal["corpus_tool_readiness_report.s35.v1"] = (
        "corpus_tool_readiness_report.s35.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    status: QualificationStatus
    available_operations: tuple[NonEmptyStr, ...]
    blocked_operation_modes: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def collections_are_unique(self) -> "CorpusToolReadinessReport":
        for field_name in (
            "available_operations",
            "blocked_operation_modes",
            "reason_codes",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self
