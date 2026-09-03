from __future__ import annotations

from pydantic import Field, model_validator

from .base import (
    ArtifactId,
    ModuleId,
    ModuleStatus,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)
from .integrity import IntegrityEnvelope, verify_integrity


class ModuleExecutionReceiptPayload(StrictModel):
    module_id: ModuleId
    status: ModuleStatus
    started_at: UtcDateTime
    completed_at: UtcDateTime
    input_artifact_ids: tuple[ArtifactId, ...] = ()
    output_artifact_ids: tuple[ArtifactId, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    implementation_sha256: Sha256Hex
    policy_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_semantics(self) -> "ModuleExecutionReceiptPayload":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must be >= started_at")
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("input_artifact_ids must be unique")
        if len(set(self.output_artifact_ids)) != len(self.output_artifact_ids):
            raise ValueError("output_artifact_ids must be unique")
        if self.status in {ModuleStatus.FAILED, ModuleStatus.INVALID} and not self.reason_codes:
            raise ValueError("failed/invalid receipts require reason codes")
        if self.status is ModuleStatus.SUCCESS and self.reason_codes:
            raise ValueError("SUCCESS receipt cannot contain blocking reason codes")
        return self


class ModuleExecutionReceipt(StrictModel):
    payload: ModuleExecutionReceiptPayload
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def validate_integrity(self) -> "ModuleExecutionReceipt":
        if not verify_integrity(self.payload, self.integrity):
            raise ValueError("module receipt integrity mismatch")
        return self


class SubphaseExecutionReceiptPayload(StrictModel):
    subphase_id: NonEmptyStr
    expected_module_ids: tuple[ModuleId, ...]
    module_receipts: tuple[ModuleExecutionReceipt, ...]
    status: ModuleStatus
    output_artifact_ids: tuple[ArtifactId, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_coverage(self) -> "SubphaseExecutionReceiptPayload":
        expected = set(self.expected_module_ids)
        actual = {receipt.payload.module_id for receipt in self.module_receipts}
        if len(expected) != len(self.expected_module_ids):
            raise ValueError("expected_module_ids must be unique")
        if len(actual) != len(self.module_receipts):
            raise ValueError("module receipts must have unique module IDs")
        if actual != expected:
            raise ValueError("module receipt coverage must exactly equal expected modules")
        child_statuses = {receipt.payload.status for receipt in self.module_receipts}
        if self.status is ModuleStatus.SUCCESS and child_statuses != {ModuleStatus.SUCCESS}:
            raise ValueError("SUCCESS subphase requires every child SUCCESS")
        if ModuleStatus.FAILED in child_statuses and self.status is not ModuleStatus.FAILED:
            raise ValueError("FAILED child requires FAILED subphase")
        if ModuleStatus.INVALID in child_statuses and self.status not in {
            ModuleStatus.INVALID,
            ModuleStatus.FAILED,
        }:
            raise ValueError("INVALID child requires INVALID/FAILED subphase")
        return self


class SubphaseExecutionReceipt(StrictModel):
    payload: SubphaseExecutionReceiptPayload
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def validate_integrity(self) -> "SubphaseExecutionReceipt":
        if not verify_integrity(self.payload, self.integrity):
            raise ValueError("subphase receipt integrity mismatch")
        return self


class ConsumerReceiptPayload(StrictModel):
    consumer_module_id: ModuleId
    source_contract_name: NonEmptyStr
    source_contract_version: NonEmptyStr
    source_payload_sha256: Sha256Hex
    accepted_artifact_ids: tuple[ArtifactId, ...] = ()
    rejected_artifact_ids: tuple[ArtifactId, ...] = ()
    reserved_artifact_ids: tuple[ArtifactId, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_dispositions(self) -> "ConsumerReceiptPayload":
        accepted = set(self.accepted_artifact_ids)
        rejected = set(self.rejected_artifact_ids)
        reserved = set(self.reserved_artifact_ids)
        if accepted & rejected or accepted & reserved or rejected & reserved:
            raise ValueError("accepted/rejected/reserved sets must be disjoint")
        if sum(map(len, (accepted, rejected, reserved))) != sum(
            map(
                len,
                (
                    self.accepted_artifact_ids,
                    self.rejected_artifact_ids,
                    self.reserved_artifact_ids,
                ),
            )
        ):
            raise ValueError("artifact disposition IDs must be unique")
        if (rejected or reserved) and not self.reason_codes:
            raise ValueError("rejected/reserved artifacts require reason codes")
        return self


class ConsumerReceipt(StrictModel):
    payload: ConsumerReceiptPayload
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def validate_integrity(self) -> "ConsumerReceipt":
        if not verify_integrity(self.payload, self.integrity):
            raise ValueError("consumer receipt integrity mismatch")
        return self
