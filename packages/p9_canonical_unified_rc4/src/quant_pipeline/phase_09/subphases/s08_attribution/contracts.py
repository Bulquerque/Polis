"""Shared strict contracts for P9.S8 attribution boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    ArtifactReference,
    Availability,
    EvidenceClass,
    IntegrityEnvelope,
    ModuleStatus,
    NonEmptyStr,
    Sha256Hex,
    StrictModel,
)

from .canonical import payload_sha256

S8ModuleId = Annotated[str, StringConstraints(pattern=r"^P9\.S8\.M0[1-8]$")]


class AttributionQuality(StrEnum):
    QUALIFIED = "QUALIFIED"
    LIMITED = "LIMITED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    INVALID = "INVALID"


class CausalStrength(StrEnum):
    SUPPORTED = "SUPPORTED"
    PLAUSIBLE = "PLAUSIBLE"
    UNRESOLVED = "UNRESOLVED"


class EvidenceStrength(StrEnum):
    FACTUAL = "FACTUAL"
    OBSERVABLE = "OBSERVABLE"
    MODEL_BASED = "MODEL_BASED"
    INSUFFICIENT = "INSUFFICIENT"


class S8ConsumerReceipt(StrictModel):
    consumer_module_id: S8ModuleId
    source_contract_name: NonEmptyStr
    source_contract_version: NonEmptyStr
    source_bundle_sha256: Sha256Hex
    input_ref_ids: tuple[NonEmptyStr, ...]
    accepted_ref_ids: tuple[NonEmptyStr, ...]
    rejected_ref_ids: tuple[NonEmptyStr, ...] = ()
    reserved_ref_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_partition(self) -> "S8ConsumerReceipt":
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


class S8ModuleExecutionReceipt(StrictModel):
    module_id: S8ModuleId
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
    def validate_semantics(self) -> "S8ModuleExecutionReceipt":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must be at or after started_at")
        if self.status is ModuleStatus.SUCCESS and not self.output_artifact_ids:
            raise ValueError("SUCCESS receipt requires output artifacts")
        if self.status in {ModuleStatus.INVALID, ModuleStatus.FAILED} and not self.reason_codes:
            raise ValueError("INVALID or FAILED receipt requires reason codes")
        return self


class S8SubphaseExecutionReceipt(StrictModel):
    subphase_id: Literal["P9.S8"] = "P9.S8"
    expected_module_ids: tuple[S8ModuleId, ...]
    module_receipts: tuple[S8ModuleExecutionReceipt, ...]
    status: ModuleStatus
    output_artifact_ids: tuple[NonEmptyStr, ...]
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def validate_conservation(self) -> "S8SubphaseExecutionReceipt":
        expected = set(self.expected_module_ids)
        actual = {item.module_id for item in self.module_receipts}
        if len(actual) != len(self.module_receipts):
            raise ValueError("duplicate module receipt")
        if actual != expected:
            raise ValueError("module receipts must exactly cover expected modules")
        statuses = {item.status for item in self.module_receipts}
        if self.status is ModuleStatus.SUCCESS and statuses != {ModuleStatus.SUCCESS}:
            raise ValueError("SUCCESS subphase cannot contain non-SUCCESS children")
        if ModuleStatus.FAILED in statuses and self.status is not ModuleStatus.FAILED:
            raise ValueError("FAILED child requires FAILED subphase")
        return self


class S8UpstreamReferences(StrictModel):
    foundation_bundle: ArtifactReference
    backtest_metrics_bundle: ArtifactReference
    robustness_stress_bundle: ArtifactReference
    consumer_receipts: tuple[S8ConsumerReceipt, ...]

    @model_validator(mode="after")
    def validate_receipts(self) -> "S8UpstreamReferences":
        refs = (
            self.foundation_bundle,
            self.backtest_metrics_bundle,
            self.robustness_stress_bundle,
        )
        expected_hashes = {ref.content_sha256 for ref in refs}
        actual_hashes = {item.source_bundle_sha256 for item in self.consumer_receipts}
        if not expected_hashes.issubset(actual_hashes):
            raise ValueError("consumer receipts must cover FOUNDATION, BACKTEST_METRICS, and ROBUSTNESS_STRESS bundles")
        run_cycles = {(ref.run_id, ref.cycle_id) for ref in refs}
        if len(run_cycles) != 1:
            raise ValueError("all upstream bundles must have the same run_id/cycle_id")
        return self


class S8BundleHeader(StrictModel):
    contract_name: Literal["P9_PROSPECTIVE_ATTRIBUTION_BUNDLE_V1"] = (
        "P9_PROSPECTIVE_ATTRIBUTION_BUNDLE_V1"
    )
    contract_version: Literal["1.0.0"] = "1.0.0"
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("created_at must be UTC")
        return value


class AttributionAmount(StrictModel):
    component_id: NonEmptyStr
    pnl_effect: float
    evidence_class: EvidenceClass
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...] = ()


class RootCauseNode(StrictModel):
    cause_id: NonEmptyStr
    source_module_id: S8ModuleId
    label: NonEmptyStr
    pnl_effect: float | None = None
    causal_strength: CausalStrength
    evidence_strength: EvidenceStrength
    evidence_refs: tuple[NonEmptyStr, ...]
    contradictions: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()


class RootCauseEdge(StrictModel):
    parent_cause_id: NonEmptyStr
    child_cause_id: NonEmptyStr
    relation: Literal["CONTRIBUTES_TO", "CONTRADICTS", "CONDITIONS", "EXPLAINS"]


def integrity_for_payload(payload: object) -> IntegrityEnvelope:
    return IntegrityEnvelope(payload_sha256=payload_sha256(payload))
