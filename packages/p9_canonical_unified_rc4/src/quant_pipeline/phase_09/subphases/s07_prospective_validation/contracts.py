"""Shared strict contracts for P9.S7.

These models are local to the S7 boundary. They intentionally do not recreate
upstream economic payloads; they carry immutable references and normalized
materialized records required by the eight S7 modules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .canonical import CANONICALIZATION_VERSION, payload_sha256

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ModuleId = Annotated[str, StringConstraints(pattern=r"^P9\.S7\.M0[1-8]$")]


class StrictModel(BaseModel):
    """Strict, immutable, finite-number model used at all S7 boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        validate_default=True,
        revalidate_instances="always",
    )


class ModuleStatus(StrEnum):
    SUCCESS = "SUCCESS"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"
    FAILED = "FAILED"


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class MaturityState(StrEnum):
    NOT_MATURED = "NOT_MATURED"
    PARTIALLY_MATURED = "PARTIALLY_MATURED"
    MATURED = "MATURED"
    SETTLED = "SETTLED"
    CENSORED = "CENSORED"
    UNOBSERVABLE = "UNOBSERVABLE"


class EvidenceClass(StrEnum):
    FACTUAL_EXECUTED = "FACTUAL_EXECUTED"
    FACTUAL_OBSERVED_NOT_EXECUTED = "FACTUAL_OBSERVED_NOT_EXECUTED"
    OBSERVABLE_COUNTERFACTUAL = "OBSERVABLE_COUNTERFACTUAL"
    MODEL_BASED_COUNTERFACTUAL = "MODEL_BASED_COUNTERFACTUAL"
    CENSORED = "CENSORED"
    UNAVAILABLE = "UNAVAILABLE"


class IntegrityEnvelope(StrictModel):
    algorithm: Literal["SHA-256"] = "SHA-256"
    canonicalization_version: Literal["JCS-LIKE-JSON-UTF8-V1"] = CANONICALIZATION_VERSION
    payload_sha256: Sha256Hex


