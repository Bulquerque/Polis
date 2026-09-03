"""Strict contracts for the final P3 integration and promotion evidence chain."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hashing import sha256_value, valid_sha256


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ReleaseBoundModel(StrictModel):
    release_id: str = Field(min_length=1)
    release_sha256: str

    @field_validator("release_sha256")
    @classmethod
    def release_digest_is_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("release_sha256 must be a lowercase SHA-256 digest")
        return value


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_STARTED = "NOT_STARTED"
    FAIL_NOT_QUALIFIED = "FAIL_NOT_QUALIFIED"


class Authority(StrEnum):
    P0 = "P0"
    P2 = "P2"
    P3_RUNTIME = "P3_RUNTIME"
    P4 = "P4"
    P9 = "P9"
    OPERATIONS = "OPERATIONS"


class ReceiptType(StrEnum):
    PLATFORM_QUALIFICATION = "PLATFORM_QUALIFICATION"
    P2_HANDOFF = "P2_HANDOFF"
    P4_CONSUMPTION = "P4_CONSUMPTION"
    VARIABLE_EVOLUTION_CONSUMPTION = "VARIABLE_EVOLUTION_CONSUMPTION"
    P9_EVALUATION = "P9_EVALUATION"
    P9_FEEDBACK = "P9_FEEDBACK"
    N_PLUS_1_FEEDBACK = "N_PLUS_1_FEEDBACK"
    CHECKPOINT_RELOAD = "CHECKPOINT_RELOAD"
    MODULE_TRACE = "MODULE_TRACE"
    FOLD_CHECKPOINT = "FOLD_CHECKPOINT"


class PublicKeyRecord(StrictModel):
    authority: Authority
    public_key: str = Field(min_length=44, max_length=44)
    enabled: bool = True


class SignedReceipt(ReleaseBoundModel):
    receipt_version: str = "p3.integration.receipt.v2"
    receipt_type: ReceiptType
    authority: Authority
    producer: str = Field(min_length=1)
    consumer: str = Field(min_length=1)
    artifact_ids: tuple[str, ...] = Field(min_length=1)
    artifact_hashes: dict[str, str]
    schema_versions: dict[str, str]
    cardinalities: dict[str, int]
    grains: dict[str, str]
    validation_status: Literal["PASS"]
    source_cycle_id: str | None = None
    target_cycle_id: str | None = None
    consumed_at: datetime
    downstream_output_id: str | None = None
    downstream_output_hash: str | None = None
    key_id: str = Field(min_length=1)
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("artifact_hashes")
    @classmethod
    def hashes_are_valid(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not valid_sha256(item) for item in value.values()):
            raise ValueError("artifact_hashes must contain lowercase SHA-256 digests")
        return value

    @field_validator("downstream_output_hash")
    @classmethod
    def downstream_hash_is_valid(cls, value: str | None) -> str | None:
        if value is not None and not valid_sha256(value):
            raise ValueError("downstream_output_hash must be SHA-256")
        return value

    @model_validator(mode="after")
    def artifact_metadata_is_exact(self) -> "SignedReceipt":
        expected = set(self.artifact_ids)
        if len(expected) != len(self.artifact_ids):
            raise ValueError("artifact_ids must be unique")
        for name, mapping in (
            ("artifact_hashes", self.artifact_hashes),
            ("schema_versions", self.schema_versions),
            ("cardinalities", self.cardinalities),
            ("grains", self.grains),
        ):
            if set(mapping) != expected:
                raise ValueError(f"{name} must have exactly the artifact_ids keys")
        if any(value < 0 for value in self.cardinalities.values()):
            raise ValueError("cardinalities cannot be negative")
        return self

    def unsigned_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("signature", None)
        return payload


class CrossPhaseReceiptBundle(ReleaseBoundModel):
    bundle_version: str = "p3.cross-phase-receipts.v2"
    receipts: tuple[SignedReceipt, ...] = Field(min_length=1)
    bundle_hash: str


class IntegrationEntryEvidence(ReleaseBoundModel):
    evidence_version: str = "p3.integration-entry.v2"
    code_and_migration_status: Literal["PASS"]
    runtime_qualification_status: Literal["PASS"]
    real_trace_module_ids: tuple[str, ...] = Field(min_length=81, max_length=81)
    receipts: tuple[SignedReceipt, ...]
    holdout_policy_hash: str
    frozen_at: datetime
    evidence_hash: str

    @field_validator("holdout_policy_hash", "evidence_hash")
    @classmethod
    def digest_is_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("expected lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def exact_module_trace(self) -> "IntegrationEntryEvidence":
        counts = {
            1: 2, 2: 3, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 1,
            10: 2, 11: 3, 12: 2, 13: 2, 14: 2, 15: 2, 16: 2, 17: 2,
            18: 2, 19: 2, 20: 7, 21: 6, 22: 3, 23: 2, 24: 3, 25: 3,
            26: 3, 27: 3, 28: 3, 29: 2, 30: 5, 31: 2,
        }
        expected = {
            f"P3.S{subphase}.M{module:02d}"
            for subphase, count in counts.items()
            for module in range(1, count + 1)
        }
        actual = set(self.real_trace_module_ids)
        if actual != expected:
            raise ValueError(
                "trace must contain exactly the 81 canonical modules; "
                f"missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
            )
        return self


class DatasetArtifact(StrictModel):
    artifact_id: str
    source_id: str
    source_hash: str
    schema_version: str
    event_time_min: datetime
    event_time_max: datetime
    available_at_min: datetime
    available_at_max: datetime
    ingested_at_max: datetime
    underlying_ids: tuple[str, ...] = Field(min_length=1)
    corporate_actions_controlled: bool
    delistings_controlled: bool
    survivorship_controlled: bool
    revisions_controlled: bool
    missingness_rate: float = Field(ge=0.0, le=1.0)
    spread_source: str
    slippage_source: str
    liquidity_source: str
    capacity_source: str

    @field_validator("source_hash")
    @classmethod
    def source_hash_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("source_hash must be SHA-256")
        return value

    @model_validator(mode="after")
    def time_order(self) -> "DatasetArtifact":
        if self.event_time_min > self.event_time_max:
            raise ValueError("invalid event-time range")
        if self.available_at_min > self.available_at_max:
            raise ValueError("invalid available-at range")
        if self.available_at_max > self.ingested_at_max:
            raise ValueError("ingested_at_max cannot predate available_at_max")
        return self


class EvaluationDatasetManifest(ReleaseBoundModel):
    manifest_version: str = "p3.evaluation-dataset.v2"
    dataset_id: str
    artifacts: tuple[DatasetArtifact, ...] = Field(min_length=1)
    created_at: datetime
    dataset_hash: str
    point_in_time_complete: bool
    final_holdout_blinded: bool

    @field_validator("dataset_hash")
    @classmethod
    def dataset_hash_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("dataset_hash must be SHA-256")
        return value


class EvaluationSplit(StrictModel):
    fold_id: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    purge_seconds: int = Field(ge=1)
    embargo_seconds: int = Field(ge=1)
    is_final_holdout: bool = False

    @model_validator(mode="after")
    def chronology(self) -> "EvaluationSplit":
        if not self.train_start < self.train_end < self.test_start < self.test_end:
            raise ValueError("split chronology must be train_start < train_end < test_start < test_end")
        if (self.test_start - self.train_end).total_seconds() < self.purge_seconds:
            raise ValueError("purge gap is too small")
        return self


class EvaluationSplitManifest(ReleaseBoundModel):
    manifest_version: str = "p3.evaluation-splits.v2"
    dataset_hash: str
    splits: tuple[EvaluationSplit, ...] = Field(min_length=5)
    split_hash: str
    final_holdout_fold_id: str
    holdout_opened_at: datetime | None = None

    @field_validator("dataset_hash", "split_hash")
    @classmethod
    def split_digest_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("expected SHA-256")
        return value

    @model_validator(mode="after")
    def validate_splits(self) -> "EvaluationSplitManifest":
        ids = [item.fold_id for item in self.splits]
        if len(ids) != len(set(ids)):
            raise ValueError("fold_id must be unique")
        matches = [
            item for item in self.splits
            if item.fold_id == self.final_holdout_fold_id and item.is_final_holdout
        ]
        if len(matches) != 1:
            raise ValueError("exactly one final holdout split is required")
        ordered = sorted(self.splits, key=lambda item: item.test_start)
        for left, right in zip(ordered, ordered[1:]):
            if left.test_end > right.test_start:
                raise ValueError("test windows must not overlap")
        return self


SUPPORTED_METRICS = {
    "brier_score": "LOWER",
    "log_loss": "LOWER",
    "net_return": "HIGHER",
    "max_drawdown": "LOWER",
    "evidence_coverage": "HIGHER",
    "cost": "LOWER",
    "latency_ms": "LOWER",
}


class MetricThreshold(StrictModel):
    metric: Literal[
        "brier_score", "log_loss", "net_return", "max_drawdown",
        "evidence_coverage", "cost", "latency_ms",
    ]
    direction: Literal["HIGHER", "LOWER"]
    minimum_delta: float
    alpha: float = Field(gt=0.0, lt=1.0)
    guardrail: bool = False

    @model_validator(mode="after")
    def direction_matches_metric(self) -> "MetricThreshold":
        expected = SUPPORTED_METRICS[self.metric]
        if self.direction != expected:
            raise ValueError(f"{self.metric} requires direction={expected}")
        return self


class ExperimentRegistry(ReleaseBoundModel):
    registry_version: str = "p3.experiment-registry.v2"
    experiment_id: str
    dataset_hash: str
    split_hash: str
    variants: tuple[str, ...]
    seeds: tuple[int, ...] = Field(min_length=3)
    prompt_hash: str
    model_fingerprint: str
    provider_fingerprint: str
    configuration_hash: str
    cache_policy_hash: str
    primary_metrics: tuple[MetricThreshold, ...] = Field(min_length=1)
    frozen_at: datetime
    holdout_access_policy: Literal["BLIND_UNTIL_FROZEN"]
    registry_hash: str

    @model_validator(mode="after")
    def validate_registry(self) -> "ExperimentRegistry":
        expected = {
            "SEARCH_RAG", "SINGLE_AGENT", "SOCIETY_NO_RELATIONS",
            "SOCIETY_NO_MEMORY", "SOCIETY_NO_TOOLS", "FULL_SOCIETY",
        }
        if set(self.variants) != expected or len(self.variants) != len(expected):
            raise ValueError(f"variants must be exactly {sorted(expected)}")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be unique")
        metrics = [item.metric for item in self.primary_metrics]
        if len(metrics) != len(set(metrics)):
            raise ValueError("primary_metrics must be unique")
        if not any(not item.guardrail for item in self.primary_metrics):
            raise ValueError("at least one non-guardrail primary metric is required")
        for field in (
            "dataset_hash", "split_hash", "prompt_hash", "model_fingerprint",
            "provider_fingerprint", "configuration_hash", "cache_policy_hash",
            "registry_hash",
        ):
            if not valid_sha256(str(getattr(self, field))):
                raise ValueError(f"{field} must be SHA-256")
        return self


class CommitmentRecord(StrictModel):
    commitment_id: str
    proposition_id: str
    underlying_id: str
    horizon: str
    source_cycle_id: str
    as_of_time: datetime
    created_at: datetime
    outcome_available_at: datetime
    commitment_hash: str

    @model_validator(mode="after")
    def no_hindsight(self) -> "CommitmentRecord":
        if self.created_at > self.as_of_time:
            raise ValueError("commitment cannot be created after as_of_time")
        if self.as_of_time >= self.outcome_available_at:
            raise ValueError("outcome must mature after commitment as_of_time")
        if not valid_sha256(self.commitment_hash):
            raise ValueError("commitment_hash must be SHA-256")
        return self


class OutcomeRecord(StrictModel):
    commitment_id: str
    proposition_id: str
    underlying_id: str
    horizon: str
    source_cycle_id: str
    outcome_available_at: datetime
    observed_at: datetime
    outcome_hash: str

    @model_validator(mode="after")
    def mature(self) -> "OutcomeRecord":
        if self.observed_at < self.outcome_available_at:
            raise ValueError("outcome was observed before availability")
        if not valid_sha256(self.outcome_hash):
            raise ValueError("outcome_hash must be SHA-256")
        return self


class CommitmentCoverageReport(ReleaseBoundModel):
    report_version: str = "p3.commitment-coverage.v2"
    experiment_id: str
    commitments: tuple[CommitmentRecord, ...]
    outcomes: tuple[OutcomeRecord, ...]
    matched_count: int
    unmatched_commitment_ids: tuple[str, ...]
    duplicate_ids: tuple[str, ...]
    premature_outcome_ids: tuple[str, ...]
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    status: Literal["PASS", "FAIL"]
    report_hash: str


class PriorSource(StrictModel):
    source_type: Literal["OBSERVED_DATA", "LITERATURE", "EXPERT_ELICITATION"]
    source_id: str
    source_hash: str
    citation_or_owner: str
    effective_at: datetime

    @field_validator("source_hash")
    @classmethod
    def prior_hash_is_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("source_hash must be SHA-256")
        return value


class SensitivityPoint(StrictModel):
    parameter: str
    value: float
    coverage: float = Field(ge=0.0, le=1.0)
    density: float = Field(ge=0.0)
    effective_sample_size: float = Field(gt=0.0)


class PopulationCalibrationBundle(ReleaseBoundModel):
    bundle_version: str = "p3.population-calibration.v2"
    experiment_id: str
    prior_sources: tuple[PriorSource, ...] = Field(min_length=1)
    resolved_parameters: dict[str, float | int | bool]
    seeds: tuple[int, ...] = Field(min_length=3)
    version_stability_score: float = Field(ge=0.0, le=1.0)
    seed_stability_score: float = Field(ge=0.0, le=1.0)
    effective_sample_size: float = Field(gt=0.0)
    sensitivity_curve: tuple[SensitivityPoint, ...] = Field(min_length=3)
    frozen_at: datetime
    bundle_hash: str


class GraphMetricComparison(StrictModel):
    metric: Literal[
        "degree_distribution", "clustering", "assortativity", "homophily",
        "centralization", "component_sizes", "path_length",
    ]
    observed: float
    generated: float
    tolerance: float = Field(ge=0.0)
    passed: bool


class SocialGraphCalibrationReport(ReleaseBoundModel):
    report_version: str = "p3.social-graph-calibration.v2"
    experiment_id: str
    benchmark_source: PriorSource
    comparisons: tuple[GraphMetricComparison, ...] = Field(min_length=7, max_length=7)
    status: Literal["PASS", "FAIL"]
    report_hash: str


class StressScenario(StrictModel):
    scenario: Literal[
        "STARVATION", "RUNAWAY_FEEDBACK", "ARTIFICIAL_POLARIZATION",
        "FROZEN_RELATIONSHIPS", "VOLATILE_RELATIONSHIPS",
    ]
    threshold: float
    observed: float
    passed: bool


class ActivationTrustSensitivityReport(ReleaseBoundModel):
    report_version: str = "p3.activation-trust-sensitivity.v2"
    experiment_id: str
    scenarios: tuple[StressScenario, ...] = Field(min_length=5, max_length=5)
    status: Literal["PASS", "FAIL"]
    report_hash: str


class ExperimentalUnit(StrictModel):
    fold_id: str
    seed: int
    experiment_registry_hash: str
    checkpoint_hash: str
    dataset_hash: str
    split_hash: str
    provider_fingerprint: str
    model_fingerprint: str
    prompt_hash: str
    configuration_hash: str
    cache_hash: str

    @model_validator(mode="after")
    def all_hashes_are_valid(self) -> "ExperimentalUnit":
        for field in (
            "experiment_registry_hash", "checkpoint_hash", "dataset_hash", "split_hash",
            "provider_fingerprint", "model_fingerprint", "prompt_hash",
            "configuration_hash", "cache_hash",
        ):
            if not valid_sha256(str(getattr(self, field))):
                raise ValueError(f"{field} must be SHA-256")
        return self


class VariantExecutionRecord(StrictModel):
    variant: Literal[
        "SEARCH_RAG", "SINGLE_AGENT", "SOCIETY_NO_RELATIONS",
        "SOCIETY_NO_MEMORY", "SOCIETY_NO_TOOLS", "FULL_SOCIETY",
    ]
    unit: ExperimentalUnit
    ablated_component: Literal["RELATIONS", "MEMORY", "TOOLS", "SOCIETY", "NONE", "SEARCH_ONLY"]
    execution_trace_hash: str
    output_artifact_hash: str
    source_kind: Literal["REAL_PIPELINE"]
    started_at: datetime
    completed_at: datetime
    record_hash: str

    @model_validator(mode="after")
    def execution_is_valid(self) -> "VariantExecutionRecord":
        if self.completed_at <= self.started_at:
            raise ValueError("completed_at must be after started_at")
        for field in ("execution_trace_hash", "output_artifact_hash", "record_hash"):
            if not valid_sha256(str(getattr(self, field))):
                raise ValueError(f"{field} must be SHA-256")
        expected = {
            "SEARCH_RAG": "SEARCH_ONLY",
            "SINGLE_AGENT": "SOCIETY",
            "SOCIETY_NO_RELATIONS": "RELATIONS",
            "SOCIETY_NO_MEMORY": "MEMORY",
            "SOCIETY_NO_TOOLS": "TOOLS",
            "FULL_SOCIETY": "NONE",
        }
        if self.ablated_component != expected[self.variant]:
            raise ValueError("ablated_component does not match variant")
        return self


class VariantExecutionManifest(ReleaseBoundModel):
    manifest_version: str = "p3.variant-execution.v2"
    experiment_id: str
    experiment_registry_hash: str
    records: tuple[VariantExecutionRecord, ...] = Field(min_length=90)
    manifest_hash: str


class EvaluationObservation(StrictModel):
    experiment_id: str
    variant: Literal[
        "SEARCH_RAG", "SINGLE_AGENT", "SOCIETY_NO_RELATIONS",
        "SOCIETY_NO_MEMORY", "SOCIETY_NO_TOOLS", "FULL_SOCIETY",
    ]
    fold_id: str
    seed: int
    observation_id: str
    execution_record_hash: str
    output_artifact_hash: str
    brier_score: float = Field(ge=0.0)
    log_loss: float = Field(ge=0.0)
    net_return: float
    volatility: float = Field(ge=0.0)
    max_drawdown: float = Field(ge=0.0, le=1.0)
    turnover: float = Field(ge=0.0)
    cost: float = Field(ge=0.0)
    latency_ms: float = Field(ge=0.0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    effective_sample_size: float = Field(gt=0.0)
    pit_integrity: Literal[True]
    authority_integrity: Literal[True]
    source_kind: Literal["REAL_PIPELINE"]

    @field_validator("execution_record_hash", "output_artifact_hash")
    @classmethod
    def observation_hash_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("expected SHA-256")
        return value


class EvaluationObservationPanel(ReleaseBoundModel):
    panel_version: str = "p3.evaluation-observations.v2"
    experiment_id: str
    experiment_registry_hash: str
    observations: tuple[EvaluationObservation, ...] = Field(min_length=90)
    panel_hash: str


class RuntimeCostLatencyRow(StrictModel):
    variant: Literal[
        "SEARCH_RAG", "SINGLE_AGENT", "SOCIETY_NO_RELATIONS",
        "SOCIETY_NO_MEMORY", "SOCIETY_NO_TOOLS", "FULL_SOCIETY",
    ]
    fold_id: str
    seed: int
    execution_record_hash: str
    provider_cost: float = Field(ge=0.0)
    storage_cost: float = Field(ge=0.0)
    tool_cost: float = Field(ge=0.0)
    latency_ms_p50: float = Field(ge=0.0)
    latency_ms_p95: float = Field(ge=0.0)

    @field_validator("execution_record_hash")
    @classmethod
    def execution_hash_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("execution_record_hash must be SHA-256")
        return value


class RuntimeCostLatencyPanel(ReleaseBoundModel):
    panel_version: str = "p3.runtime-cost-latency.v2"
    experiment_id: str
    experiment_registry_hash: str
    rows: tuple[RuntimeCostLatencyRow, ...] = Field(min_length=90)
    cost_budget_per_execution: float = Field(gt=0.0)
    latency_budget_ms_p95: float = Field(gt=0.0)
    panel_hash: str


class QualificationCheck(StrictModel):
    check_id: Literal[
        "MODULE_REGRESSION", "REPOSITORY_REGRESSION", "RUFF", "MYPY",
        "COVERAGE", "LOAD", "CONCURRENCY", "DISASTER_RECOVERY",
        "PRISTINE_INSTALL", "MIGRATION_IDEMPOTENCE", "ROLLBACK_PRISTINE",
        "SBOM", "DEPENDENCY_LOCK", "SILENT_FALLBACK_SCAN",
    ]
    status: Literal["PASS"]
    command: str = Field(min_length=1)
    evidence_path: str = Field(min_length=1)
    evidence_sha256: str
    executed_at: datetime
    tool_version: str | None = None

    @field_validator("evidence_path")
    @classmethod
    def path_is_relative_and_safe(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("evidence_path must be a safe relative path")
        return value

    @field_validator("evidence_sha256")
    @classmethod
    def evidence_hash_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("evidence_sha256 must be SHA-256")
        return value


class QualificationSummary(ReleaseBoundModel):
    summary_version: str = "p3.qualification-summary.v2"
    module_count: Literal[81]
    coverage_percent: float = Field(ge=0.0, le=100.0)
    silent_fallback_count: Literal[0]
    checks: tuple[QualificationCheck, ...] = Field(min_length=14, max_length=14)
    evidence_hash: str

    @model_validator(mode="after")
    def checks_are_exact(self) -> "QualificationSummary":
        expected = {
            "MODULE_REGRESSION", "REPOSITORY_REGRESSION", "RUFF", "MYPY",
            "COVERAGE", "LOAD", "CONCURRENCY", "DISASTER_RECOVERY",
            "PRISTINE_INSTALL", "MIGRATION_IDEMPOTENCE", "ROLLBACK_PRISTINE",
            "SBOM", "DEPENDENCY_LOCK", "SILENT_FALLBACK_SCAN",
        }
        actual = {item.check_id for item in self.checks}
        if actual != expected or len(self.checks) != len(expected):
            raise ValueError(f"qualification checks must be exactly {sorted(expected)}")
        return self


class P0PromotionDecision(ReleaseBoundModel):
    decision_version: str = "p0.p3-promotion-decision.v2"
    candidate_bundle_hash: str
    decision: Literal["PROMOTE", "REJECT"]
    decided_at: datetime
    authority: Literal[Authority.P0]
    key_id: str
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("candidate_bundle_hash")
    @classmethod
    def candidate_hash_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("candidate_bundle_hash must be SHA-256")
        return value

    def unsigned_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("signature", None)
        return payload


class PromotionCandidateBundle(ReleaseBoundModel):
    bundle_version: str = "p3.promotion-candidate.v2"
    qualification_chain_hash: str
    evidence_hashes: dict[str, str]
    created_at: datetime
    promotion_authority: Literal["P0_ONLY"] = "P0_ONLY"
    production_promotion_allowed: Literal[False] = False
    bundle_hash: str

    @field_validator("qualification_chain_hash", "bundle_hash")
    @classmethod
    def candidate_digest_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("expected SHA-256")
        return value

    @field_validator("evidence_hashes")
    @classmethod
    def evidence_hashes_valid(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or any(not valid_sha256(item) for item in value.values()):
            raise ValueError("evidence_hashes must be non-empty SHA-256 values")
        return value


class GateResult(StrictModel):
    gate_id: str
    status: GateStatus
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_hashes: dict[str, str] = Field(default_factory=dict)


class IntegrationGateReport(ReleaseBoundModel):
    report_version: str = "p3.integration-gates.v2"
    gates: tuple[GateResult, ...]
    overall_status: GateStatus
    p0_promotion_validated: bool
    production_promotion_allowed: bool
    generated_at: datetime
    qualification_chain_hash: str
    report_hash: str

    @model_validator(mode="after")
    def promotion_control(self) -> "IntegrationGateReport":
        if self.production_promotion_allowed and not self.p0_promotion_validated:
            raise ValueError("P3 cannot self-promote")
        return self


def with_computed_hash(model: StrictModel, field_name: str) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload[field_name] = ""
    payload[field_name] = sha256_value(payload)
    return payload
