from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from .artifacts import ArtifactReference
from .base import ArtifactId, NonEmptyStr, ReasonCode, StrictModel
from .handoff import P8EvaluationHandoffPayload
from .receipts import ConsumerReceipt


class HandoffValidationStatus(StrEnum):
    ACCEPTED_FULL = "ACCEPTED_FULL"
    ACCEPTED_LIMITED = "ACCEPTED_LIMITED"
    REJECTED_CONTRACT = "REJECTED_CONTRACT"
    REJECTED_INTEGRITY = "REJECTED_INTEGRITY"
    REJECTED_INCOMPLETE = "REJECTED_INCOMPLETE"


class ValidationCheck(StrictModel):
    check_id: NonEmptyStr
    passed: bool
    reason_codes: tuple[ReasonCode, ...] = ()
    details: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_reason_semantics(self) -> "ValidationCheck":
        if self.passed and self.reason_codes:
            raise ValueError("passed check cannot have blocking reason codes")
        if not self.passed and not self.reason_codes:
            raise ValueError("failed check requires reason codes")
        return self


class HandoffValidationReport(StrictModel):
    status: HandoffValidationStatus
    checks: tuple[ValidationCheck, ...]
    limitations: tuple[NonEmptyStr, ...] = ()


class ValidatedP8EvaluationHandoff(StrictModel):
    handoff: P8EvaluationHandoffPayload
    accepted_artifacts: tuple[ArtifactReference, ...]
    status: HandoffValidationStatus
    limitations: tuple[NonEmptyStr, ...]
    consumer_receipt: ConsumerReceipt
    validation_report: HandoffValidationReport

    @model_validator(mode="after")
    def validate_status(self) -> "ValidatedP8EvaluationHandoff":
        accepted_ids = {ref.artifact_id for ref in self.accepted_artifacts}
        receipt_ids = set(self.consumer_receipt.payload.accepted_artifact_ids)
        if accepted_ids != receipt_ids:
            raise ValueError("accepted artifacts must match consumer receipt")
        if self.status not in {
            HandoffValidationStatus.ACCEPTED_FULL,
            HandoffValidationStatus.ACCEPTED_LIMITED,
        }:
            raise ValueError("validated handoff requires accepted status")
        return self
