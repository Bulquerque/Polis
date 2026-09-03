from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .s30_models import (
    BeliefOutcomeCommitmentLog,
    ExecutionContext,
    Phase3RunSnapshot,
    Phase4SocialHandoffManifest,
    QualityStatus,
    StrictModel,
    ValidatedSocietyStatePanel,
    VariableEvolutionInputManifest,
)

NonNegativeInt = Annotated[int, Field(ge=0)]


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class CutoffRiskClass(StrEnum):
    STRICT_CLEAN = "STRICT_CLEAN"
    LOWER_RISK = "LOWER_RISK"
    CONTAMINATION_RISK = "CONTAMINATION_RISK"
    UNKNOWN = "UNKNOWN"


class EvaluationReadiness(StrEnum):
    PENDING_MATURITY = "PENDING_MATURITY"
    READY_FOR_EVALUATION = "READY_FOR_EVALUATION"


class ConsumerBindingStatus(StrEnum):
    READY_FOR_BOUND_P9 = "READY_FOR_BOUND_P9"
    CONSUMER_NOT_YET_BOUND = "CONSUMER_NOT_YET_BOUND"
    BLOCKED = "BLOCKED"


class ModelKnowledgeCutoffReport(StrictModel):
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    release_date: date | None = None
    known_training_cutoff: date | None = None
    evaluation_start: datetime
    evaluation_end: datetime
    risk_class: CutoffRiskClass
    rationale: str = Field(min_length=1, max_length=2000)
    lineage_id: str = Field(min_length=1)

    @field_validator("evaluation_start", "evaluation_end")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def valid_evaluation_window(self) -> "ModelKnowledgeCutoffReport":
        if self.evaluation_end < self.evaluation_start:
            raise ValueError("evaluation_end must not be before evaluation_start")
        return self


class ArtifactReference(StrictModel):
    artifact_name: Literal[
        "phase4_social_handoff_manifest",
        "variable_evolution_input_manifest",
        "belief_outcome_commitment_log",
        "model_knowledge_cutoff_report",
        "phase3_run_snapshot",
        "validated_society_state_panel",
    ]
    artifact_id: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_count: NonNegativeInt
    grain: tuple[str, ...] = Field(min_length=1)
    producer_module_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    available_at: datetime
    quality_status: QualityStatus

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return _aware(value, "available_at")


