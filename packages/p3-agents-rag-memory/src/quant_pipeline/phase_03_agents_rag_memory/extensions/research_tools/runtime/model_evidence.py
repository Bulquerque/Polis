"""Evidence and qualification contracts for P3.S40."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr, Sha256, utc

from .model_base import OutcomeStatus, QualificationStatus, RegistryStatus, S40Lineage, SCHEMA_VERSION

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


class CoverageReport(ContractModel):
    score: Probability
    observations_requested: NonNegativeInt = 0
    observations_used: NonNegativeInt = 0
    observations_rejected_future: NonNegativeInt = 0
    observations_rejected_quality: NonNegativeInt = 0
    missing_requirements: tuple[NonEmptyStr, ...] = ()


class ProvenanceEvidence(ContractModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    available_at: datetime
    content_hash: Sha256
    source_quality: Probability = 1.0
    p1_raw_artifact_id: str | None = None
    p2_artifact_id: str | None = None
    p2_record_id: str | None = None
    p2_lineage_id: str | None = None

    @field_validator("available_at")
    @classmethod
    def available_at_is_aware(cls, value: datetime) -> datetime:
        return utc(value)


class ProvenanceReport(ContractModel):
    evidence: tuple[ProvenanceEvidence, ...]
    source_families: tuple[NonEmptyStr, ...]
    source_count: NonNegativeInt
    lineage_complete: bool
    provenance_hash: Sha256


class PitProof(ContractModel):
    decision_time: datetime
    latest_available_at: datetime | None = None
    records_rejected_future: NonNegativeInt = 0
    p1_snapshot_id: str | None = None
    p2_snapshot_id: str | None = None
    input_hashes: tuple[Sha256, ...] = ()
    proof_hash: Sha256

    @field_validator("decision_time", "latest_available_at")
    @classmethod
    def times_are_aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)

    @model_validator(mode="after")
    def latest_is_visible(self) -> "PitProof":
        if self.latest_available_at and self.latest_available_at > self.decision_time:
            raise ValueError("latest_available_at exceeds decision_time")
        return self


class ExecutionReport(ContractModel):
    execution_id: NonEmptyStr
    provider_id: NonEmptyStr
    latency_ms: NonNegativeFloat
    cost_units: NonNegativeFloat
    deterministic_or_seeded: bool
    request_hash: Sha256
    response_hash: Sha256 | None = None
    trace_id: NonEmptyStr


class ResearchToolResultEnvelope(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    execution_id: NonEmptyStr
    request_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    outcome_status: OutcomeStatus
    requested_mode: NonEmptyStr
    executed_mode: NonEmptyStr
    downgrade_reason: str | None = None
    canonical_payload_hash: Sha256
    evidence_refs: tuple[NonEmptyStr, ...]
    coverage: CoverageReport
    provenance: ProvenanceReport
    pit_proof: PitProof
    execution: ExecutionReport
    reason_codes: tuple[NonEmptyStr, ...] = ()
    envelope_hash: Sha256


class ResearchToolResultEnvelopePanel(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[ResearchToolResultEnvelope, ...]
    lineage: S40Lineage
    panel_hash: Sha256


class ResearchToolEvidenceMap(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[ProvenanceEvidence, ...]
    lineage: S40Lineage
    map_hash: Sha256


class ResearchToolExecutionTraceRecord(ContractModel):
    trace_id: NonEmptyStr
    span_id: NonEmptyStr
    parent_span_id: str | None = None
    event_name: NonEmptyStr
    event_time: datetime
    run_id: str | None = None
    cycle_id: str | None = None
    cognition_transaction_id: NonEmptyStr
    request_id: NonEmptyStr
    execution_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    event_hash: Sha256

    @field_validator("event_time")
    @classmethod
    def event_time_is_aware(cls, value: datetime) -> datetime:
        return utc(value)


class ResearchToolExecutionTracePanel(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[ResearchToolExecutionTraceRecord, ...]
    lineage: S40Lineage
    panel_hash: Sha256


class OperationModeQualificationRecord(ContractModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_id: NonEmptyStr
    status: QualificationStatus
    handler_id: NonEmptyStr
    contract_tests_passed: NonNegativeInt = 0
    integration_tests_passed: NonNegativeInt = 0
    leakage_tests_passed: NonNegativeInt = 0
    replay_tests_passed: NonNegativeInt = 0
    reason_codes: tuple[NonEmptyStr, ...] = ()


class OperationModeQualificationMatrix(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[OperationModeQualificationRecord, ...]
    lineage: S40Lineage
    matrix_hash: Sha256


class ResearchToolLeakageReport(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: RegistryStatus
    tests_run: NonNegativeInt
    tests_passed: NonNegativeInt
    failed_test_ids: tuple[NonEmptyStr, ...] = ()
    invariants: tuple[NonEmptyStr, ...]
    lineage: S40Lineage
    report_hash: Sha256


class QualificationEvidenceManifest(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    artifact_ids: tuple[NonEmptyStr, ...]
    artifact_hashes: tuple[Sha256, ...]
    lineage: S40Lineage
    manifest_hash: Sha256