class ArtifactReference(StrictModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    artifact_schema_name: NonEmptyStr
    artifact_schema_version: NonEmptyStr
    artifact_schema_sha256: Sha256Hex
    content_sha256: Sha256Hex
    producer_module_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: datetime | None = None
    available_at: datetime
    computed_at: datetime | None = None
    maturity_at: datetime | None = None
    uri: NonEmptyStr
    availability: Availability = Availability.AVAILABLE

    @field_validator("decision_time", "available_at", "computed_at", "maturity_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("datetime must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def validate_clock_order(self) -> "ArtifactReference":
        if self.decision_time is not None and self.available_at > self.decision_time:
            raise ValueError("available_at must not be after decision_time for decision inputs")
        if self.computed_at is not None and self.computed_at < self.available_at:
            raise ValueError("computed_at must be at or after available_at")
        if self.maturity_at is not None and self.decision_time is not None:
            if self.maturity_at < self.decision_time:
                raise ValueError("maturity_at must not precede decision_time")
        return self


class ConsumerReceipt(StrictModel):
    consumer_module_id: ModuleId
    source_contract_name: NonEmptyStr
    source_contract_version: NonEmptyStr
    source_bundle_sha256: Sha256Hex
    input_ref_ids: tuple[NonEmptyStr, ...]
    accepted_ref_ids: tuple[NonEmptyStr, ...]
    rejected_ref_ids: tuple[NonEmptyStr, ...] = ()
    reserved_ref_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_partition(self) -> "ConsumerReceipt":
        groups = [
            set(self.accepted_ref_ids),
            set(self.rejected_ref_ids),
            set(self.reserved_ref_ids),
        ]
        if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
            raise ValueError("accepted, rejected, and reserved refs must be disjoint")
        if set(self.input_ref_ids) != set().union(*groups):
            raise ValueError("receipt states must exactly cover input_ref_ids")
        if (self.rejected_ref_ids or self.reserved_ref_ids) and not self.reason_codes:
            raise ValueError("rejected or reserved refs require reason_codes")
        return self


class ModuleExecutionReceipt(StrictModel):
    module_id: ModuleId
    status: ModuleStatus
    input_artifact_ids: tuple[NonEmptyStr, ...]
    output_artifact_ids: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    started_at: datetime
    completed_at: datetime
    diagnostics_sha256: Sha256Hex
    integrity: IntegrityEnvelope

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("receipt datetimes must be UTC")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "ModuleExecutionReceipt":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must be at or after started_at")
        if self.status is ModuleStatus.SUCCESS and not self.output_artifact_ids:
            raise ValueError("SUCCESS receipt requires at least one output artifact")
        if self.status in {ModuleStatus.INVALID, ModuleStatus.FAILED} and not self.reason_codes:
            raise ValueError("INVALID or FAILED receipt requires reason_codes")
        return self


class S7SubphaseExecutionReceipt(StrictModel):
    subphase_id: Literal["P9.S7"] = "P9.S7"
    expected_module_ids: tuple[ModuleId, ...]
    module_receipts: tuple[ModuleExecutionReceipt, ...]
    status: ModuleStatus
    output_artifact_ids: tuple[NonEmptyStr, ...]
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def validate_module_conservation(self) -> "S7SubphaseExecutionReceipt":
        expected = set(self.expected_module_ids)
        actual = {receipt.module_id for receipt in self.module_receipts}
        if len(actual) != len(self.module_receipts):
            raise ValueError("duplicate module receipt")
        if actual != expected:
            raise ValueError("module receipts must exactly cover expected modules")
        child_statuses = {receipt.status for receipt in self.module_receipts}
        if self.status is ModuleStatus.SUCCESS and child_statuses != {ModuleStatus.SUCCESS}:
            raise ValueError("SUCCESS subphase cannot contain non-SUCCESS children")
        if ModuleStatus.FAILED in child_statuses and self.status is not ModuleStatus.FAILED:
            raise ValueError("FAILED child requires FAILED subphase")
        return self


class S7MaterializationReceipt(StrictModel):
    receipt_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    source_bundle_sha256s: tuple[Sha256Hex, Sha256Hex, Sha256Hex]
    materialized_payload_sha256: Sha256Hex
    producer_module_id: NonEmptyStr
    receipt_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_receipt_hash(self) -> "S7MaterializationReceipt":
        expected = payload_sha256(
            self.model_dump(mode="python", exclude={"receipt_sha256"})
        )
        if self.receipt_sha256 != expected:
            raise ValueError("S7 materialization receipt hash mismatch")
        return self


class S7UpstreamReferences(StrictModel):
    foundation_bundle: ArtifactReference
    backtest_metrics_bundle: ArtifactReference
    robustness_stress_bundle: ArtifactReference
    consumer_receipts: tuple[ConsumerReceipt, ...]

    @model_validator(mode="after")
    def validate_receipts(self) -> "S7UpstreamReferences":
        expected_hashes = {
            self.foundation_bundle.content_sha256,
            self.backtest_metrics_bundle.content_sha256,
            self.robustness_stress_bundle.content_sha256,
        }
        receipt_hashes = {receipt.source_bundle_sha256 for receipt in self.consumer_receipts}
        if not expected_hashes.issubset(receipt_hashes):
            raise ValueError("consumer receipts must cover all three upstream bundles")
        return self


class BundleHeader(StrictModel):
    contract_name: Literal["P9_S7_PROSPECTIVE_MONITORING_BUNDLE_V1"] = (
        "P9_S7_PROSPECTIVE_MONITORING_BUNDLE_V1"
    )
    contract_version: Literal["1.0.0"] = "1.0.0"
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("created_at must be UTC")
        return value


def integrity_for(model: BaseModel) -> IntegrityEnvelope:
    """Build an integrity envelope for a payload that excludes the envelope itself."""

    return IntegrityEnvelope(payload_sha256=payload_sha256(model))


def validate_reason_code(code: str) -> str:
    """Validate the local P9 reason-code namespace."""

    if not re.fullmatch(r"P9_[A-Z0-9_]+", code):
        raise ValueError(f"invalid reason code: {code}")
    return code
