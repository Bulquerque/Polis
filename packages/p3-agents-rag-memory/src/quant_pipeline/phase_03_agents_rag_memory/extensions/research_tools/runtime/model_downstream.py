"""Research process, downstream, and release contracts for P3.S40."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr, Sha256

from .model_base import (
    ConsumerCompatibilityStatus,
    ReleaseGateStatus,
    S40Lineage,
    SCHEMA_VERSION,
)

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


class ResearchProcessRecord(ContractModel):
    process_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    subject_refs: tuple[NonEmptyStr, ...] = ()
    proposition_refs: tuple[NonEmptyStr, ...] = ()
    tool_families_used: tuple[NonEmptyStr, ...]
    operations_used: tuple[NonEmptyStr, ...]
    operation_keys: tuple[NonEmptyStr, ...]
    requested_modes: tuple[NonEmptyStr, ...]
    executed_modes: tuple[NonEmptyStr, ...]
    visible_tool_call_count: NonNegativeInt
    internal_subquery_count: NonNegativeInt = 0
    cost_units: NonNegativeFloat
    source_diversity: NonNegativeInt
    source_quality_mean: Probability
    evidence_coverage: Probability
    counterevidence_ratio: Probability = 0.0
    information_latency_seconds: NonNegativeFloat
    future_records_rejected: NonNegativeInt
    downgrade_count: NonNegativeInt
    truncated: bool
    evidence_refs: tuple[NonEmptyStr, ...]
    process_hash: Sha256


class ResearchProcessPanel(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[ResearchProcessRecord, ...]
    lineage: S40Lineage
    panel_hash: Sha256


class DownstreamHandoffManifest(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    handoff_id: NonEmptyStr
    consumer_phase: Literal["P4", "P9"]
    compatibility_status: ConsumerCompatibilityStatus
    artifact_ids: tuple[NonEmptyStr, ...]
    schema_refs: tuple[NonEmptyStr, ...]
    content_hashes: tuple[Sha256, ...]
    required_consumer_changes: tuple[NonEmptyStr, ...] = ()
    lineage: S40Lineage
    manifest_hash: Sha256


class P9LearningEvidenceRecord(ContractModel):
    learning_evidence_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    requested_mode: NonEmptyStr
    executed_mode: NonEmptyStr
    cost_units: NonNegativeFloat
    evidence_coverage: Probability
    source_quality_mean: Probability
    belief_commitment_refs: tuple[NonEmptyStr, ...]
    evidence_refs: tuple[NonEmptyStr, ...]
    result_hash: Sha256
    trace_hash: Sha256
    model_knowledge_cutoff_hash: Sha256
    known_training_cutoff: date | None = None
    eligible_feedback_cycle: Literal["N_PLUS_1_ONLY"] = "N_PLUS_1_ONLY"


class P9LearningEvidenceBundle(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[P9LearningEvidenceRecord, ...]
    model_knowledge_cutoff_hash: Sha256
    known_training_cutoff: date | None = None
    eligible_feedback_cycle: Literal["N_PLUS_1_ONLY"] = "N_PLUS_1_ONLY"
    lineage: S40Lineage
    bundle_hash: Sha256


class BlockingIssue(ContractModel):
    issue_id: NonEmptyStr
    severity: Literal["BLOCKER", "MAJOR", "MINOR"]
    owner: NonEmptyStr
    reason_code: NonEmptyStr
    summary: NonEmptyStr
    affected_operations: tuple[NonEmptyStr, ...] = ()


class BlockingIssuePanel(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    records: tuple[BlockingIssue, ...]
    lineage: S40Lineage
    panel_hash: Sha256


class ReleaseGate(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: ReleaseGateStatus
    qualified_operations: NonNegativeInt
    degraded_operations: NonNegativeInt
    blocked_operations: NonNegativeInt
    failed_operations: NonNegativeInt
    p4_compatibility: ConsumerCompatibilityStatus
    p9_compatibility: ConsumerCompatibilityStatus
    p5_direct_connection_absent: Literal[True] = True
    p0_only_promotion_authority: Literal[True] = True
    blocking_issue_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()
    lineage: S40Lineage
    gate_hash: Sha256