class CommitmentMaturityEntry(StrictModel):
    commitment_id: str = Field(min_length=1)
    commitment_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    person_id: str = Field(min_length=1)
    underlying_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    belief_value: Annotated[float, Field(ge=-1.0, le=1.0)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence_refs: tuple[str, ...] = ()
    committed_at: datetime
    matures_at: datetime
    readiness: EvaluationReadiness
    lineage_id: str = Field(min_length=1)

    @field_validator("committed_at", "matures_at")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def maturity_after_commitment(self) -> "CommitmentMaturityEntry":
        if self.matures_at <= self.committed_at:
            raise ValueError("matures_at must be after committed_at")
        return self


class BlindHoldoutPolicy(StrictModel):
    policy_id: Literal["p9.blind_holdout.v1"] = "p9.blind_holdout.v1"
    policy_version: Literal["1.0.0"] = "1.0.0"
    evaluation_authority: Literal["P9"] = "P9"
    producer_can_read_outcomes: Literal[False] = False
    contains_outcome_labels: Literal[False] = False
    contains_evaluation_results: Literal[False] = False
    same_cycle_feedback_allowed: Literal[False] = False
    feedback_return_artifact: Literal["phase3_retro_handoff_manifest"] = (
        "phase3_retro_handoff_manifest"
    )


class ReproducibilityKeys(StrictModel):
    snapshot_id: str = Field(min_length=1)
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_registry_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bundle_build_type: Literal["p3.s31.evaluation-evidence-export/v1"] = (
        "p3.s31.evaluation-evidence-export/v1"
    )
    builder_id: Literal["quant_pipeline.phase_03_agents_rag_memory.P3.S31.M01"] = (
        "quant_pipeline.phase_03_agents_rag_memory.P3.S31.M01"
    )


class P9EvaluationEvidenceBundle(StrictModel):
    artifact_id: str = Field(min_length=1)
    created_at: datetime
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    pipeline_version: str = Field(min_length=1)
    schema_id: Literal["p3.s31.p9_evaluation_evidence_bundle.semantic"] = (
        "p3.s31.p9_evaluation_evidence_bundle.semantic"
    )
    schema_version: Literal["1.0.0"]
    items: tuple[ArtifactReference, ...] = Field(min_length=6, max_length=6)
    commitments: tuple[CommitmentMaturityEntry, ...]
    cutoff_risk_class: CutoffRiskClass
    cutoff_report_ref: str = Field(min_length=1)
    reproducibility: ReproducibilityKeys
    blind_holdout_policy: BlindHoldoutPolicy
    evaluation_authority: Literal["P9"] = "P9"
    contains_evaluation_results: Literal[False] = False
    contains_outcome_labels: Literal[False] = False
    contains_promotion_decision: Literal[False] = False
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    complete: Literal[True] = True
    lineage_id: str = Field(min_length=1)

    @field_validator("created_at", "as_of_time")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def exact_artifact_set(self) -> "P9EvaluationEvidenceBundle":
        names = [item.artifact_name for item in self.items]
        expected = {
            "phase4_social_handoff_manifest",
            "variable_evolution_input_manifest",
            "belief_outcome_commitment_log",
            "model_knowledge_cutoff_report",
            "phase3_run_snapshot",
            "validated_society_state_panel",
        }
        if set(names) != expected or len(names) != len(set(names)):
            raise ValueError("bundle must contain exactly the six declared evidence inputs")
        return self


class P9ConsumerCompatibilityConfig(StrictModel):
    config_id: Literal["p3.s31.p9-consumer-compatibility"] = (
        "p3.s31.p9-consumer-compatibility"
    )
    config_version: Literal["1.0.0"] = "1.0.0"
    current_p9_input_contract_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_p9_output_contract_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    declared_p9_inputs: tuple[str, ...]
    consumer_contract_id: str = Field(min_length=1)
    consumer_binding_status: ConsumerBindingStatus
    blind_holdout_policy_ref: Literal["p9.blind_holdout.v1"] = "p9.blind_holdout.v1"

    @model_validator(mode="after")
    def binding_matches_declared_inputs(self) -> "P9ConsumerCompatibilityConfig":
        required = {
            "p9_evaluation_evidence_bundle",
            "p9_context_learning_handoff_manifest",
        }
        is_bound = required.issubset(set(self.declared_p9_inputs))
        if is_bound and self.consumer_binding_status == ConsumerBindingStatus.CONSUMER_NOT_YET_BOUND:
            raise ValueError("consumer is declared bound by P9 inputs but status says not bound")
        if not is_bound and self.consumer_binding_status == ConsumerBindingStatus.READY_FOR_BOUND_P9:
            raise ValueError("consumer cannot be READY_FOR_BOUND_P9 before P9 declares both inputs")
        return self


class P9ContextLearningHandoffManifest(StrictModel):
    manifest_id: str = Field(min_length=1)
    created_at: datetime
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    pipeline_version: str = Field(min_length=1)
    schema_id: Literal["p3.s31.p9_context_learning_handoff_manifest.semantic"] = (
        "p3.s31.p9_context_learning_handoff_manifest.semantic"
    )
    schema_version: Literal["1.0.0"]
    artifact_hashes: dict[str, str]
    bundle_artifact_id: str = Field(min_length=1)
    bundle_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    consumer_contract_id: str = Field(min_length=1)
    consumer_contract_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    consumer_binding_status: ConsumerBindingStatus
    evaluation_authority: Literal["P9"] = "P9"
    blind_holdout_policy_ref: Literal["p9.blind_holdout.v1"] = "p9.blind_holdout.v1"
    contains_evaluation_results: Literal[False] = False
    contains_promotion_decision: Literal[False] = False
    quality_status: QualityStatus
    quality_reasons: tuple[str, ...]
    complete: Literal[True] = True
    lineage_id: str = Field(min_length=1)

    @field_validator("created_at", "as_of_time")
    @classmethod
    def aware_datetime(cls, value: datetime, info):  # type: ignore[no-untyped-def]
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def exact_hash_set(self) -> "P9ContextLearningHandoffManifest":
        expected = {
            "p9_evaluation_evidence_bundle",
            "phase4_social_handoff_manifest",
            "variable_evolution_input_manifest",
            "phase3_run_snapshot",
        }
        if set(self.artifact_hashes) != expected:
            raise ValueError("artifact_hashes must contain exactly the four handoff artifacts")
        for value in self.artifact_hashes.values():
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("artifact_hashes values must be lowercase SHA-256 digests")
        return self


__all__ = [
    "BeliefOutcomeCommitmentLog",
    "BlindHoldoutPolicy",
    "CommitmentMaturityEntry",
    "ConsumerBindingStatus",
    "CutoffRiskClass",
    "EvaluationReadiness",
    "ExecutionContext",
    "ModelKnowledgeCutoffReport",
    "P9ConsumerCompatibilityConfig",
    "P9ContextLearningHandoffManifest",
    "P9EvaluationEvidenceBundle",
    "Phase3RunSnapshot",
    "Phase4SocialHandoffManifest",
    "QualityStatus",
    "ValidatedSocietyStatePanel",
    "VariableEvolutionInputManifest",
]
